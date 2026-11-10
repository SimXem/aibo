# Math-problem shock

The math-problem shock is a manual, unpublished experiment. It asks whether a
model's AI-risk forecast (AIRO) or AI-benefit forecast (AIBO, the welfare page)
changes after the model has just seen how badly or how well it forecast
something else.

The "something else" is a set of 60 open math problems. In one conversation the
model first forecasts when each problem will be solved. In the shock arm it is
then told which ones were actually solved, next to its own forecasts. After that
it gets the normal AIRO or AIBO prompt, unchanged.

There are two parts in this repository:

| Part | Where | What it does |
|---|---|---|
| The math-problem project | `experiments/math-shock/` (a git subtree of [SimXem/math-problem-info-shock](https://github.com/SimXem/math-problem-info-shock)), run with `code/math_shock_pipeline.py` | The standalone study: builds the 60-problem sample, asks models for forecasts, then asks follow-up questions. Its own README explains the method in full. |
| The shock experiment | `code/run_math_shock.py` (content in `redlines/math_shock.py`) | Runs the math exchange *before* AIRO's or AIBO's prompt, in three arms, and writes the rows. |

You only need the second part to run the experiment. Run `w1-r1` of the
project is already finished and committed; the experiment uses a "pack" built
from it.

## What the math shock is

### The math problems

- 60 problems from two public trackers: the
  [Erdős Problems database](https://github.com/teorth/erdosproblems) and
  Google DeepMind's
  [Formal Conjectures](https://github.com/google-deepmind/formal-conjectures).
- All 60 were open on **T0 = 2026-06-30**, the end of the training-cutoff
  month of the newest model asked.
- 15 had been solved by the snapshot date **S = 2026-11-02**. Ten of the 60 were
  picked *because* they were solved; the other 50 were drawn at random, and 5 of
  those were solved. Across all 533 eligible problems, 66 (12.4%) were solved
  by S.
- For each problem the model gives three months: a best guess, a 10% date and
  a 90% date. It answers as a JSON array, with no tools (no search, no code).

### The three arms

Every arm makes one call per eligible model. Each call is one conversation, and
"the series' prompt" is AIRO's or AIBO's normal prompt, unchanged:

| Arm | First user message | Second user message |
|---|---|---|
| `control` | The series' prompt | — |
| `math-placebo` | The math prompt (the model forecasts the 60 problems) | "Next, a separate set of questions.", then the series' prompt |
| `math-shock` | The math prompt (the model forecasts the 60 problems) | **The reveal**, then "Next, a separate set of questions.", then the series' prompt |

**The reveal** lists the 15 solved problems. For each, it gives the solve date,
the model's own forecast, and whether the solve came before its 10% date,
inside its 10%–90% range or after its 90% date. It then says how the sample was
drawn and gives the base rate (66 of 533), so that the enriched sample alone
does not drive the update. Finally it lists the 45 problems that were still
open. It does not ask for revised math forecasts.

How to read the arms:

- `math-shock` vs `math-placebo`: the effect of the feedback.
- `math-placebo` vs `control`: the effect of doing the math task at all.

If the answer to the math prompt has no JSON array, the model is asked once
more: "Reply with the JSON array only, exactly as specified above." If it still
fails, the call fails and is retried; the series' prompt is never asked without
the math step.

### Who is asked

Only models whose training cutoff is on or before T0, so that none can already
know which problems were solved. Cutoffs, with sources, are in
`data/training_cutoffs.json`; a model missing from that file is skipped. The
same models are asked in all three arms. As of 2026-11-10, all four panel
models are eligible: Opus 5.5, GPT-6 Astra, Sonnet 5.5 and Fable 5.1.

### The pack

The problem texts, outcomes and prompt templates for the experiment are in one
JSON file, `private/pretasks/math-shock-w1-r1.json` (or under
`$AIRO_PRETASK_DIR`). It is kept **outside git**, and `code/run_math_shock.py`
pins it by SHA-256. Rows written to `results/experiments/` (which feeds the
public download) carry only opaque problem codes, the model's dates and hashes,
never problem text. The full text of each conversation goes to private
transcripts beside the pack.

## Setup

1. Set up AIRO as usual (see "Elicit new forecasts" in the top-level
   `README.md`): the pi harness (`pip install -e . -e ./packages/fri-forecaster`
   and `npm ci` in `packages/fri-forecaster`), plus API keys in
   `~/.config/redlines/env`, including `TAVILY_API_KEY`.
2. Build the pack if `private/pretasks/math-shock-w1-r1.json` is missing:

   ```bash
   python code/math_shock_pipeline.py pack --run w1-r1
   ```

   It should print `sha256 8f3585467566a067808d7ea40f48649ee0ee214fad24b68fde457d3a4359370a`.
   The runner refuses any other hash.
3. Only if you want to run the project's own stages or tests, give it its own
   environment:

   ```bash
   python3 -m venv experiments/math-shock/.venv
   experiments/math-shock/.venv/bin/pip install -r experiments/math-shock/requirements.lock.txt
   ```

   `code/math_shock_pipeline.py` uses `$MATH_SHOCK_PYTHON` if it is set, else
   that `.venv`, else the Python that runs it.
4. For AIRO's tests of this code: `pip install -e '.[test]'`.

**Do not edit files inside `experiments/math-shock/`.** The pack records the
project commit it was built from. A local edit changes that, so the pack's
hash no longer matches the pinned one. Bring in project updates with
`git subtree pull`.

## Commands

Commands marked **PAID** call model APIs. Everything else is free and offline.

### `code/run_math_shock.py`: the experiment

| Command / option | What it does |
|---|---|
| `--dry-run` | Prints the series' prompt, the math prompt, the retry line, the turn each math arm adds, and which models would be asked. No model is called. |
| *(no options)* | **PAID.** All three arms × every eligible model, with AIRO's prompt. |
| `--experiment airo` / `welfare` | Which series' prompt every arm asks: `airo` (risk questions, the default) or `welfare` (AIBO's benefit questions). |
| `--condition NAME` | Which of the series' five prompt conditions to ask: `none` (the default prompt, the default), `independent`, `recent`, `critical`, `two-step`, or `all`. Repeatable or comma-separated; each condition gets all three arms. See [the five prompt conditions](#running-it-under-the-five-prompt-conditions). |
| `--arm NAME` | Only this arm: `control`, `math-placebo` or `math-shock`. Repeatable. Default: all three. |
| `--models "A,B"` | Only these models, by label as the dry run prints them (e.g. `"GPT-6 Astra"`). |
| `--smoke` | **PAID.** The first eligible model only. Rows go to `smoke-…` files. |
| `--workers N` | Calls in parallel (default 5). |
| `--retries N` | Re-asks a call whose math step failed or whose forecast grid came back less than 90% complete (default 2). |
| `--out`, `--conditional-out` | Override where rows are written (default `results/experiments/`). |
| `--allow-ungrounded` | Runs without Tavily web search; rows are marked ungrounded. |

### `code/math_shock_pipeline.py`: the math-problem project

`python code/math_shock_pipeline.py STEP [ARGS...]`, from the repository root.
Paths after the step are relative to `experiments/math-shock/`, and any other
arguments are passed to the step unchanged.

| Step | What it does |
|---|---|
| `prepare config/runs/<run>.yaml` | Downloads both trackers, builds the problem frame, outcomes and sample, drafts any missing problem statements (**PAID** if any are missing; frozen ones are reused), writes the prompts and a lock file, then rebuilds everything from the archive to check it. `--no-fetch` skips the download. |
| `forecast config/runs/<run>.yaml` | **PAID** (batch API, half price). Sends each model the math prompt 5 times, with the problems in a different order each time, and parses the answers into `runs/<run>/parsed.csv`. `--stub` is a free offline dry run; `--models` and `--samples N` pick a subset; `--direct` skips the batch API. |
| `followup config/followups/<id>.yaml` | **PAID.** Shows each model which problems were solved, next to its forecasts, and asks for revised forecasts of the open ones. Writes `runs/<run>/followups/<id>/`. |
| `test` | The project's own tests (22). No network, no API. |
| `pack --run <run>` | Builds the experiment's pack from a finished run (`code/build_math_shock_pack.py`). It checks the run's hashes and that its statements are approved, checks that the pack reproduces the project's prompts byte for byte, writes `private/pretasks/math-shock-<run>.json` and prints its SHA-256. `--out-dir` writes elsewhere. |

The project's stages use this repository's API keys, then
`experiments/math-shock/.env` for any that are still unset.

### Tests

```bash
pytest tests/test_math_shock.py tests/test_math_pipeline.py   # AIRO's side, incl. the project's tests
python code/math_shock_pipeline.py test                       # the project's tests alone
```

## Running it with the default AIRO prompt

"Default" means AIRO's `none` condition: the baseline prompt with no added
instruction (`experiments/airo.toml`). This is what the runner asks when you
don't pass `--condition`.

```bash
python code/run_math_shock.py --dry-run    # check the prompts and the models; free
python code/run_math_shock.py --smoke      # PAID: one model, all three arms
python code/run_math_shock.py              # PAID: every eligible model, all three arms
```

To run part of it, for example the shock arm for one model:

```bash
python code/run_math_shock.py --arm math-shock --models "GPT-6 Astra"
```

Output, with `<run>` a UTC timestamp such as `2026-11-10T1530Z`:

- `results/experiments/math-shock-<run>.jsonl`: the unconditional answers.
- `results/experiments/math-shock-<run>-instrument.jsonl`: every row.
  Each row's `condition` is its arm. The first row of each math-arm call has a
  `pretask` field with the problem order, the model's math forecasts, the
  number of valid ones, hashes, token use and the transcript path. Control rows
  have `pretask: null`.
- `private/pretasks/math-shock-w1-r1/transcripts/<run>/`: the full
  conversations of the math arms (prompts, replies, both pi sessions).

## Running it with the default AIBO prompt

Add `--experiment welfare`. Every arm then asks AIBO's `none` prompt (life
expectancy and economic growth, `experiments/welfare.toml`) in place of
AIRO's.

```bash
python code/run_math_shock.py --experiment welfare --dry-run
python code/run_math_shock.py --experiment welfare --smoke     # PAID
python code/run_math_shock.py --experiment welfare             # PAID
```

The rows go to `results/experiments/welfare-math-shock-<run>.jsonl` (and
`-instrument.jsonl`). Their own name keeps them out of AIRO's download.

### If a paid run is refused

Before any paid run, AIRO and AIBO alike, the runner checks that the newest
ECI snapshot is no more than 21 days old. It also checks that the scenario sets
that quote the snapshot (`data/eci_self_conditions.json`,
`data/eci_self6mo_conditions.json`, `data/combined_conditions.json`) were
regenerated from it. For AIBO, it also checks that
`data/welfare_conditions.json` is the current copy of AIRO's combined set. Dry
runs skip these checks.

To fix a refusal, run all of these steps. Fetching a snapshot alone is not
enough.

```bash
python3 -m redlines.eci --fetch                  # 1. a fresh snapshot: data/epoch_capabilities_index_<date>.csv
python3 code/check_eci_snapshot.py --rebuild     # 2. regenerate the scenario sets from it, then check them
python3 code/make_welfare_conditions.py          # 3. AIBO only: re-copy the combined set
python3 code/make_welfare_conditions.py --check  #    and confirm the copy is current
```

Steps 2 and 3 rewrite tracked files in `data/`. The scheduled AIRO job does
steps 1 and 2 itself before every run (`code/refresh_panel.sh`). If the
combined set's protocol has changed, step 3 refuses until the copy gets a new
welfare protocol (`--protocol welfare-joint-v2`, see
`code/make_welfare_conditions.py`).

## Running it under the five prompt conditions

AIRO's published number for a model is the mean of five calls, one under each
of five prompt conditions (`experiments/airo.toml`). AIBO uses the same five,
with its own wording for `independent` and `two-step`
(`experiments/welfare.toml`).

| Condition | Instruction added to the prompt |
|---|---|
| `none` | Nothing (the default prompt). |
| `independent` | Make your own forecasts; don't rely on external surveys or prominent figures' probabilities. |
| `recent` | Focus on, and weight more heavily, information from the past year. |
| `critical` | Evaluate existing forecasts critically, including the track record of whoever made them. |
| `two-step` | First forecast capability progress, then the risk (AIBO: the progress) given those capabilities. |

The full texts are in `VARIANTS` in `redlines/experiments.py`.

Use `--condition all` to run the shock under all five. Each condition gets
the three arms, so one run asks 15 arms per eligible model:

```bash
python code/run_math_shock.py --condition all --dry-run                          # AIRO: the five prompts; free
python code/run_math_shock.py --condition all --smoke                            # PAID: one model, 15 calls
python code/run_math_shock.py --condition all                                    # PAID: every eligible model

python code/run_math_shock.py --experiment welfare --condition all --dry-run     # AIBO: the five prompts; free
python code/run_math_shock.py --experiment welfare --condition all               # PAID
```

You can also pick some of them, by repeating the option or with a comma:

```bash
python code/run_math_shock.py --condition recent,critical
python code/run_math_shock.py --condition none --condition two-step --arm math-shock
```

The dry run prints each condition's prompt once, then the math step once, then
the turn that each kind of math arm adds before its condition's prompt.

**Cost.** A full five-condition run is five times a default run: 3 arms × 5
conditions × the eligible models. With today's four models that is 60
full-length AIRO (or AIBO) calls, 40 of which also have a math step first.

**How the rows are labelled.** All conditions of one run go into the same
files (`math-shock-<run>.jsonl` for AIRO, `welfare-math-shock-<run>.jsonl` for
AIBO). Each row's `condition` names its arm and prompt condition:

| Prompt condition | `control` arm | `math-placebo` arm | `math-shock` arm |
|---|---|---|---|
| `none` | `control` | `math-placebo` | `math-shock` |
| `recent` (and the others) | `control.recent` | `math-placebo.recent` | `math-shock.recent` |

The rows' `variant` field gives the instruction that was added (AIBO's
`independent` shows as `welfare-independent`). In Python,
`split_arm("math-shock.recent")` in `code/run_math_shock.py` returns
`("math-shock", "recent")`.

Within one run, a model sees the 60 problems in the same order in every math
arm, so the arms differ only in the reveal and the prompt condition. A
`control.<condition>` row asks exactly what that condition asks in AIRO's or
AIBO's own runs, and has the same `condition_sha256`.

Only these five can be picked. AIRO's sixth condition (`ai-banned`, with its
URL guard) and the Friday news shadow are refused.
