# Build the AIRO welfare dashboard by reusing AIRO's pipeline

You are working in the AIRO repo (`/home/s/aibo`, a fork; the Python package is `redlines`). AIRO asks a panel of frontier models catastrophe questions. Each question is asked once unconditionally and once under 14 scenario conditions, under five prompt variants whose mean is each model's published number. The results are rendered as `index.html`.

Your job is to run **the same pipeline with a different prompt**:
- **Questions:** 5 welfare questions (life expectancy and GDP growth) instead of the Auto-ARC ladder.
- **Conditions:** the same 14 scenario conditions.
- **Prompts:** the same five prompt variants, two of them reworded.
- **Output:** a second page, `welfare.html`.

**Write as little new code as possible.** Reuse AIRO's functions, data shapes, page chunks and the published pilot's page components. Where an existing function nearly fits, give it a parameter rather than copying it. Write new code only where the welfare questions really differ.

There is one real difference: each question x horizon cell is answered with **five percentiles** (p10, p25, p50, p75, p90) instead of one probability. Your new code should sit around that difference and nowhere else.

## Read first

- `welfare/README.md`: what each file in `welfare/` is, and the open choices with their defaults.
- `welfare/questions.json`, `welfare/welfare_conditions.json`, `welfare/variants.json`, `welfare/experiment.welfare.toml`.
- `welfare/prompts/welfare-two-step.txt` and `welfare/prompts/tools.json`: the intended content of a welfare call. They were rendered by a reference script, not by the runner. Your live render follows the runner's own layout, and it must carry the same content.
- `welfare/reference/welfare-page-pilot.jsx` and `welfare/reference/welfare-pilot-blob-2026-10-01.json`: the published pilot page's components and its data blob. These are your page and your blob shape.
- In `code/run_unified.py`: `run`, `run_one_joint`, `load_batch`, `build_prompt`, `build_prompt_joint`, `PROMPT_JOINT_GROUPED`, `minimal_joint_prompt`, `_cells_schema`, `submit_cells_tool`, `submit_tool_joint`, `clean_forecasts_joint`, and the row-writing code after the loop.
- Also: `redlines/experiments.py`; `redlines/runlog.py` (`pool`, `pooled_rows`, `panel_rows`); `redlines/views/axes.py`, a view over its own scenario set's logs and the closest model for yours; `redlines/__main__.py` (BUILDERS, VIEW_ORDER, PAGE_ORDER, `cmd_assemble`); `redlines/pages.py`; `web/demo/manifest.json`.

## What is already reused, with no code

- **Separate logs.** `data/welfare_conditions.json` is the combined set copied verbatim under slug `welfare`. Because it is not in `PUBLISHED_SETS`, `run()` already sends its rows to `results/welfare_runs/` and `results/conditional_runs_welfare.jsonl`, and refuses AIRO's logs.
- **Conditions text.** `resolve_set` and `scenarios_block` render the CONDITIONS block and the `eci_forecast` step from it.
- **Experiment machinery.** `redlines/experiments.py` loads `welfare/experiment.welfare.toml` as is once the two variant keys exist. That covers cadence (manual), pooling, the `condition_sha256` stamps and the `--dry-run` preview. No new settings and no hash changes are needed.
- **The call itself.** The minimal instrument, the pi harness, `run_one_joint`'s loop, partial delivery through `submit_cells`, the usage and evidence capture, and the row stamps. `minimal_joint_prompt` already rewrites the catastrophe head to a neutral "questions. Answer all of them".
- **The page.** `redlines/pages.py`, `redlines/hydrate.py`, the `web/demo/` and `web/shared/` chunks, and the pilot's components.

## Do this

1. **Data and config.**
   - Copy `welfare/questions.json` to `data/welfare_questions.json`, `welfare/welfare_conditions.json` to `data/`, and `welfare/experiment.welfare.toml` to `experiments/welfare.toml`.
   - Add `welfare-independent` and `welfare-two-step` to VARIANTS in `redlines/experiments.py`. Use the texts from `welfare/variants.json` verbatim, with a dated comment like the existing ones.
   - Do not edit the existing variants.
2. **Questions.** When the scenario set names `questions`, `run()` loads that file instead of the ladder and cross-cutting files. Use a small loader that returns `load_batch`'s tuple. Make `build_prompt` take what welfare questions lack or add: no severity label, a `unit_text` line, and per-question horizon meanings. It should not grow a second path.
3. **Percentiles.** Thread one value mode, probability or percentiles, through the existing functions. It comes from the question set and defaults to probability:
   - the cell schema (`welfare/prompts/tools.json` shows the percentile form);
   - `take_cells`;
   - `clean_forecasts_joint`, which accepts five finite, non-decreasing numbers within the question's `bounds`;
   - the delivery paragraph and the Step 2 sentence of the prompt (see the prompts in `welfare/prompts/` for the wording);
   - the rows' `forecasts` entries, which become `{"horizon", "percentiles": {...}}`.
   
   `minimal_joint_prompt` puts the variant paragraph before the delivery paragraph. Keep that anchor working for both modes.
4. **View.** Add `redlines/views/welfare.py`, modelled on `axes.py` and registered as `welfare`. It reads the welfare logs through `runlog`'s existing filters and pools the newest complete day:
   - each percentile is averaged over a model's five pooled calls, the way `pool` averages probabilities;
   - `eciForecast` is pooled the same way;
   - `shift` is the conditional p50 minus the unconditional p50.
   
   It emits `window.__WELFARE__` in the pilot blob's shape. With no welfare rows it emits a blob the page shows as unavailable, and `python -m redlines build` must not fail.
5. **Page.**
   - Write `web/welfare/manifest.json` with target `welfare.html`. List the existing chunks the pilot components need, and the blobs those chunks read.
   - Add the pilot's JSX as `web/welfare/85-welfare.jsx`, as unchanged as possible. Replace the PILOT badge with the run date, and add one collapsible line listing the five prompt texts and saying the number is their mean.
   - Leave out `80-app.jsx`.
   - Add `welfare` to PAGE_ORDER.
6. **Tests.** Add `tests/test_welfare.py`, fixtures only. Cover:
   - the welfare set's conditions, groups and elicit equal the combined set's, so a drift of the copy fails;
   - the variant lands before the delivery paragraph;
   - percentile cleaning: good, missing, non-monotone and out-of-bounds cells;
   - the probability mode is unchanged;
   - the view pools five synthetic calls correctly and builds when empty;
   - the page assembles.
   
   Run the whole `pytest` suite.

## Hard constraints

- **No paid API calls.** Do not run anything that calls a model, elicits, publishes or deploys. That includes `code/run_unified.py` without `--dry-run`, `code/cron_run.sh`, `code/publish_dashboard.sh` and `code/publish_public.sh`. Before relying on `--dry-run`, read it and confirm it exits before any paid call.
- Prefix every runner or CLI command with `REDLINES_ENV_FILE=/dev/null`. Never read, source or print `.env` or any credential file (`redlines.llm.load_keys()` reads `~/.config/redlines/env` and `<repo>/.env` otherwise).
- **AIRO must not move.** Leave unchanged: `index.html`; `results/`; `data/combined_conditions.json`; the existing experiments and VARIANTS; AIRO's rendered prompt; every existing `condition_sha256`. The golden tests must pass.
- Match the surrounding code: dated comments that say why, stdlib only in the build stage, existing names.
- Work on `main`: this is a fork, so no new branch. Commit in logical steps. Do not push.

## Done means

- `pytest` passes, and nothing AIRO publishes changed.
- `REDLINES_ENV_FILE=/dev/null python -m redlines.experiments due welfare` lists the five conditions. `... --date <a Wednesday>` without a name does not list them.
- `REDLINES_ENV_FILE=/dev/null python code/run_unified.py --experiment welfare --dry-run` prints welfare prompts with the content of `welfare/prompts/`.
- `python -m redlines build --views welfare` and the welfare page assembly succeed, both empty and from fixtures.

## Report back

In under 300 words:
- what you changed, file by file, and how many lines of new code that came to;
- anything you could not reuse, and why;
- the exact command for the first live run;
- an estimate of its cost from the pilot ($16.85 for one Opus 5.5 call, so about $85 per model for five calls).
