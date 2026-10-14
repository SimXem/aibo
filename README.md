# agent-box

Agentic forecasting jobs for FRI. Today this is the FRI Forecaster package
(`fri_forecaster`); the job queue it is growing into is specced in issue #1.

An agentic forecasting harness: [pi](https://github.com/earendil-works/pi) drives the
model; this package supplies the research tools (Tavily `web_search` / `read_page`), the
submit tools, a research floor, and the bookkeeping (evidence, usage, merged answer).
Factored out of AIRO on 2026-10-05; AIRO and the ForecastBench driver are its users.

How it fits with FRI's other code: **fri-utils is model identity** (immutable
`model_run_key`, the warehouse's `dim_model_run`); **this is the loop**. Single-call
baselines stay on fri-utils; agentic configurations run here.

## Requirements

- Python ≥ 3.11, stdlib only.
- Node and pi **0.99.2**, pinned in `package.json`: `npm ci` in the checkout puts it where
  the harness looks (`harness.REPO_PI`). Override with `FORECASTER_PI` (a `pi` executable
  or its `cli.js`). pi owns model auth.
- `TAVILY_API_KEY` for research, and the providers' API keys, from the environment or an
  env file (`keys.py`).

```sh
git clone https://github.com/forecastingresearch/agent-box && cd agent-box
npm ci && python -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

## Use

```python
from fri_forecaster import harness
res = harness.run(model="openai-codex/gpt-6-astra", system=SYS, prompt=P, workdir=W,
                  cell_schema={...}, key_fields=["resolution_date"], allowed_keys=[...],
                  tool_descriptions={...}, min_research=2)
res["cells"], res["answer"], res["evidence"], res["usage"]
```

ForecastBench (see the module docstring for the rules):

```sh
python -m fri_forecaster.forecastbench run   --root R --model openai-codex/gpt-6-astra
python -m fri_forecaster.forecastbench build --root R --set-number 2 \
    --member openai-codex/gpt-6-astra --name "..." --org "<team name>" --model-org OpenAI
```

A whole round, unattended: `scripts/fb_round.sh <due date>`. It submits the conditions
of a name registry (`fri_forecaster/names.py`) and reads its machine settings from
`~/.config/fri-forecaster/round.env`. The registry and the team name stay private, outside
the repo; `examples/` shows the shape of both.

## Test

```sh
python -m pytest -q        # against a fake pi: no network, no spend
```
