"""FRI Forecaster: one agentic forecasting call through pi.

Shared by AIRO (code/pi_harness/run_pi.py) and the ForecastBench driver. The caller supplies the prompt, the
shape of a forecast cell and which cells it wants; this module runs pi with
pi_tools.ts, then folds pi's JSON event stream into evidence and
usage and merges the submitted pieces with the final answer.

    res = run(model="openai/gpt-6-astra", system=SYS, prompt=P, workdir=W,
              cell_schema={...}, key_fields=["id", "resolution_date"],
              allowed_keys=["q1|2026-10-18", ...])
    res["cells"]    # {key: cell}, pieces first, final.json's cells override
    res["answer"]   # the submit_forecast arguments (rationale, key_sources, ...)

Nothing here knows about any one caller's questions or rows.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from fri_forecaster.keys import KEY_FOR

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "pi_tools.ts")
TOOL_CLI = os.path.join(HERE, "tool_cli.py")
RESEARCH_TOOLS = ("web_search", "read_page")
# PINNED: pi 0.99.2, which knows the panel models and whose extension API
# pi_tools.ts is written against; older pis know none of the panel models and
# load a different typebox. package.json pins it: `npm ci` in a checkout puts
# it where REPO_PI looks. Override with FORECASTER_PI (a `pi` executable or a
# cli.js run under node). Never a `pi` from PATH: it is rarely this version.
PINNED_PI_VERSION = "0.99.2"
REPO_PI = os.path.join(os.path.dirname(HERE), "node_modules", "@earendil-works", "pi-coding-agent",
                       "dist", "bundle", "cli.js")
DEFAULT_PI = os.environ.get("FORECASTER_PI") or (REPO_PI if os.path.exists(REPO_PI) else None)
# Isolation: no built-in tools, no discovered extensions/skills/prompt
# templates, and no AGENTS.md/CLAUDE.md from the cwd or its parents, so the
# saved system.txt + prompt.txt are the whole prompt.
ISOLATION = ["--no-builtin-tools", "--no-session", "--no-extensions", "--no-skills",
             "--no-prompt-templates", "--no-context-files"]
# Billing: API keys only. pi takes a bearer or OAuth token from the environment
# over ANTHROPIC_API_KEY, and a `pi /login` leaves OAuth credentials in its
# agent directory (~/.pi/agent by default), which it also prefers -- a personal
# Claude subscription paid for a run that way (2026-10-15). So pi runs without
# these variables, in the agent directory the caller names (PI_CODING_AGENT_DIR)
# or an empty one of ours, and never in one that holds a login.
LOGIN_TOKENS = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN")
AGENT_DIR = os.path.join(tempfile.gettempdir(), "fri-forecaster-agent")
# A provider error ends pi's turn with exit 0 and no cells (Anthropic's
# "out of extra usage" 400 on bursts, 2026-10-14). Retries wait this many
# seconds times the attempt number.
RETRY_BACKOFF = 20


def key_of(cell, key_fields):
    return "|".join(str(cell.get(k)) for k in key_fields)


# The loop's optional settings (pi_tools.ts's header says what each does).
# Unset, a call runs the default loop: the ForecastBench driver's.
LOOP_OPTIONS = ("floor_counts", "coverage", "withhold_final", "warn_missing_keys", "max_turns", "debrief")


def write_spec(workdir, *, cell_schema, key_fields, allowed_keys, tool_descriptions,
               min_research=0, research_tools=RESEARCH_TOOLS, final_extra=None, cells_tool=True,
               tool_parameters=None, **loop):
    """spec.json for pi_tools.ts. tool_descriptions: {tool name: description}
    for every tool offered (research tools, submit_forecast, and submit_cells
    unless cells_tool is False); tool_parameters: {tool name: JSON schema} to
    replace a tool's built-in parameters; `loop`: LOOP_OPTIONS."""
    unknown = set(loop) - set(LOOP_OPTIONS)
    if unknown:
        raise TypeError(f"unknown loop options {sorted(unknown)}; have {LOOP_OPTIONS}")
    tools = {name: {"description": tool_descriptions[name],
                    **({"parameters": tool_parameters[name]} if name in (tool_parameters or {}) else {})}
             for name in list(research_tools) + (["submit_cells"] if cells_tool else []) + ["submit_forecast"]}
    spec = {"tool_cli": TOOL_CLI, "research_tools": list(research_tools), "min_research": min_research,
            "tools": tools, "cell_schema": cell_schema, "key_fields": list(key_fields),
            "allowed_keys": list(allowed_keys), "final_extra": final_extra or {},
            **{k: v for k, v in loop.items() if v is not None}}
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "spec.json"), "w") as f:
        json.dump(spec, f, indent=1)
    return spec


def pi_argv(pi=DEFAULT_PI):
    if not pi:
        raise RuntimeError(f"no pi: run `npm ci` in the fri-forecaster checkout, or set FORECASTER_PI "
                           f"to a pi {PINNED_PI_VERSION} executable or cli.js")
    return ["node", pi] if pi.endswith(".js") else [pi]


def pi_version(pi=DEFAULT_PI):
    try:
        return subprocess.run(pi_argv(pi) + ["--version"], capture_output=True, text=True,
                              timeout=60).stdout.strip().splitlines()[-1]
    except Exception:
        return None


# The prompt goes to pi on STDIN, never as an argument. Linux hands one
# argument at most 128 KiB (MAX_ARG_STRLEN), and AIRO's joint prompt passed
# that on 2026-10-19; pi reads piped stdin as its first prompt, verbatim but
# for surrounding whitespace (it trims), so what the model reads and prompt.txt
# differ by at most a trailing newline. Callers can check this flag before
# sending a prompt that would not fit an argument. (The same cap is why a
# debrief validator's value reaches tool_cli on stdin: pi_tools.ts.)
PROMPT_ON_STDIN = True


def pi_command(model, system, *, thinking="high", pi=DEFAULT_PI):
    return pi_argv(pi) + ["-p", "--mode", "json", *ISOLATION, "-e", EXT,
                          "--model", model, "--thinking", thinking, "--system-prompt", system]


def new_attempt_dir(workdir):
    """A fresh workdir/attempt-N, so a retry never reads an earlier attempt's
    pieces.jsonl or final.json."""
    os.makedirs(workdir, exist_ok=True)
    n = 1 + max([int(d.split("-", 1)[1]) for d in os.listdir(workdir)
                 if d.startswith("attempt-") and d.split("-", 1)[1].isdigit()] or [0])
    path = os.path.join(workdir, f"attempt-{n}")
    os.makedirs(path)
    return path


def parse_events(lines):
    """pi's JSON event stream -> (evidence, usage). usage has turns, tokens, cost.
    pi (0.99) puts a tool's args on tool_execution_start and its result on
    tool_execution_end: they are joined by toolCallId."""
    args_by_id = {}
    evidence, turns = [], 0
    usage = {"turns": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0, "api_error": None}
    for line in lines:
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "tool_execution_start":
            args_by_id[e.get("toolCallId")] = e.get("args")
        if e.get("type") == "tool_execution_end" and e.get("toolName") in RESEARCH_TOOLS:
            res = e.get("result")
            det = (res or {}).get("details") if isinstance(res, dict) else None
            result = det if det is not None else res
            evidence.append({"tool": e["toolName"],
                             "args": e.get("args") if e.get("args") is not None else args_by_id.get(e.get("toolCallId")),
                             "result": result,
                             "error": (result or {}).get("error") if isinstance(result, dict) else None})
        if e.get("type") == "message_end" and (e.get("message") or {}).get("role") == "assistant":
            u = (e["message"].get("usage") or {})
            turns += 1
            usage["input_tokens"] += int(u.get("input") or 0)
            usage["output_tokens"] += int(u.get("output") or 0)
            usage["cached_tokens"] += int(u.get("cacheRead") or 0)
            usage["cost_usd"] = round(usage["cost_usd"] + float(((u.get("cost") or {}).get("total")) or 0), 6)
            if e["message"].get("stopReason") == "error":
                usage["api_error"] = (e["message"].get("errorMessage") or "error")[:300]
    usage["turns"] = turns
    usage["research_ok"] = sum(1 for ev in evidence if not ev["error"])
    usage["research_failed"] = sum(1 for ev in evidence if ev["error"])
    return evidence, usage


def collect(workdir, key_fields, allowed_keys):
    """pieces.jsonl + final.json -> (cells, answer, delivery). Only allowed
    keys are kept; the final answer's cells override the pieces'."""
    allowed = set(allowed_keys)
    received, delivery = {}, {"cells_calls": 0, "cells_in_pieces": 0, "cells_in_final": 0}
    pieces = os.path.join(workdir, "pieces.jsonl")
    if os.path.exists(pieces):
        for line in open(pieces):
            if not line.strip():
                continue
            p = json.loads(line)
            delivery["cells_calls"] += 1
            for f in p.get("forecasts") or []:
                if isinstance(f, dict) and key_of(f, key_fields) in allowed:
                    received[key_of(f, key_fields)] = f
    delivery["cells_in_pieces"] = len(received)
    final_path = os.path.join(workdir, "final.json")
    answer = json.load(open(final_path))["answer"] if os.path.exists(final_path) else {}
    for f in answer.get("forecasts") or []:
        if isinstance(f, dict) and key_of(f, key_fields) in allowed:
            received[key_of(f, key_fields)] = f
            delivery["cells_in_final"] += 1
    return received, answer, delivery


def pi_env(model, env=None):
    """pi's environment: the process's, the caller's `env` over it, then the
    billing rules above: no login token, the model's provider key present
    (keys.KEY_FOR), an agent directory without a login."""
    full = dict(os.environ, **(env or {}))
    for k in LOGIN_TOKENS:
        full.pop(k, None)
    key = KEY_FOR.get(model.partition("/")[0])
    if key and not full.get(key):
        raise RuntimeError(f"{model}: {key} is not set; pi is billed to API keys only (keys.load_keys reads the env file)")
    agent = full.get("PI_CODING_AGENT_DIR") or AGENT_DIR
    os.makedirs(agent, exist_ok=True)
    auth = read_json(os.path.join(agent, "auth.json")) or {}
    logins = sorted(p for p, v in auth.items() if isinstance(v, dict) and v.get("type") == "oauth")
    if logins:
        raise RuntimeError(f"{agent}/auth.json holds a login for {', '.join(logins)}; pi is billed to API keys only: "
                           f"point PI_CODING_AGENT_DIR at a directory without one")
    full["PI_CODING_AGENT_DIR"] = agent
    return full


def run(*, model, system, prompt, workdir, cell_schema, key_fields, allowed_keys, tool_descriptions,
        min_research=0, research_tools=RESEARCH_TOOLS, final_extra=None, cells_tool=True,
        thinking="high", pi=DEFAULT_PI, cwd=None, env=None, timeout=None, tool_parameters=None,
        retries=0, **loop):
    """One pi call, in a fresh workdir/attempt-N (returned as "workdir").
    Writes spec.json, prompt.txt, system.txt, events.jsonl, stderr.txt there
    (and pi_tools.ts writes pieces.jsonl, final.json, debrief.json). pi's
    environment is pi_env's: billed to API keys only. A call that ends in a
    provider error with no cells (usage["api_error"]) is made again, up to
    `retries` times, each in its own attempt folder, RETRY_BACKOFF seconds
    times the attempt number apart."""
    full_env = pi_env(model, env)
    for attempt in range(retries + 1):
        res = _call(model=model, system=system, prompt=prompt, workdir=workdir, cell_schema=cell_schema,
                    key_fields=key_fields, allowed_keys=allowed_keys, tool_descriptions=tool_descriptions,
                    min_research=min_research, research_tools=research_tools, final_extra=final_extra,
                    cells_tool=cells_tool, thinking=thinking, pi=pi, cwd=cwd, env=full_env, timeout=timeout,
                    tool_parameters=tool_parameters, **loop)
        if res["cells"] or not res["usage"]["api_error"] or attempt == retries:
            return res
        time.sleep(RETRY_BACKOFF * (attempt + 1))


def _call(*, model, system, prompt, workdir, cell_schema, key_fields, allowed_keys, tool_descriptions,
          min_research, research_tools, final_extra, cells_tool, thinking, pi, cwd, env, timeout,
          tool_parameters, **loop):
    workdir = new_attempt_dir(workdir)
    write_spec(workdir, cell_schema=cell_schema, key_fields=key_fields, allowed_keys=allowed_keys,
               tool_descriptions=tool_descriptions, min_research=min_research,
               research_tools=research_tools, final_extra=final_extra, cells_tool=cells_tool,
               tool_parameters=tool_parameters, **loop)
    open(os.path.join(workdir, "prompt.txt"), "w").write(prompt)
    open(os.path.join(workdir, "system.txt"), "w").write(system)
    cmd = pi_command(model, system, thinking=thinking, pi=pi)
    full_env = dict(env, FORECASTER_OUT=workdir, FORECASTER_PY=sys.executable)
    t0 = datetime.now(timezone.utc)
    events_path = os.path.join(workdir, "events.jsonl")
    with open(events_path, "w") as ev, open(os.path.join(workdir, "stderr.txt"), "w") as err:
        try:
            rc = subprocess.run(cmd, input=prompt.encode(), stdout=ev, stderr=err, env=full_env, cwd=cwd,
                                timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    secs = (datetime.now(timezone.utc) - t0).total_seconds()
    evidence, usage = parse_events(open(events_path))
    usage["harness"] = "pi"
    usage["seconds"] = round(secs)
    cells, answer, delivery = collect(workdir, key_fields, allowed_keys)
    final = read_json(os.path.join(workdir, "final.json")) or {}
    return {"rc": rc, "seconds": secs, "evidence": evidence, "usage": usage, "cells": cells,
            "answer": answer, "delivery": delivery, "forced": bool(final.get("forced")),
            "debrief": read_json(os.path.join(workdir, "debrief.json")),
            "trace": events_path, "workdir": workdir}


def read_json(path):
    return json.load(open(path)) if os.path.exists(path) else None
