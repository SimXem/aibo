#!/usr/bin/env python3
"""The acquisition side's LLM plumbing: key loading, the reasoning level per
provider, and the coverage count the runners report.

The loop itself is pi's (redlines/pi_loop.py, agent-box). Until 2026-10-22
this module also held a litellm loop, the published loop before combined-v9;
it left with litellm, after litellm 1.107.0 on PyPI shipped a credential
stealer (2026-10-21). Every condition now runs through pi.

`load_keys()` reads the installation's keys file, which is what happens in
production. The engine's parser is stdlib-only, so importing this module --
which tests/ do, to load the runners -- needs no third-party dependency.
"""
import os

# The keys come from the installation's one keys file, through the engine
# (fri_forecaster.keys: $FORECASTER_ENV_FILE, else ~/.config/fri-forecaster/env),
# as every other project's do. TAVILY is the one that is load-bearing rather
# than optional: run_unified.py refuses to run without it rather than quietly
# publishing forecasts that the provenance line says were web-grounded but were
# not. It serves both grounding tools (web_search and read_page).
from . import eci as _eci  # noqa: E402,F401  (puts packages/forecaster on the path in a bare checkout)
from fri_forecaster import keys as _keys  # noqa: E402

PROVIDER_KEYS = _keys.KEYS


def load_keys():
    """Populate os.environ with the model and search keys from the keys file.
    Never overrides a variable that is already set.

    Best-effort by design: a missing file or a missing provider just means that
    provider stays unconfigured, and an Anthropic-only run still works. Callers
    that actually need a specific key check for it themselves after calling this
    (run_unified.py refuses to start without TAVILY_API_KEY). Returns the sorted
    names of the keys that ARE configured afterwards, for logging.
    """
    return _keys.load_keys()


# Reasoning level, per provider family: pi's `--thinking` for the model.
# Project lead, 2026-09-02: reasoning should be at its maximum. The top rung
# is spelled differently per family: Fable 5 / Opus 5 take "max"; GPT-5.5 Pro
# and GPT-5.6 Sol take "xhigh" (probed on the box 2026-09-02). Anthropic's
# effort also governs how many tool calls the model makes, which is the
# point. REDLINES_REASONING overrides for an experiment ("none" turns
# thinking off).
# The table is the shared panel's (fri_forecaster.panel, since 2026-11-11).
from fri_forecaster.panel import REASONING, REASONING_DEFAULT  # noqa: E402


def reasoning_for(model):
    """The reasoning level for `model`, or None for none."""
    override = os.environ.get("REDLINES_REASONING")
    if override:
        return None if override.lower() == "none" else override
    return REASONING.get(model.split("/", 1)[0], REASONING_DEFAULT)


def research_coverage(evidence):
    """{cause: n} over recorded evidence: how many recent-window searches
    (args carrying `cause` and a truthy `recent_days`) each question group
    got, in first-seen order. What the loop's coverage rule counts."""
    out = {}
    for e in evidence or []:
        args = e.get("args")
        if isinstance(args, dict) and args.get("cause") is not None and args.get("recent_days"):
            out[args["cause"]] = out.get(args["cause"], 0) + 1
    return out
