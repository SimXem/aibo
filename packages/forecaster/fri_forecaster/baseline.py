"""The Baseline condition: how a dashboard asks the panel.

One call per panel member (fri_forecaster.panel), with nothing in it but the
dashboard's own prompt:

  no system prompt      one space, because pi puts its own coding-assistant
                        prompt in place of an empty one.
  research is offered,  web_search and read_page (Tavily, tools.py), described
  never required        by what they do; no research floor, no coverage rule.
  no debrief            the call ends with the answer.
  reasoning at the top  panel.reasoning_for.
  a turn limit of 100   a runaway guard far above any call seen (64 turns); it
                        also keeps the harness's nudge on, so a reply cut at
                        the output limit with no submission does not end the
                        call.

This is AIRO's published condition `none` (its minimal instrument,
combined-v10, 2026-10-19: the prompt-variant experiments of 2026-10-14..19
found the instrument's guidance moved no headline forecast), labelled
"Baseline" on its dashboard. AIRO's runner reads the constants below, so the
two cannot drift; a dashboard that asks something other than probabilities
calls run() with its own answer schema.
"""
import copy
import os
import tempfile

from . import panel
from .tools import READ_PAGE_TOOL, WEB_SEARCH_TOOL

SYSTEM = " "
MAX_TURNS = 100
# A whole call, research included.
TIMEOUT = 3 * 3600
WEB_SEARCH = ("Search the web. Returns titled snippets with URLs and publication dates. "
              "recent_days limits results to the last N days.")
LOOP = {"min_research": 0, "floor_counts": "returned", "withhold_final": True,
        "warn_missing_keys": False, "max_turns": MAX_TURNS}


def research_tools():
    """web_search and read_page as the condition offers them: {name,
    description, parameters}. web_search loses `cause`, which serves only a
    coverage rule."""
    search = {k: copy.deepcopy(WEB_SEARCH_TOOL[k]) for k in ("name", "description", "parameters")}
    search["description"] = WEB_SEARCH
    search["parameters"]["properties"].pop("cause", None)
    read = {k: copy.deepcopy(READ_PAGE_TOOL[k]) for k in ("name", "description", "parameters")}
    return [search, read]


def run(model, prompt, *, workdir, cell_schema, key_fields, allowed_keys, submit_forecast, submit_cells=None,
        env=None, timeout=TIMEOUT, cwd=None, retries=0, pi=None, harness_run=None):
    """One Baseline call. `model` is a panel row's `model`; `submit_cells` and
    `submit_forecast` are the dashboard's two answer tools as {description,
    parameters} (the pieces along the way, and the final answer); the cells
    they carry are `cell_schema`, keyed by `key_fields`, and only
    `allowed_keys` are kept. A dashboard whose answer fits one call leaves
    `submit_cells` out, and a tool without `parameters` keeps the harness's
    own. `pi`: another pi than the harness's default. -> harness.run's result."""
    if harness_run is None:
        from . import harness
        harness_run = harness.run
    research = research_tools()
    specs = {**{t["name"]: t for t in research}, **({"submit_cells": submit_cells} if submit_cells else {}),
             "submit_forecast": submit_forecast}
    # pi writes its working directory into its system prompt: run it from an
    # empty directory whose name says nothing about the project.
    cwd = cwd or os.path.join(tempfile.gettempdir(), "w")
    os.makedirs(cwd, exist_ok=True)
    return harness_run(model=panel.pi_model(model), system=SYSTEM, prompt=prompt, workdir=workdir, cwd=cwd,
                       cell_schema=cell_schema, key_fields=list(key_fields), allowed_keys=list(allowed_keys),
                       tool_descriptions={n: s["description"] for n, s in specs.items()},
                       tool_parameters={n: s["parameters"] for n, s in specs.items() if s.get("parameters")},
                       research_tools=tuple(t["name"] for t in research), cells_tool=bool(submit_cells),
                       thinking=panel.reasoning_for(model), timeout=timeout, env=env, retries=retries,
                       **({"pi": pi} if pi else {}), **LOOP)
