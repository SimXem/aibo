"""Experiments and the conditions they run.

A CONDITION is one configured way of running the instrument: the scenario
set it asks, the prompt variant, the instrument (minimal or standard), the
loop (harness), the models, a URL guard, and whether its rows publish. An
EXPERIMENT is a set of conditions with shared config, one TOML file under
experiments/: its top-level settings are every condition's, and a
condition's own table overrides any of them (2026-10-21; before that a
scenario set declared the variants it was asked under, and the shadow loop
and the axes instruments were each run their own way).

`pooled` names the conditions whose mean is each model's published number.
They run together: the mean is taken over one day's calls
(redlines.runlog.pool). A published condition outside `pooled` enters no
number and is never shown (2026-10-21); its rows stay in the run log and the
download. An unpublished one writes to results/experiments/ and nothing on
the page reads it.

A condition's CADENCE says when the cron runs it (2026-10-21): a list of
weekdays, UTC ("wed"), any of which may be an ordinal one ("1st wed", the
first Wednesday of the month), or "manual" for only when named by hand.
code/cron_run.sh asks `python -m redlines.experiments due` what is due
today and runs each group. The pooled conditions share one cadence, and a
published condition outside them runs only on days they run (a rule from
when the Timeline drew its line beside theirs, until 2026-10-21).

code/run_unified.py --experiment NAME runs an experiment's conditions (all
of them, or those named with --condition), whatever their cadence. Every row
a call writes carries the experiment's name, the condition's id, and condition_sha256, a hash of
the condition's settings, so two rows asked under different settings never
pass for the same condition.

Stdlib only (tomllib), like the rest of the build stage: the views read
experiments/airo.toml for what the published series asks.
"""
import argparse
import hashlib
import json
import re
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import REPO_ROOT
from .registry import DEFAULT_MODEL_SET

EXPERIMENTS_DIR = REPO_ROOT / "experiments"
# The experiment whose pooled conditions are the dashboard's series.
PUBLISHED = "airo"

# PROMPT VARIANTS (Jason's five, 2026-10-14). Each is the same instrument with
# one added instruction, verbatim. `none` adds nothing. A condition names one
# (`variant`); the runner puts its text into the prompt (code/run_unified.py
# minimal_joint_prompt, apply_variant), and the Timeline shows it beside the
# condition's line.
VARIANTS = {
    "none": None,
    "independent": (
        "Try to make your own forecasts. Do not take into account external surveys "
        "assessing extinction or catastrophic risk, or other probabilities given by "
        "prominent figures. The goal is to reach your own independent conclusion."),
    "recent": (
        "If you search external information, focus on information that arrived within "
        "the past year, and weight more heavily sources that are more up to date about "
        "recent developments."),
    "critical": (
        "Evaluate existing information critically. If you take into account forecasts by "
        "specific people or surveyed groups, consider their recent and historical "
        "forecasting accuracy, as well as the information available to the forecasters "
        "when they made their forecasts."),
    "two-step": (
        "Proceed in two steps. First, make the best predictions you can about model "
        "capability progress over the relevant time frame, via human generated "
        "improvement or recursive self-improvement. Consider the distribution, not only "
        "the modal outcome. Then, given possible model capabilities, evaluate the risk "
        "posed and put these pieces together."),
    # THE SIXTH (2026-10-19 evening): the AI-forecast ban, the `both` arm of the
    # anchor-guard experiment of 2026-10-16 (results/experiments/anchor-guard-
    # 2026-10-16, where it was a system-prompt addendum; the minimal instrument
    # has no system prompt, so it goes where a variant's text goes). The airo
    # experiment pairs it with agent-box's URL guard against AIRO's own pages,
    # passed to that condition's calls alone.
    "ai-banned": (
        "Forecasts produced by AI systems, including any automated forecasting "
        "dashboard or model ensemble, carry no information beyond their inputs. Do not "
        "consult them or use them as evidence."),
}
DEFAULT_VARIANT = "none"

INSTRUMENTS = ("standard", "minimal")
# The loop: pi (agent-box), the only one since litellm left on 2026-10-22.
# Still a setting, and still hashed, so a condition records the loop its
# calls ran through.
HARNESSES = ("pi",)
# Every setting a condition has, and its value when neither the experiment
# nor the condition sets it.
DEFAULTS = {
    "scenarios": None,                # the scenario set, a path from the repo root (required)
    "variant": DEFAULT_VARIANT,       # the instruction VARIANTS adds to the prompt
    "instrument": "standard",         # "minimal": the guidance cut (code/run_unified.py)
    "harness": "pi",                  # the loop (redlines.pi_loop)
    "model_set": DEFAULT_MODEL_SET,   # redlines.registry.MODEL_SETS
    "repeats": 1,                     # calls per model per run
    "url_block_patterns": None,       # agent-box's URL guard for these calls alone
    "news_cache": False,             # frozen weekly news input + AI-forecast ban (unpublished shadow)
    "max_turns": None,               # None: instrument default; 0: no forced-turn submission

    "publish": False,                 # rows go to the scenario set's own logs, which the page reads
    "cadence": "manual",              # when the cron runs it: weekdays (UTC), or "manual"
}
# Settings that say where a condition's rows go, how many calls it makes or
# when, not what a call is asked: outside the hash.
UNHASHED = ("publish", "repeats", "cadence")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ORDINALS = ("1st", "2nd", "3rd", "4th", "5th")


def path_of(name):
    """An experiment's name (experiments/<name>.toml) or a path to a TOML file."""
    p = Path(name)
    return p if p.suffix == ".toml" else EXPERIMENTS_DIR / f"{name}.toml"


def names():
    return sorted(p.stem for p in EXPERIMENTS_DIR.glob("*.toml"))


def load(name):
    """-> {"name", "path", "pooled": [ids], "conditions": {id: condition}}.

    A condition is a dict of every setting in DEFAULTS, resolved (the
    condition's own table over the experiment's over the defaults), plus
    `id`, `pooled` (bool) and `sha256`. Conditions keep the file's order.
    Raises ValueError on anything the runner could not run as written.
    """
    path = path_of(name)
    raw = tomllib.loads(path.read_text())
    tables = raw.pop("conditions", None) or {}
    pooled = raw.pop("pooled", [])
    shared = _settings(raw, path.name)
    if not tables:
        raise ValueError(f"{path.name}: no [conditions.<id>] tables")
    stray = [c for c in pooled if c not in tables]
    if stray:
        raise ValueError(f"{path.name}: pooled names {stray}, which are not conditions")
    conditions = {}
    for cid, own in tables.items():
        where = f"{path.name} [conditions.{cid}]"
        s = {**DEFAULTS, **shared, **_settings(own, where)}
        _check(s, cid in pooled, where)
        conditions[cid] = {"id": cid, **s, "pooled": cid in pooled, "sha256": condition_sha256(s)}
    _check_cadences(conditions, path.name)
    return {"name": path.stem, "path": path, "pooled": list(pooled), "conditions": conditions}


def condition_sha256(settings):
    """A hash of what a condition's calls are asked: every setting but UNHASHED."""
    keep = {k: settings[k] for k in DEFAULTS if k not in UNHASHED}
    # An opt-in extension must not change existing published condition hashes.
    if not keep["news_cache"]:
        del keep["news_cache"]
    if keep["max_turns"] is None:
        del keep["max_turns"]
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def baseline(experiment):
    """The condition that adds no instruction (variant `none`): the prompt the
    page shows as the one the series is asked."""
    return next(c for c in experiment["conditions"].values() if c["variant"] == DEFAULT_VARIANT)


def is_due(condition, day):
    """Does the cron run this condition on `day` (a date, UTC)?"""
    if condition["cadence"] == "manual":
        return False
    weekday = WEEKDAYS[day.weekday()]
    return any(e == weekday or e == f"{ORDINALS[(day.day - 1) // 7]} {weekday}"
               for e in condition["cadence"])


def due(day=None, named=None):
    """What to run: [(experiment, publish, [condition ids])], one entry per
    group run_unified runs together (one scenario set, one destination).
    With `named`, every condition of those experiments, whatever their
    cadence (a run by hand); else every condition due on `day` (default
    today, UTC), across experiments."""
    day = day or datetime.now(timezone.utc).date()
    out = []
    for name in named or names():
        exp = load(name)
        groups = {}
        for c in exp["conditions"].values():
            if named or is_due(c, day):
                groups.setdefault((c["scenarios"], c["publish"]), []).append(c["id"])
        out += [(exp["name"], publish, ids) for (_, publish), ids in groups.items()]
    return out


def check_patterns(raw):
    """A bad URL-guard pattern fails before the first paid call, not inside it
    (the split is redlines.tools.blocked_patterns's: newlines or commas)."""
    for p in re.split(r"[\n,]", raw or ""):
        if p.strip():
            re.compile(p.strip(), re.I)


def _settings(table, where):
    unknown = sorted(set(table) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"{where}: unknown setting(s) {unknown}; a condition has {sorted(DEFAULTS)}")
    return dict(table)


def _check(s, pooled, where):
    if s["max_turns"] is not None and (type(s["max_turns"]) is not int or s["max_turns"] < 0
                                      or s["harness"] != "pi"):
        raise ValueError(f"{where}: max_turns must be a nonnegative integer for pi")
    if not isinstance(s["news_cache"], bool):
        raise ValueError(f"{where}: news_cache must be boolean")
    if s["news_cache"] and (s["harness"] != "pi" or s["instrument"] != "minimal"
                           or s["publish"] or pooled
                           or s["variant"] != "recent" or not s["url_block_patterns"]):
        raise ValueError(f"{where}: news_cache requires unpooled unpublished minimal/pi Recent with a URL guard")
    if not s["scenarios"]:
        raise ValueError(f"{where}: no scenario set (`scenarios`)")
    if s["variant"] not in VARIANTS:
        raise ValueError(f"{where}: unknown variant {s['variant']!r}; choose from {sorted(VARIANTS)}")
    if s["instrument"] not in INSTRUMENTS:
        raise ValueError(f"{where}: instrument {s['instrument']!r} is not one of {INSTRUMENTS}")
    if s["harness"] not in HARNESSES:
        raise ValueError(f"{where}: harness {s['harness']!r} is not one of {HARNESSES}")
    if s["url_block_patterns"]:
        try:
            check_patterns(s["url_block_patterns"])
        except re.error as e:
            raise ValueError(f"{where}: bad url_block_patterns: {e}") from None
    if not isinstance(s["repeats"], int) or s["repeats"] < 1:
        raise ValueError(f"{where}: repeats must be a whole number >= 1")
    if pooled and not s["publish"]:
        raise ValueError(f"{where}: a pooled condition publishes (publish = true)")
    c = s["cadence"]
    if c != "manual" and not (isinstance(c, list) and c and all(_entry(e) for e in c)):
        raise ValueError(f"{where}: cadence {c!r} is not \"manual\" or a list of weekdays "
                         f"({', '.join(WEEKDAYS)}), each may be ordinal (\"1st wed\")")


def _entry(e):
    parts = e.split() if isinstance(e, str) else []
    return (len(parts) == 1 and parts[0] in WEEKDAYS) or \
        (len(parts) == 2 and parts[0] in ORDINALS and parts[1] in WEEKDAYS)


def _check_cadences(conditions, where):
    """The pooled conditions share one cadence (a day's mean is over all of
    them), and a published condition outside them runs on no day they do not
    (a rule from when the Timeline drew its line beside theirs). Run by hand,
    anything goes."""
    pooled = [c for c in conditions.values() if c["pooled"]]
    if not pooled:
        return
    cadences = {json.dumps(c["cadence"]) for c in pooled}
    if len(cadences) > 1:
        raise ValueError(f"{where}: the pooled conditions run on different cadences {sorted(cadences)}")
    # A year holds every (ordinal, weekday) a cadence can name.
    year = [date(2026, 1, 1) + timedelta(days=i) for i in range(365)]
    for c in conditions.values():
        if c["pooled"] or not c["publish"]:
            continue
        if any(is_due(c, d) and not is_due(pooled[0], d) for d in year):
            raise ValueError(f"{where} [conditions.{c['id']}]: cadence {c['cadence']} runs on days "
                             f"the pooled conditions ({pooled[0]['cadence']}) do not, and "
                             "a published condition runs only beside them")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m redlines.experiments")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("due", help="what to run: one line per group, "
                                   "'<experiment> <publish|aside> <condition>...'")
    d.add_argument("names", nargs="*", help="these experiments, every condition (default: what is due)")
    d.add_argument("--date", type=date.fromisoformat, help="as of this UTC date (default: today)")
    args = ap.parse_args(argv)
    for name, publish, ids in due(args.date, args.names):
        print(name, "publish" if publish else "aside", *ids)


if __name__ == "__main__":
    main()
