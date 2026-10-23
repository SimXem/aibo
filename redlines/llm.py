#!/usr/bin/env python3
"""The acquisition side's LLM plumbing: key loading, the reasoning level per
provider, and the coverage count the runners report.

The loop itself is pi's (redlines/pi_loop.py, agent-box). Until 2026-10-22
this module also held a litellm loop, the published loop before combined-v9;
it left with litellm, after litellm 1.107.0 on PyPI shipped a credential
stealer (2026-10-21). Every condition now runs through pi.

`load_keys()` reads an env file, which is what happens in production. Parsing
KEY=value needs no dependency, so importing this module -- which tests/ do, to
load the runners -- stays stdlib-only and the `python3 -m redlines build` path
keeps its no-third-party-deps promise.
"""
import os
from pathlib import Path

from .config import REPO_ROOT

# Every provider key the runners can use. TAVILY is the one that is load-bearing
# rather than optional: run_unified.py refuses to run without it rather than
# quietly publishing forecasts that the provenance line says were web-grounded
# but were not. It serves both grounding tools (web_search and read_page).
# METACULUS_API_KEY left the list on 2026-09-02 with the metaculus_lookup tool
# (redlines/tools.py says why); a value still in the env file is ignored.
PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                 "GOOGLE_API_KEY", "XAI_API_KEY", "TAVILY_API_KEY")

# REDLINES_ENV_FILE is EXCLUSIVE: naming a file means read that file and no
# other, so a run can be pinned to a known key set (and so tests are hermetic on
# a machine that has real keys lying around). With it unset, both defaults are
# read in order and the FIRST value found wins for a given key. A variable
# already in the environment always beats every file, so
# `TAVILY_API_KEY=... python code/run_unified.py` works with no file at all --
# and so does cron_run.sh, which sources the env file before exec'ing us.
# The defaults: ~/.config/redlines/env (the cron box's, mode 600), then the
# checkout's own .env.
def _env_paths():
    explicit = os.environ.get("REDLINES_ENV_FILE")
    if explicit:
        return [Path(explicit).expanduser()]
    return [Path.home() / ".config" / "redlines" / "env", REPO_ROOT / ".env"]


def _parse_env(path):
    """KEY=value lines -> dict. Tolerates `export ` prefixes, blank lines, #
    comments, and surrounding quotes -- the same shapes `set -a; . file` accepts,
    since the cron box sources the very same file with the shell."""
    out = {}
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def load_keys():
    """Populate os.environ with provider API keys from the first env file that
    has them. Never overrides a variable that is already set.

    Best-effort by design: a missing file or a missing provider just means that
    provider stays unconfigured, and an Anthropic-only run still works. Callers
    that actually need a specific key check for it themselves after calling this
    (run_unified.py refuses to start without TAVILY_API_KEY). Returns the sorted
    names of the keys that ARE configured afterwards, for logging.
    """
    for path in _env_paths():
        values = _parse_env(path)
        for k in PROVIDER_KEYS:
            if values.get(k):
                os.environ.setdefault(k, values[k])
    return sorted(k for k in PROVIDER_KEYS if os.environ.get(k))


# Reasoning level, per provider family: pi's `--thinking` for the model.
# Project lead, 2026-09-02: reasoning should be at its maximum. The top rung
# is spelled differently per family: Fable 5 / Opus 5 take "max"; GPT-5.5 Pro
# and GPT-5.6 Sol take "xhigh" (probed on the box 2026-09-02). Anthropic's
# effort also governs how many tool calls the model makes, which is the
# point. REDLINES_REASONING overrides for an experiment ("none" turns
# thinking off).
REASONING = {"anthropic": "max", "openai": "xhigh"}
REASONING_DEFAULT = "high"


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
