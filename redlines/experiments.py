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
(redlines.runlog.pool). A published condition outside `pooled` is drawn as
its own line and enters no number; an unpublished one writes to
results/experiments/ and nothing on the page reads it.

code/run_unified.py --experiment NAME runs an experiment's conditions (all
of them, or those named with --condition). Every row a call writes carries
the experiment's name, the condition's id, and condition_sha256, a hash of
the condition's settings, so two rows asked under different settings never
pass for the same condition.

Stdlib only (tomllib), like the rest of the build stage: the views read
experiments/airo.toml for what the published series asks.
"""
import hashlib
import json
import re
import tomllib
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
HARNESSES = ("litellm", "pi")
# Every setting a condition has, and its value when neither the experiment
# nor the condition sets it.
DEFAULTS = {
    "scenarios": None,                # the scenario set, a path from the repo root (required)
    "variant": DEFAULT_VARIANT,       # the instruction VARIANTS adds to the prompt
    "instrument": "standard",         # "minimal": the guidance cut (code/run_unified.py)
    "harness": "litellm",             # the loop: litellm (redlines.llm) or pi (agent-box)
    "model_set": DEFAULT_MODEL_SET,   # redlines.registry.MODEL_SETS
    "repeats": 1,                     # calls per model per run
    "url_block_patterns": None,       # agent-box's URL guard for these calls alone (pi only)
    "publish": False,                 # rows go to the scenario set's own logs, which the page reads
}
# Settings that say where a condition's rows go or how many calls it makes,
# not what a call is asked: outside the hash.
UNHASHED = ("publish", "repeats")


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
    return {"name": path.stem, "path": path, "pooled": list(pooled), "conditions": conditions}


def condition_sha256(settings):
    """A hash of what a condition's calls are asked: every setting but UNHASHED."""
    keep = {k: settings[k] for k in DEFAULTS if k not in UNHASHED}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def baseline(experiment):
    """The condition that adds no instruction (variant `none`): the prompt the
    page shows as the one the series is asked."""
    return next(c for c in experiment["conditions"].values() if c["variant"] == DEFAULT_VARIANT)


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
    if not s["scenarios"]:
        raise ValueError(f"{where}: no scenario set (`scenarios`)")
    if s["variant"] not in VARIANTS:
        raise ValueError(f"{where}: unknown variant {s['variant']!r}; choose from {sorted(VARIANTS)}")
    if s["instrument"] not in INSTRUMENTS:
        raise ValueError(f"{where}: instrument {s['instrument']!r} is not one of {INSTRUMENTS}")
    if s["harness"] not in HARNESSES:
        raise ValueError(f"{where}: harness {s['harness']!r} is not one of {HARNESSES}")
    if s["instrument"] == "minimal" and s["harness"] != "pi":
        raise ValueError(f"{where}: the minimal instrument runs through pi")
    if s["url_block_patterns"]:
        if s["harness"] != "pi":
            raise ValueError(f"{where}: a URL guard travels per call through pi only")
        try:
            check_patterns(s["url_block_patterns"])
        except re.error as e:
            raise ValueError(f"{where}: bad url_block_patterns: {e}") from None
    if not isinstance(s["repeats"], int) or s["repeats"] < 1:
        raise ValueError(f"{where}: repeats must be a whole number >= 1")
    if pooled and not s["publish"]:
        raise ValueError(f"{where}: a pooled condition publishes (publish = true)")
