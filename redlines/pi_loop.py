"""The loop every call runs through: FRI's agent-box (the `fri_forecaster`
package, packages/fri-forecaster). pi drives the model, and its extension
enforces the instrument's rules -- the research floor, the coverage rule, the
turn limit, the debrief and its validator -- with the loop options in
agent-box's README ("How it works"). The prompt, the tools and their schemas,
the cell cleaning and the rows are the instrument's own (code/run_unified.py).

The published loop since combined-v9 (2026-10-16), and the only one since
2026-10-22, when the litellm loop before it left the repo. The loop is a
condition's `harness` setting (redlines/experiments.py), so a condition with
another loop would be its own condition, with its own condition_sha256.

pi cannot force a tool choice, so the last turn ASKS for submit_forecast and
offers nothing else, and the output cap per turn is pi's for the model.

Needs fri-forecaster (`pip install -e ./packages/fri-forecaster`) and pi
0.99.2: FORECASTER_PI names its cli.js unless agent-box's own `npm ci` put it
in place.
"""
import json
import os
import tempfile
import time

from .llm import reasoning_for

# A whole call, research and debrief included.
DEFAULT_TIMEOUT = 3 * 3600


def pi_model(model):
    """The registry's id -> pi's. The registry's ids name OpenAI's Responses
    API by a path segment (`openai/responses/...`, the route the litellm loop
    took, and what rows and data/auto_models.json record); pi picks the API
    itself."""
    return model.replace("openai/responses/", "openai/", 1)


def call_tools(model, prompt, tools, final_tool, *, max_iters=6, system=None,
               min_evidence=0, usage=None, partial_tool=None, coverage=None, debrief=None,
               allowed_keys=None, env=None, timeout=None, run=None):
    """Let the model call `tools` to gather evidence, then submit its answer
    through `final_tool` (whose `forecasts` items are the cell schema).
    -> (answer_args, evidence); fills `usage` and `debrief` in place, feeds
    `partial_tool["fn"]` every piece in order, raises if the model never
    submits. `allowed_keys` ("qid|horizon") are the cells the call asks for,
    which pi's tools check pieces against. `env` is THIS call's environment
    for pi and its tool processes, over the process's own (agent-box
    `harness.run(env=...)`): the URL guard (redlines.tools.BLOCK_ENV) travels
    here, per call, never in os.environ, because the runner's workers run
    calls side by side (2026-10-19). `timeout` (seconds) caps the whole call,
    REDLINES_PI_TIMEOUT or three hours by default; `run` replaces
    fri_forecaster.harness.run (tests)."""
    if run is None:
        from fri_forecaster import harness
        run = harness.run
        # Linux hands one argument at most 128 KiB. agent-box passes the prompt
        # on stdin since 2026-10-19 (harness.PROMPT_ON_STDIN); an older one
        # passes it as an argument and would fail with E2BIG. Fail here, by
        # name, before any paid call.
        size = len(prompt.encode())
        if size > 131072 and not getattr(harness, "PROMPT_ON_STDIN", False):
            raise RuntimeError(f"the prompt is {size} bytes, past the 128 KiB one argument may hold, and this "
                               "agent-box passes it as one: install an agent-box that passes it on stdin")
    names = {t["name"] for t in tools}
    specs = [*tools, *([partial_tool] if partial_tool else []), final_tool]
    cell_items = (partial_tool or final_tool)["parameters"]["properties"]["forecasts"]["items"]
    base = os.environ.get("REDLINES_PI_DIR") or os.path.join(tempfile.gettempdir(), "redlines-pi")
    workdir = os.path.join(base, f"{model.replace('/', '_')}-{time.time_ns()}")
    loop = dict(min_research=min_evidence, floor_counts="returned", coverage=list(coverage or []) or None,
                withhold_final=True, warn_missing_keys=False, max_turns=max_iters)
    if debrief:
        loop["debrief"] = {"tool": {k: debrief["tool"][k] for k in ("name", "description", "parameters")},
                           "prompt": debrief["prompt"], "retries": int(debrief.get("retries", 1)),
                           **({"validator": debrief["validator"]} if debrief.get("validator") else {})}
    thinking = reasoning_for(model) or "off"
    # pi writes its working directory into the system prompt; run from the
    # checkout, that line names the project (".../airo/...") to the model --
    # a pointer to AIRO's own published forecasts. pi runs from an empty
    # directory with a name that says nothing (2026-10-15).
    cwd = os.environ.get("REDLINES_PI_CWD") or os.path.join(tempfile.gettempdir(), "w")
    os.makedirs(cwd, exist_ok=True)
    res = run(model=pi_model(model), system=system or "", prompt=prompt, workdir=workdir, cwd=cwd,
              cell_schema=cell_items, key_fields=["question_id", "horizon"],
              allowed_keys=list(allowed_keys or []),
              tool_descriptions={t["name"]: t.get("description", "") for t in specs},
              tool_parameters={t["name"]: t["parameters"] for t in specs},
              research_tools=tuple(n for n in ("web_search", "read_page") if n in names),
              cells_tool=bool(partial_tool), thinking=thinking,
              timeout=int(timeout or os.environ.get("REDLINES_PI_TIMEOUT", DEFAULT_TIMEOUT)),
              env={"PI_CODING_AGENT_DIR": os.environ.get("PI_CODING_AGENT_DIR") or os.path.join(base, "agent"),
                   **(env or {})},
              **loop)
    if usage is not None:
        u = res["usage"]
        for k in ("turns", "input_tokens", "output_tokens", "cached_tokens"):
            usage[k] = usage.get(k, 0) + (u.get(k) or 0)
        usage["cost_usd"] = round(usage.get("cost_usd", 0.0) + (u.get("cost_usd") or 0.0), 6)
        usage.update(reasoning_effort=thinking, reasoning_requested=thinking,
                     harness={"name": "pi", "pi_model": pi_model(model), "forced": res["forced"],
                              "rc": res["rc"], "seconds": round(res["seconds"])})
    if partial_tool:
        pieces = os.path.join(res["workdir"], "pieces.jsonl")
        for line in (open(pieces) if os.path.exists(pieces) else []):
            if line.strip():
                partial_tool["fn"](forecasts=json.loads(line).get("forecasts"))
    if debrief is not None and res.get("debrief") is not None:
        debrief.update({k: res["debrief"].get(k) for k in ("result", "complete", "attempts", "problems", "error")})
    if not res["answer"]:
        limit = f"within {max_iters + 2} turns" if max_iters else "before the run ended (no forced-turn cap)"
        raise RuntimeError(f"{final_tool['name']} not called {limit} (pi exit "
                           f"{res['rc']}); recorded usage={usage}; trace={res.get('trace')}")
    evidence = [{k: e.get(k) for k in ("tool", "args", "result")} for e in res["evidence"]]
    return res["answer"], evidence
