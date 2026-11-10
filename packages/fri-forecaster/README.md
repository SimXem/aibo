# agent-box

Since 2026-10-19 this package lives in the AIRO repository ([forecastingresearch/airo](https://github.com/forecastingresearch/airo)) under `packages/fri-forecaster`, with its history; it was split out of AIRO on 2026-10-11 as agent-box and rejoined. Install it from that checkout (`pip install -e packages/fri-forecaster`) or from git (`pip install 'fri-forecaster @ git+https://github.com/forecastingresearch/airo#subdirectory=packages/fri-forecaster'`).

Agentic forecasting jobs for FRI. Today this is the FRI Forecaster package
(`fri_forecaster`); the job queue it is growing into is specced in issue #1.

[pi](https://github.com/earendil-works/pi) drives the model; this package supplies the
research tools (Tavily `web_search` / `read_page`), the submit tools, a research floor,
and the bookkeeping (evidence, usage, merged answer). Factored out of AIRO on 2026-10-05;
AIRO and the ForecastBench driver are its users.

How it fits with FRI's other code: **fri-utils is model identity** (immutable
`model_run_key`, the warehouse's `dim_model_run`); **this is the loop**. Single-call
baselines stay on fri-utils; agentic configurations run here.

## How it works

One forecasting call is a folder. The caller writes the inbox, pi works the question
with the tools it is given, and the answers land in the same folder, which is the outbox.

```
 caller: harness.run(model, system, prompt, output schema, tools)
   │
   ▼
 ┌─ inbox: <workdir>/attempt-N/ ──────────────────────────────────┐
 │ system.txt     the system prompt                               │
 │ prompt.txt     the question                                    │
 │ spec.json      the tools offered, the research floor, the      │
 │                shape of one answer, the answers wanted         │
 └───────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
 ┌─ pi 0.99.2: the agent loop (model calls, retries, context) ────┐
 │ no built-in tools; its only tools come from pi_tools.ts:       │
 │   web_search, read_page ──> tool_cli.py ──> Tavily             │
 │   submit_forecast (and optionally submit_cells), locked        │
 │   until the research floor is met                              │
 └───────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
 ┌─ outbox: the same folder ──────────────────────────────────────┐
 │ final.json     the answer (submit_forecast)                    │
 │ pieces.jsonl   answers sent along the way (submit_cells)       │
 │ events.jsonl   pi's event stream: every tool call, tokens, $   │
 └───────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
 result: cells, answer, evidence (the research calls), usage
```

Every attempt gets a fresh `attempt-N` folder, so a retry never reads an older answer.

The loop has options, all off by default (the ForecastBench driver's loop); AIRO's
runner turns them on to match its own instrument. `harness.run(..., **options)`:

| option | what it does |
|---|---|
| `floor_counts="returned"` | failed research calls count toward the research floor too |
| `coverage=[keys]` | submission waits for a recent-window `web_search` tagged with each key |
| `withhold_final=True` | the submit tools are not offered at all until the floor and coverage are met |
| `warn_missing_keys=False` | the final answer is accepted as sent, with no warning about missing cells |
| `max_turns=N` | from turn N only `submit_forecast` is offered and asked for, for up to two more turns; a reply in prose gets a nudge |
| `debrief={...}` | after the answer, one more turn for a structured debrief, validated, with retries, saved to `debrief.json` |
| `tool_parameters={...}` | replace a tool's parameter schema, e.g. to require a `cause` on `web_search` |
pi runs isolated: no built-in tools, no discovered extensions or skills, no
AGENTS.md/CLAUDE.md, so the inbox is the whole prompt.

Today each caller loops over calls itself: the ForecastBench driver makes one call per
question per model ([fri_forecaster/README.md](fri_forecaster/README.md)). Issue #1
puts a shared queue in front, **planned, not built yet**:

```
 requesters ──> inbox/<job>.json ──> workers ──> outbox/<job>/result.json ──> requesters
                                     each runs one call as above
```

## What goes in and out

A ForecastBench-style question with two resolution dates. Values are illustrative.

**In.** `prompt.txt`:

```
Today is 2026-10-11.

Question (yfinance): Will SPY's market close price be higher on the resolution date than on 2026-10-11?

Resolution criteria: Resolves to the market close price on the resolution date, from Yahoo Finance.
URL: https://finance.yahoo.com/quote/SPY
Value on 2026-10-09: 671.2 (SPY's market close on 2026-10-09.)

Give one forecast for EACH of these resolution dates (the probability the question resolves Yes when evaluated on that date): 2026-10-18, 2026-11-10
```

The harness hands pi the prompt on stdin, never as an argument (Linux allows one at most
128 KiB, and AIRO's joint prompt is past that); pi reads it as its first message, trimmed
of surrounding whitespace. `system.txt` begins *"You are a careful, calibrated forecaster…"*. `spec.json` says which
tools pi gets, how much research comes first, and what an answer looks like:

```json
{
 "research_tools": ["web_search", "read_page"],
 "min_research": 2,
 "tools": {
  "web_search": {"description": "Search the web. Returns titles, URLs, snippets and dates. …"},
  "read_page": {"description": "Read the text of one web page …"},
  "submit_forecast": {"description": "Submit your final forecasts: one {resolution_date, probability} per resolution date …"}
 },
 "cell_schema": {"type": "object", "required": ["resolution_date", "probability"],
                 "properties": {"resolution_date": {"type": "string"},
                                "probability": {"type": "number", "minimum": 0, "maximum": 1}}},
 "key_fields": ["resolution_date"],
 "allowed_keys": ["2026-10-18", "2026-11-10"]
}
```

**Out.** `final.json`, written when the model calls `submit_forecast`:

```json
{
 "t": 1791729120000,
 "research": 3,
 "research_failed": 0,
 "answer": {
  "forecasts": [
   {"resolution_date": "2026-10-18", "probability": 0.56},
   {"resolution_date": "2026-11-10", "probability": 0.6}
  ],
  "rationale": "SPY closes higher over a week a little over half the time, and over a month about 60%; nothing scheduled before 2026-11-10 looks large enough to move that.",
  "key_sources": ["https://finance.yahoo.com/quote/SPY"]
 }
}
```

The result `harness.run` returns, folded from the outbox:

```json
{
 "cells": {
  "2026-10-18": {"resolution_date": "2026-10-18", "probability": 0.56},
  "2026-11-10": {"resolution_date": "2026-11-10", "probability": 0.6}
 },
 "answer": {"forecasts": ["…as in final.json…"], "rationale": "…", "key_sources": ["…"]},
 "evidence": [
  {"tool": "web_search", "args": {"query": "SPY weekly returns base rate"}, "result": {"results": ["…"]}, "error": null},
  {"tool": "read_page", "args": {"url": "https://finance.yahoo.com/quote/SPY"}, "result": {"text": "…"}, "error": null},
  {"tool": "web_search", "args": {"query": "market calendar October November 2026", "recent_days": 30}, "result": {"results": ["…"]}, "error": null}
 ],
 "usage": {"turns": 6, "input_tokens": 48210, "output_tokens": 2950, "cached_tokens": 31800,
           "cost_usd": 0.31, "research_ok": 3, "research_failed": 0, "harness": "pi", "seconds": 74},
 "delivery": {"cells_calls": 0, "cells_in_pieces": 0, "cells_in_final": 2},
 "rc": 0
}
```

Only the answers asked for (`allowed_keys`) are kept; anything else the model sends is
dropped.

## Requirements

- Python ≥ 3.11, stdlib only.
- Node and pi **0.99.2**, pinned in `package.json`: `npm ci` in the checkout puts it where
  the harness looks (`harness.REPO_PI`). Override with `FORECASTER_PI` (a `pi` executable
  or its `cli.js`). pi owns model auth.
- `TAVILY_API_KEY` for research, and the providers' API keys, from the environment or an
  env file (`keys.py`).
- Optional: `FORECASTER_BLOCK_URL_PATTERNS`, regular expressions separated by commas or
  newlines, matched case-insensitively against URLs. When set, `web_search` drops matching
  results and `read_page` refuses matching URLs; unset or empty, nothing changes. Pass it
  per run with `harness.run(env=...)`.

```sh
git clone https://github.com/forecastingresearch/agent-box && cd agent-box
npm ci && python -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

## Tavily response cache

Searches and full-page extracts are cached on disk for **one hour** by default,
shared by all local workers and tool subprocesses (including separate conditions
and models). Identical concurrent requests make only one upstream call. This is
implemented in the Tavily tools, not the agent-box service; AIRO's mirrored tools
use the same cache format and directory.

- `FORECASTER_TAVILY_CACHE_DIR`: defaults to
  `${XDG_CACHE_HOME:-~/.cache}/fri-forecaster/tavily`. Use a local filesystem.
- `FORECASTER_TAVILY_CACHE_TTL`: lifetime in seconds; default `3600`, `0` disables.
  To isolate a forecasting run, set a fresh directory for that run and remove it
  afterwards. Otherwise nearby runs may reuse evidence for up to one hour.
- Keys include the endpoint, complete request settings (including news dates),
  and a hash of the API credential; credentials themselves are never stored.
  Queries are matched exactly, not semantically. Full-page extraction is shared
  across offsets; condition/group tags do not partition identical research.
- URL guards and group tags are applied anew on every call, including cache hits.
  Tool results and evidence recording retain their existing shape.
- Network failures, API error responses, and empty/failed extracts are not cached.
  Cache storage failures fall back to live requests. No stale-on-error fallback.
- The private cache contains source text. Expired rows are pruned on successful
  writes; remove the directory when no workers are running to purge everything.
  This stdlib implementation uses Linux/POSIX advisory file locks.

An opt-in live probe from the AIRO checkout checks eight concurrent workers
across both tool copies, pagination, and per-caller tags, with an isolated cache:

```sh
python3 code/probe_tavily_cache.py --live --env-file /path/to/provider.env
```

It makes no model calls and caps HTTP attempts at four (normally one search and
one extraction). It prints request counts and checksums, not credentials or page
contents, and removes its temporary cache afterwards. This verifies deliberate
identical requests, not the hit rate of a natural forecasting run.

## Use

```python
from fri_forecaster import harness
res = harness.run(model="openai-codex/gpt-6-astra", system=SYS, prompt=P, workdir=W,
                  cell_schema={...}, key_fields=["resolution_date"], allowed_keys=[...],
                  tool_descriptions={...}, min_research=2)
res["cells"], res["answer"], res["evidence"], res["usage"]
```

ForecastBench, from picking models by ECI to the forecast sets you upload:
[fri_forecaster/README.md](fri_forecaster/README.md).

## Dependency security

`brace-expansion` is overridden to `^5.0.12` to fix the filename-pattern
availability advisories in pi → minimatch → brace-expansion. The lockfile also
omits pi's `hasShrinkwrap` flag: otherwise npm replays pi 0.99.2's published
shrinkwrap and installs 5.0.9 even with the override and patched lock entry.
When refreshing dependencies, verify a clean `npm ci` followed by
`npm ls brace-expansion` still installs 5.0.12 or later.

## Test

```sh
python -m pytest -q        # no network, no spend
```

The harness and driver tests use a fake pi. `tests/test_pi_tools.py` runs the real pi
(`npm ci` first; skipped without it) against a scripted model on a local server, so
`pi_tools.ts` is tested as pi loads it: the research floor, pieces, the final answer.
CI runs both on every push and pull request.
