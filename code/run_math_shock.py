#!/usr/bin/env python3
"""The math-shock experiment (2026-11-10): AIRO's forecast after an
information shock about the model's own forecasting (redlines/math_shock.py).

Three arms, one call per eligible panel model each, in one run:

  control       the series' baseline prompt (its experiment's `none`), as is
  math-placebo  the math step, then a neutral handoff, then the same prompt
  math-shock    the math step, then what happened to the problems against the
                model's own forecasts, the handoff, then the same prompt

Two series can be asked (--experiment, as run_unified's): AIRO's, the risk
questions (experiments/airo.toml, the default), or the welfare page's, the
benefit questions (experiments/welfare.toml, 2026-11-10). One run asks one.

    python code/run_math_shock.py --dry-run     # every prompt, the models; no call
    python code/run_math_shock.py               # PAID: three arms x the eligible panel
    python code/run_math_shock.py --arm math-shock --models "GPT-6 Astra"
    python code/run_math_shock.py --experiment welfare --dry-run

Manual and unpublished: rows go to results/experiments/<name>-<run>.jsonl
(and -instrument.jsonl) like any unpublished condition's -- <name> is
math-shock for AIRO, welfare-math-shock for welfare, so that welfare's stay
out of AIRO's download (redlines/export.py airo_file) -- each call's first row
carrying `pretask` -- problem codes, the model's dates, hashes; never problem
text, since results/experiments/ reaches the public download. The transcripts
(prompts, replies, both sessions) go beside the private pack:
<AIRO_PRETASK_DIR>/<pack>/transcripts/<run>/.

HOW. run_unified.py does the work -- the prompt, the panel, the workers, the
retries, the rows -- and three of its names are wrapped here, as its tests
replace call_tools:

  run_one_joint  knows which arm a call is in, and adds `pretask` to its rows;
  call_tools     for a math arm, first the MATH STEP: pi with no tools and a
                 session file, asked the math prompt, and once more in the same
                 session if no JSON array came back (the project's retry); then
                 the series' call as always, through code/math_shock_pi,
                 which continues that session, with the reveal and handoff
                 before the series' prompt in the same user turn;
  select_models  only models whose training cutoff is at or before T0
                 (data/training_cutoffs.json), in every arm, so the arms stay
                 comparable.

Nothing in run_unified, redlines.pi_loop or agent-box changes. A math step
that fails (no array after the retry, a provider error) fails that attempt;
run_unified retries the call, and the series' prompt is never asked without
the step. The arms are defined here, not in experiments/*.toml, so neither the
cron nor `run_unified --experiment` can ask a math arm without its step. A cell
is whatever the series asks (AIRO's probabilities; welfare's percentiles and
probabilities): the wraps never read one.
"""
import argparse
import copy
import inspect
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from redlines import experiments, math_shock as ms  # noqa: E402
from redlines.llm import reasoning_for  # noqa: E402
from redlines.pi_loop import DEFAULT_TIMEOUT, pi_model  # noqa: E402

EXPERIMENT = "math-shock"
# The pack: math-problem knowledge-shock run w1-r1 (T0 2026-06-30, S
# 2026-11-02), built by code/build_math_shock_pack.py, outside git.
PACK_ID = "math-shock-w1-r1"
PACK_SHA256 = "8f3585467566a067808d7ea40f48649ee0ee214fad24b68fde457d3a4359370a"
# The series a run can ask: experiment -> the baseline condition every arm
# asks. AIRO's is the default and keeps its rows' name (EXPERIMENT).
BASES = {"airo": "none", "welfare": "none"}
DEFAULT_BASE = "airo"
ARMS = {"control": None, "math-placebo": "none", "math-shock": "solved_side_by_side"}


def experiment_name(base=DEFAULT_BASE):
    """The name a run's rows and files go under: math-shock for AIRO; for
    another series, prefixed by it (welfare-math-shock), so its files under
    results/experiments/ are that page's, never AIRO's download's
    (redlines/export.py airo_file)."""
    if base not in BASES:
        raise ValueError(f"unknown series {base!r}; have {sorted(BASES)}")
    return EXPERIMENT if base == DEFAULT_BASE else f"{base}-{EXPERIMENT}"
WRAPPER = os.path.join(ROOT, "code", "math_shock_pi")
SESSION_ENV, PI_ENV = "AIRO_PRETASK_SESSION", "AIRO_PRETASK_PI"


def load_runner():
    """code/run_unified.py as a module, as its tests load it."""
    spec = importlib.util.spec_from_file_location("run_unified", os.path.join(ROOT, "code", "run_unified.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def arm_conditions(arms=ARMS, pack_id=PACK_ID, pack_sha256=PACK_SHA256, base=DEFAULT_BASE):
    """The arms as run_unified conditions: copies of the series' baseline,
    unpublished. A math arm carries its pretask under `_pretask` (run_unified
    ignores it) and a hash of the baseline's settings and the pretask; the
    control keeps the baseline's hash, since it asks the same."""
    experiment_name(base)       # a known series, or ValueError
    base = experiments.load(base)["conditions"][BASES[base]]
    out = []
    for aid, mode in arms.items():
        c = {**copy.deepcopy(base), "id": aid, "publish": False, "pooled": False, "cadence": "manual"}
        if mode is not None:
            c["_pretask"] = {"pack": pack_id, "pack_sha256": pack_sha256, "reveal": mode}
            c["sha256"] = ms.sha256_text(json.dumps({"base": base["sha256"], "pretask": c["_pretask"]},
                                                    sort_keys=True))
        out.append(c)
    return out


# ---- the math step: pi itself, no extension, a session file -------------------
# Where and how redlines.pi_loop runs pi, so the two steps share a working
# directory (pi writes it into the system prompt), an agent directory and a
# thinking level.

def pi_base():
    return os.environ.get("REDLINES_PI_DIR") or os.path.join(tempfile.gettempdir(), "redlines-pi")


def pi_cwd():
    cwd = os.environ.get("REDLINES_PI_CWD") or os.path.join(tempfile.gettempdir(), "w")
    os.makedirs(cwd, exist_ok=True)
    return cwd


def pi_timeout():
    return int(os.environ.get("REDLINES_PI_TIMEOUT", DEFAULT_TIMEOUT))


def add_usage(total, u):
    for k in ("turns", "input_tokens", "output_tokens", "cached_tokens"):
        total[k] = total.get(k, 0) + (u.get(k) or 0)
    total["cost_usd"] = round(total.get("cost_usd", 0.0) + (u.get("cost_usd") or 0.0), 6)


def reply_text(events_path):
    """The last assistant message's text in pi's event stream (None if none)."""
    text = None
    with open(events_path) as f:
        lines = f.readlines()
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message") or {}
        if e.get("type") == "message_end" and m.get("role") == "assistant":
            c = m.get("content")
            text = c if isinstance(c, str) else "".join(
                p.get("text", "") for p in (c or []) if isinstance(p, dict) and p.get("type") == "text")
    return text


def pi_turn(harness, model, system, text, session, workdir, timeout):
    """One user turn of the math step: agent-box's pi command without its
    extension (so no tools at all), continuing (or starting) `session`."""
    attempt = harness.new_attempt_dir(workdir)
    system_file = os.path.join(attempt, "system.txt")
    with open(system_file, "w") as f:
        f.write(system)
    with open(os.path.join(attempt, "prompt.txt"), "w") as f:
        f.write(text)
    cmd = harness.pi_command(pi_model(model), system_file, thinking=reasoning_for(model) or "off")
    i = cmd.index("-e")
    del cmd[i:i + 2]
    i = cmd.index("--no-session")
    cmd[i:i + 1] = ["--session", session]
    env = harness.pi_env(pi_model(model), {"PI_CODING_AGENT_DIR": os.environ.get("PI_CODING_AGENT_DIR")
                                           or os.path.join(pi_base(), "agent")})
    events = os.path.join(attempt, "events.jsonl")
    with open(events, "w") as ev, open(os.path.join(attempt, "stderr.txt"), "w") as err:
        try:
            rc = subprocess.run(cmd, input=text.encode(), stdout=ev, stderr=err, env=env, cwd=pi_cwd(),
                                timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    with open(events) as f:
        _, usage = harness.parse_events(f)
    return reply_text(events), usage, rc


def math_step(harness, model, pack, codes, run_date, *, system, record, usage, timeout=None):
    """The math prompt, and once more if no JSON array came back. Fills
    `record` (turns, replies) and `usage` as it goes; raises on a provider
    error or a second answer without an array."""
    workdir = record["workdir"]
    os.makedirs(workdir, exist_ok=True)
    session = os.path.join(workdir, "session.jsonl")
    prompt = ms.math_prompt(pack, codes, run_date)
    for text in (prompt, ms.RETRY_MSG):
        reply, u, rc = pi_turn(harness, model, system, text, session, workdir, timeout or pi_timeout())
        add_usage(usage, u)
        record["turns"].append({"user": text, "reply": reply, "rc": rc, "usage": u})
        if rc != 0 or u.get("api_error") or reply is None:
            raise RuntimeError(f"math step: pi exit {rc}, api_error {u.get('api_error')!r} ({workdir})")
        rows, issues, parsed = ms.parse_answer(reply, codes, pack["t0"])
        if parsed:
            return {"session": session, "prompt": prompt, "rows": rows, "issues": issues,
                    "turns": len(record["turns"])}
    raise RuntimeError(f"math step: no JSON array after the retry turn ({workdir})")


# ---- the three wraps ------------------------------------------------------------

class Pretask:
    """Installs the wraps on a loaded run_unified (`install`); a call's arm
    travels in a thread-local, set by run_one_joint for the worker thread
    that runs it."""

    def __init__(self, ru, pack, pack_sha256, cutoffs, harness=None):
        self.ru, self.pack, self.pack_sha256, self.cutoffs = ru, pack, pack_sha256, cutoffs
        self._harness = harness
        self.local = threading.local()
        self.orig = {}

    def harness(self):
        if self._harness is None:
            from fri_forecaster import harness
            self._harness = harness
        return self._harness

    def install(self):
        for name in ("run_one_joint", "call_tools", "select_models"):
            self.orig[name] = getattr(self.ru, name)
            setattr(self.ru, name, getattr(self, name))
        return self

    def uninstall(self):
        for name, fn in self.orig.items():
            setattr(self.ru, name, fn)

    def run_one_joint(self, *args, **kwargs):
        orig = self.orig["run_one_joint"]
        a = inspect.signature(orig).bind(*args, **kwargs).arguments
        pre = a["condition"].get("_pretask")
        if not pre:
            rows = orig(*args, **kwargs)
            for r in rows:
                r["pretask"] = None
            return rows
        if (pre["pack"], pre["pack_sha256"]) != (self.pack["pack"], self.pack_sha256):
            raise ValueError(f"{a['condition']['id']}: pretask pack {pre['pack']} is not the loaded one")
        today = a.get("today") or datetime.now(timezone.utc).date()
        # One order per model and run, the same in both math arms.
        seed = f"{self.pack['pack']}|{a['run_id']}|{a.get('arm')}|{a['label']}"
        ctx = {"mode": pre["reveal"], "codes": ms.order(self.pack, seed), "run_date": today.isoformat(),
               "step": None, "math_steps": [], "usage": {}, "message": None, "forecast_workdirs": []}
        self.local.call = ctx
        try:
            rows = orig(*args, **kwargs)
        except Exception as e:
            self.transcript(a, ctx, error=e)
            raise
        finally:
            self.local.call = None
        step = ctx["step"]
        rec = ms.row_record(self.pack, self.pack_sha256, ctx["mode"], ctx["codes"], step["rows"], step["issues"],
                            prompt=step["prompt"], msg=ctx["message"], turns=step["turns"],
                            math_calls=len(ctx["math_steps"]), usage=ctx["usage"],
                            transcript=self.transcript(a, ctx, rows=rows))
        for i, r in enumerate(rows):
            r["pretask"] = rec if i == 0 else None
        return rows

    def call_tools(self, model, prompt, tools, final_tool, **kw):
        orig = self.orig["call_tools"]
        ctx = getattr(self.local, "call", None)
        if ctx is None:
            return orig(model, prompt, tools, final_tool, **kw)
        harness = self.harness()
        if ctx["step"] is None:     # once per call: a retried forecast continues the same math step
            record = {"workdir": os.path.join(pi_base(), f"math-{model.replace('/', '_')}-{time.time_ns()}"),
                      "turns": [], "error": None}
            ctx["math_steps"].append(record)
            usage = kw.get("usage")
            spent = {}
            try:
                ctx["step"] = math_step(harness, model, self.pack, ctx["codes"], ctx["run_date"],
                                        system=kw.get("system") or "", record=record, usage=spent)
            except Exception as e:
                record["error"] = f"{type(e).__name__}: {e}"
                raise
            finally:
                add_usage(ctx["usage"], spent)
                if usage is not None:   # the call's usage on its row: the math step's turns included
                    add_usage(usage, spent)
        step = ctx["step"]
        ctx["message"] = ms.message(self.pack, ctx["codes"], step["rows"], ctx["mode"])
        env = {**(kw.pop("env", None) or {}), SESSION_ENV: step["session"], PI_ENV: harness.DEFAULT_PI or ""}

        def run(**rk):
            res = harness.run(pi=WRAPPER, **rk)
            ctx["forecast_workdirs"].append(res["workdir"])
            return res

        return orig(model, ctx["message"] + "\n\n" + prompt, tools, final_tool, env=env, run=run, **kw)

    def select_models(self, model_set, args):
        orig = self.orig["select_models"]
        models, stamp = orig(model_set, argparse.Namespace(**{**vars(args), "smoke": False}))
        keep = []
        for label, m in models:
            ok, why = ms.eligible(m, self.pack["t0"], self.cutoffs)
            print(f"    {'ask ' if ok else 'SKIP'} {label}: {why}")
            if ok:
                keep.append((label, m))
        if not keep:
            sys.exit(f"no model of {model_set} may take the math pretask (T0 {self.pack['t0']}): "
                     "add sourced cutoffs to data/training_cutoffs.json")
        return (keep[:1] if args.smoke else keep), stamp

    def transcript(self, a, ctx, rows=None, error=None):
        """The private record of a math arm's call -> its path under the
        pretask folder (what the row's `pretask.transcript` names)."""
        run_id, label, cid = a["run_id"], a["label"], a["condition"]["id"]
        # A failed call has no rows: its id as run_one_joint would have made
        # it, with the scenario set, so AIRO's and welfare's never share one.
        call_id = rows[0]["call_id"] if rows else (
            f"{run_id}:{self.ru.set_slug(a['policies'])}:{a.get('arm')}:{label}"
            + (f":{cid}" if cid != self.ru.DEFAULT_VARIANT else ""))
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", call_id)
        rel = os.path.join(self.pack["pack"], "transcripts", re.sub(r"[^A-Za-z0-9._-]+", "_", run_id), name)
        base = ms.pretask_dir() / rel
        base.parent.mkdir(parents=True, exist_ok=True)
        step = ctx["step"]
        doc = {"call_id": call_id, "model": a["model_id"], "label": label, "arm": a.get("arm"),
               "experiment": a["experiment"], "scenario_set": self.ru.set_slug(a["policies"]),
               "condition": cid, "reveal": ctx["mode"], "pack": self.pack["pack"],
               "pack_sha256": self.pack_sha256, "run_date": ctx["run_date"], "order": ctx["codes"],
               "status": "failed" if error else "ok", "error": f"{type(error).__name__}: {error}" if error else None,
               "math_prompt": step["prompt"] if step else None, "math_steps": ctx["math_steps"],
               "forecasts": step["rows"] if step else None, "issues": step["issues"] if step else None,
               "relations": ms.relations(self.pack, step["rows"]) if step else None,
               "message": ctx["message"], "forecast_workdirs": ctx["forecast_workdirs"], "usage": ctx["usage"]}
        with open(f"{base}.json", "w") as f:
            f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        sessions = [(step["session"] if step else None, "math-session"),
                    (os.path.join(ctx["forecast_workdirs"][-1], "session.jsonl") if ctx["forecast_workdirs"]
                     else None, "session")]
        for src, tag in sessions:
            if src and os.path.exists(src):
                shutil.copyfile(src, f"{base}.{tag}.jsonl")
        return f"{rel}.json"


# ---- the run ------------------------------------------------------------------------

def dry_run(ru, pt, args, conditions, path, name=EXPERIMENT):
    """The series' prompt once (every arm asks the same), the math step and
    what precedes that prompt in each math arm, and who would be asked."""
    ru.run(args, {"name": name}, conditions[:1], path, False)
    if len(conditions) > 1:
        print(f"##### {', '.join(c['id'] for c in conditions[1:])}: the same prompt #####")
    math = [c for c in conditions if c.get("_pretask")]
    if math:
        pack, today = pt.pack, datetime.now(timezone.utc).date().isoformat()
        codes = ms.order(pack, f"{pack['pack']}|dry-run")
        st = ms.stats(pack)
        print(f"##### MATH STEP, before the prompt above in {', '.join(c['id'] for c in math)} (pack {pack['pack']}: "
              f"{st['n_items']} problems open on T0 {pack['t0']}, {st['n_solved']} solved by S "
              f"{pack['snapshot_date']}; no tools) #####")
        print(ms.math_prompt(pack, codes, today))
        print(f"##### ONCE, IF NO JSON ARRAY CAME BACK: {ms.RETRY_MSG} #####")
        rows, _, _ = ms.parse_answer("", codes, pack["t0"])
        for c in math:
            print(f"##### {c['id']}: THE USER TURN, THEN THE PROMPT ABOVE (shown for an answer with no "
                  "valid forecast) #####")
            print(ms.message(pack, codes, rows, c["_pretask"]["reveal"]))
    print("##### MODELS #####")
    pt.select_models(conditions[0]["model_set"], args)


def main(argv=None):
    ap = argparse.ArgumentParser(description="AIRO (or the welfare page) after a math-problem information "
                                             "shock (see this file's docstring)")
    ap.add_argument("--experiment", choices=list(BASES), default=DEFAULT_BASE,
                    help="the series whose baseline prompt every arm asks: airo (the risk questions, "
                         "default) or welfare (the benefit questions; rows under welfare-math-shock)")
    ap.add_argument("--arm", action="append", choices=list(ARMS), default=[],
                    help="run only this arm (repeatable; default: all three)")
    ap.add_argument("--models", help="comma-separated label filter")
    ap.add_argument("--smoke", action="store_true", help="one eligible model only (still paid)")
    ap.add_argument("--dry-run", action="store_true", help="print the prompts and the models; no model is called")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--retries", type=int, default=2,
                    help="re-ask a call whose math step failed or whose grid came back <90%% complete")
    ap.add_argument("--out", default=None, help="the unconditional slice (default: results/experiments/)")
    ap.add_argument("--conditional-out", default=None, help="every row (default: results/experiments/)")
    ap.add_argument("--allow-ungrounded", action="store_true", help="run without Tavily (rows say so)")
    args = ap.parse_args(argv)
    name = experiment_name(args.experiment)
    conditions = arm_conditions({a: ARMS[a] for a in (args.arm or ARMS)}, base=args.experiment)
    try:
        pack = ms.load_pack(PACK_ID, PACK_SHA256)
    except (OSError, ValueError) as e:
        sys.exit(str(e))
    ru = load_runner()
    if os.environ.get(ru.BLOCK_ENV):
        try:
            experiments.check_patterns(os.environ[ru.BLOCK_ENV])
        except re.error as e:
            sys.exit(f"{ru.BLOCK_ENV}: bad pattern: {e}")
    path = os.path.join(ROOT, conditions[0]["scenarios"])
    # As run_unified's main: the combined set refuses a stale ECI snapshot,
    # and the welfare set also a stale copy of the combined set.
    if not args.dry_run:
        ru.eci_preflight(path)
    ns = argparse.Namespace(out=args.out, conditional_out=args.conditional_out, dry_run=args.dry_run,
                            smoke=args.smoke, models=args.models, retries=args.retries, workers=args.workers,
                            news_snapshot=None, allow_ungrounded=args.allow_ungrounded)
    pt = Pretask(ru, pack, PACK_SHA256, ms.load_cutoffs()).install()
    if args.dry_run:
        return dry_run(ru, pt, ns, conditions, path, name)
    return ru.run(ns, {"name": name}, conditions, path, False)


if __name__ == "__main__":
    main()
