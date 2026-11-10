"""The math-shock pretask (2026-11-10): an information shock before the forecast.

The math-problem knowledge-shock project (a sibling study, outside this
repository) asks a model when each of 60 math problems will be solved -- all
open on T0, the model's training cutoff -- and then shows it, in the same
conversation, which were solved by a later snapshot date S, beside its own
forecast for each. Here that exchange comes BEFORE AIRO's forecast, in one
conversation:

  1. the math prompt (the project's forecast template, verbatim); the model
     answers in plain text with a JSON array, no tools;
  2. what happened to the problems, against the model's own forecasts (the
     project's `solved_side_by_side` reveal, verbatim up to its re-forecast
     request), then a neutral handoff -- or the handoff alone (the placebo);
  3. AIRO's prompt, unchanged.

code/run_math_shock.py runs it (the arms, the pi session that carries turns
1-2 into AIRO's call, the rows). This module is the content: the pack, the
prompts, the parser and the reveal, ported from the project's
pipeline/parse.py, render.py and followup.py so the two studies ask and score
the same way. Stdlib only.

THE PACK is one JSON file, kept OUT OF GIT (AIRO_PRETASK_DIR, default
private/pretasks/): the sample, its outcomes, the approved problem
statements and the project's templates, built by
code/build_math_shock_pack.py and pinned here by SHA-256. Rows carry only
problem codes (opaque) and hashes; the text stays in the private transcripts.
"""
import hashlib
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRETASK_DIR_ENV = "AIRO_PRETASK_DIR"
DEFAULT_PRETASK_DIR = REPO_ROOT / "private" / "pretasks"
CUTOFFS = REPO_ROOT / "data" / "training_cutoffs.json"
PACK_FORMAT = 1

# The project's parse retry (pipeline/run.py RETRY_MSG), verbatim.
RETRY_MSG = "Reply with the JSON array only, exactly as specified above."
# Between what happened and AIRO's prompt: neutral, so the shock is not
# pointed at the questions (decided 2026-11-10).
HANDOFF = "Next, a separate set of questions."
# "solved_side_by_side": the project's reveal; "none": the placebo, the
# math task with no feedback.
REVEALS = ("solved_side_by_side", "none")
# The project's reveal goes on to ask for revised forecasts of the open
# problems; here it stops at the sentence before that request, which lists
# them instead.
REVEAL_CUT = "The other {n_open} problems were still open on {snapshot_date}."

DATE = re.compile(r'^(\d{4})-(\d{2})$')


def pretask_dir():
    return Path(os.environ.get(PRETASK_DIR_ENV) or DEFAULT_PRETASK_DIR)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_text(s):
    return sha256_bytes(s.encode("utf-8"))


def pack_path(pack_id, directory=None):
    return Path(directory or pretask_dir()) / f"{pack_id}.json"


def load_pack(pack_id, sha256, directory=None):
    """The pinned pack. Refuses a missing file or one whose bytes changed."""
    path = pack_path(pack_id, directory)
    if not path.exists():
        raise FileNotFoundError(f"{path}: no pack {pack_id!r}; build it with code/build_math_shock_pack.py "
                                f"(the pack stays outside git; {PRETASK_DIR_ENV} names its folder)")
    raw = path.read_bytes()
    got = sha256_bytes(raw)
    if got != sha256:
        raise ValueError(f"{path}: SHA-256 {got} is not the pinned {sha256}; a changed pack is a new pack")
    pack = json.loads(raw)
    if pack.get("pack") != pack_id or pack.get("format") != PACK_FORMAT:
        raise ValueError(f"{path}: not pack {pack_id!r} in format {PACK_FORMAT}")
    if REVEAL_CUT not in pack["templates"]["reveal_solved"]:
        raise ValueError(f"{path}: the reveal template no longer has {REVEAL_CUT!r}")
    return pack


def by_code(pack):
    return {p["code"]: p for p in pack["problems"]}


# ---- the forecast prompt (project: pipeline/render.py render) ---------------

def order(pack, seed):
    """The problem codes in this call's order: the project's hash_rank, a
    SHA-256 of "seed|unit_id", as its per-conversation order is."""
    return [p["code"] for p in sorted(pack["problems"], key=lambda p: sha256_text(f"{seed}|{p['unit_id']}"))]


def math_prompt(pack, codes, run_date):
    probs = by_code(pack)
    items = "\n".join(f"[{c}] {probs[c]['display_name']}: {probs[c]['statement']}" for c in codes)
    t0 = pack["t0"]
    return pack["templates"]["forecast"].format(run_date=run_date, t0=t0, t0_month=t0[:7],
                                                n_items=len(codes), items=items)


# ---- parsing (project: pipeline/parse.py), violations flagged, never repaired

def extract_array(text):
    """First top-level JSON array in the text (tolerates code fences / surrounding prose)."""
    t = re.sub(r'```(?:json)?', '', text)
    i, j = t.find('['), t.rfind(']')
    if i < 0 or j < i:
        raise ValueError('no JSON array found')
    return json.loads(t[i:j + 1])


def _key(v):
    """Sortable key: (year, month); after-2100 -> (9999, 12)."""
    if v == 'after-2100':
        return (9999, 12)
    m = DATE.match(v or '')
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return (int(m.group(1)), int(m.group(2)))


def validate(items, codes, t0):
    """-> (rows, global_issues). One row per expected code."""
    t0k = (int(t0[:4]), int(t0[5:7]))
    got, issues = {}, []
    for it in items:
        c = str(it.get('id', '')).strip() if isinstance(it, dict) else ''
        if c not in codes:
            issues.append(f'unknown id {c!r}')
        elif c in got:
            issues.append(f'duplicate id {c}')
        else:
            got[c] = it
    rows = []
    for pos, c in enumerate(codes):
        it = got.get(c)
        if it is None:
            rows.append({'code': c, 'position': pos, 'valid': 0, 'issues': 'missing'})
            continue
        vals = {k: str(it.get(k, '')).strip() for k in ('best', 'q10', 'q90')}
        keys = {k: _key(v) for k, v in vals.items()}
        prob = [f'bad format {k}={vals[k]!r}' for k, v in keys.items() if v is None]
        if not prob:
            if not keys['q10'] <= keys['best'] <= keys['q90']:
                prob.append('quantiles not ordered')
            if any(v < t0k for v in keys.values()):
                prob.append('date before T0 month')
        rows.append({'code': c, 'position': pos, **vals, 'valid': int(not prob), 'issues': '; '.join(prob)})
    return rows, issues


def parse_answer(text, codes, t0):
    """A reply -> (rows, global_issues, parsed). parsed is False when no
    JSON array could be read: the project's one retry turn is then due."""
    try:
        items = extract_array(text or "")
        if not isinstance(items, list):
            raise ValueError("not a JSON array")
    except (ValueError, json.JSONDecodeError) as e:
        rows = [{'code': c, 'position': i, 'valid': 0, 'issues': 'unparseable'} for i, c in enumerate(codes)]
        return rows, [str(e)], False
    rows, issues = validate(items, codes, t0)
    return rows, issues, True


# ---- the reveal (project: pipeline/followup.py render, render.py _outcome_text)

def _month(v):
    return (9999, 12) if v == 'after-2100' else (int(v[:4]), int(v[5:7]))


def relation(solve_date, f):
    if not f or not int(f['valid']):
        return 'you gave no valid forecast'
    m = _month(solve_date[:7])
    if m < _month(f['q10']):
        return 'solved before your 10% date'
    if m <= _month(f['q90']):
        return 'solved inside your 10%-90% range'
    return 'solved after your 90% date'


def fmt(f):
    if not f or not int(f['valid']):
        return '(no valid forecast)'
    return f"best {f['best']}, q10 {f['q10']}, q90 {f['q90']}"


def outcome_text(p, s_date):
    if int(p['solved']):
        kind = p['outcome_type'] if p['outcome_type'] in ('proved', 'disproved', 'solved', 'independent') else 'resolved'
        return f"solved on {p['solve_date']} ({kind})"
    return f'still open as of {s_date}'


def stats(pack):
    probs, slog, s_date = pack["problems"], pack["sample_log"], pack["snapshot_date"]
    n_random = sum(p['role'] == 'random' for p in probs)
    return dict(t0=pack["t0"], snapshot_date=s_date, s_month=s_date[:7], n_items=len(probs),
                n_solved=sum(int(p['solved']) for p in probs),
                n_guaranteed=sum(p['role'] == 'guaranteed' for p in probs), n_random=n_random,
                n_random_solved=sum(p['role'] == 'random' and int(p['solved']) for p in probs),
                n_eligible=slog['n_eligible'], n_pool_solved=slog['n_solved_pool'],
                pool_pct=f"{100 * slog['n_solved_pool'] / slog['n_eligible']:.1f}")


def reveal_template(pack):
    """The project's reveal, cut before its re-forecast request: the still-open
    problems are listed, not asked about again."""
    t = pack["templates"]["reveal_solved"]
    return t[:t.index(REVEAL_CUT) + len(REVEAL_CUT) - 1] + ":\n\n{open_items}"


def reveal(pack, codes, rows):
    """What happened, against this conversation's forecasts, in its order."""
    probs, s_date = by_code(pack), pack["snapshot_date"]
    f = {r['code']: r for r in rows}.get
    solved = [k for k in codes if int(probs[k]['solved'])]
    open_ = [k for k in codes if not int(probs[k]['solved'])]
    s_items = '\n'.join(
        f"- [{k}] {probs[k]['display_name']}: {outcome_text(probs[k], s_date)}. "
        f"Your forecast: {fmt(f(k))}; {relation(probs[k]['solve_date'], f(k))}." for k in solved)
    o_items = '\n'.join(f"[{k}] {probs[k]['display_name']}" for k in open_)
    return reveal_template(pack).format(**stats(pack), n_open=len(open_), solved_items=s_items, open_items=o_items)


def message(pack, codes, rows, mode):
    """The user turn before AIRO's prompt: the reveal and the handoff, or
    (placebo) the handoff alone."""
    if mode not in REVEALS:
        raise ValueError(f"unknown reveal {mode!r}; have {REVEALS}")
    if mode == "none":
        return HANDOFF
    return reveal(pack, codes, rows) + "\n\n" + HANDOFF


def relations(pack, rows):
    """{code: relation} for the solved problems (the private transcript's)."""
    probs = by_code(pack)
    return {r['code']: relation(probs[r['code']]['solve_date'], r) for r in rows if int(probs[r['code']]['solved'])}


# ---- who may be asked: a model must not know what happened after T0 ---------

def load_cutoffs(path=CUTOFFS):
    return json.loads(Path(path).read_text())["models"]


def eligible(model_id, t0, cutoffs):
    """-> (ok, why). The project's rule: a model whose training cutoff is
    later than T0 cannot be asked (it may know what was solved)."""
    c = cutoffs.get(model_id)
    if not c:
        return False, f"no training cutoff on record for {model_id} (data/training_cutoffs.json)"
    if c["cutoff"] > t0[:7]:
        return False, f"training cutoff {c['cutoff']} is after T0 {t0}"
    return True, f"training cutoff {c['cutoff']} <= T0 {t0}"


# ---- what a row may say: codes and hashes, never problem text ----------------

def row_record(pack, pack_sha256, mode, codes, rows, issues, *, prompt, msg, turns, math_calls,
               usage, transcript):
    return {"pack": pack["pack"], "pack_sha256": pack_sha256, "reveal": mode, "status": "ok",
            "turns": turns, "math_calls": math_calls, "order": list(codes),
            "forecasts": [{k: r.get(k) for k in ("code", "best", "q10", "q90", "valid", "issues")} for r in rows],
            "n_valid": sum(int(r["valid"]) for r in rows), "issues": list(issues),
            "prompt_sha256": sha256_text(prompt), "message_sha256": sha256_text(msg),
            "usage": usage, "transcript": transcript}
