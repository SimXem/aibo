# Math-problem forecasting pipeline

Language models get 60 math problems that were open at a reference date T0 (their training cutoff) and forecast when each will be solved. A follow-up then shows each model which of them were solved by a later snapshot date S, next to its own forecast, and asks for revised forecasts of the problems still open.

## How to run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock.txt
# API keys in .env: ANTHROPIC_API_KEY=..., OPENAI_API_KEY=...  (git-ignored)

.venv/bin/python -m pipeline.stage_prepare  config/runs/w1-r1.yaml          # data, sample, statements, prompts
.venv/bin/python -m pipeline.stage_forecast config/runs/w1-r1.yaml          # forecasts -> runs/w1-r1/parsed.csv
.venv/bin/python -m pipeline.stage_followup config/followups/w1-r1-f2.yaml  # revised forecasts -> runs/w1-r1/followups/<id>/
.venv/bin/python -m unittest discover -s tests -t .                         # tests (no network, no API)
```

- **`stage_prepare`** downloads both trackers, builds the frame, outcomes and sample, drafts missing problem statements, writes the prompts and a lock file, and rebuilds everything from the archive to check it. New statements are frozen **without human review** (marked `auto_approved`); existing ones are reused. `--no-fetch` skips the download.
- **`stage_forecast`** sends each model its forecast prompt 5 times, with the problems in a different order each time, and parses the answers. `--models` and `--samples N` select a subset.
- **`stage_followup`** sends the follow-up message in each finished forecast conversation of the models in the follow-up config, then writes `parsed.csv` (revised next to earlier forecast), `dates_long.csv` and `dates_summary.csv`.

All model calls go through the providers' batch APIs at half price (Anthropic Message Batches, OpenAI Batch API); `--direct` uses direct calls instead, and `--stub` does a free offline dry run. The runners can be re-run safely: finished work is skipped. `--help` on each runner lists its steps; each step is also a module of its own (`pipeline.fetch`, `build`, `statements`, `verify`, `run`, `run_batch`, `parse`, `followup`). For a new snapshot, copy `config/runs/w1-r1.yaml` with a later `snapshot_date` and the actual `run_date`; never edit a config, rules file or template a run has used.

## Sources and procedure

**Trackers.** Both are archived as git bundles in `archive/` (checksums in `manifest.json`); every later step reads only from those bundles.
- [Erdős Problems database](https://github.com/teorth/erdosproblems) (Apache-2.0): problem status, prize and tags from `data/problems.yaml`. Archived head `e8eb305` (2026-11-03).
- [Formal Conjectures](https://github.com/google-deepmind/formal-conjectures) (Apache-2.0, Google DeepMind): one Lean 4 file per problem, with a `research open` / `research solved` category per theorem, a docstring and the formal statement. It is the second status source for Erdős problems and the source of all statement texts. Archived head `91de790` (2026-11-03).

**Frame, outcomes, sample** (all rules in `rules/rules_v1.yaml`):
- **Open at T0:** open in the tracker at T0, with at least one open headline theorem (name without `.variants.`) in a Formal Conjectures file. Erdős problems without such a file, "not provable / not disprovable" problems and the machine-generated WrittenOnTheWallII collection are excluded.
- **Solved by S:** the Erdős database says proved, disproved, solved or independent, or all headline theorems in the Formal Conjectures file are no longer open. The solve date is the earliest such recording, taken as the UTC date of the commit. Literature finds are dropped: solves whose commit says the result was already known, or whose added references all predate T0.
- **Sample:** 60 problems: 10 drawn from those solved by S, 50 at random from the rest, stratified (Erdős / named conjectures / other) and drawn by seeded hash rank. Inclusion probabilities are stored per problem.

**Statements.** The text each model sees is drafted by Claude Opus 5.5 from the problem's T0 docstring and Lean statement (at most 50 words, no history, attribution or solution status) and frozen in `statements/`. The 60 statements in use were reviewed against the full T0 Lean files: 33 drafts kept, 27 corrected. The review files are in `review/`.

**Prompts.** The forecast prompt (`templates/v1/forecast.txt`) lists the 60 problems and asks for three dates per problem: a best guess and the dates by which the model gives a 10% and a 90% chance of a solve, as JSON. The follow-up (`templates/followup_v1/reveal_solved.txt`) lists the problems solved by S with the model's earlier forecast for each, states that 10 of the 60 were chosen because they were solved and that 66 of 533 (12.4%) eligible problems were solved by S, and asks for revised forecasts of the still-open problems.

**Models.** IDs and cutoffs from the vendors' model pages (checked 2026-11-04). T0 = 2026-06-30, the end of the month of the latest cutoff.

| Model | API ID | Training cutoff | Effort |
|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | Jun 2026 ([source](https://platform.claude.com/docs/en/about-claude/models/overview)) | vendor default (`medium`) |
| GPT-6 Astra | `gpt-6-astra` | Apr 30, 2026 ([source](https://developers.openai.com/api/docs/models/gpt-6-astra)) | `high` |
| GPT-6.1 Sol | `gpt-6.1-sol` | Apr 30, 2026 ([source](https://developers.openai.com/api/docs/models/gpt-6.1-sol)) | `high` |
| GPT-6.1 Terra | `gpt-6.1-terra` | Jun 01, 2026 ([source](https://developers.openai.com/api/docs/models/gpt-6.1-terra)) | `high` |

**No tools.** The models get no web search, web fetch or code execution; the code refuses any request parameter beyond the model, messages, effort and token limit. The prompt names the trackers (and the Erdős database's URL), but the models cannot look anything up.

**Reproducibility.** Rebuilding a run from its config and the archived bundles reproduces frame, outcomes, sample and prompts byte for byte (`pipeline.verify`). Model calls refuse to start if the prompts don't match the run's lock file. Every model response is archived unchanged in `raw/`, with request parameters and token usage.

## Run so far

One test run with Claude Opus 5.5 (run `w1-r1`, T0 = 2026-06-30, S = 2026-11-02): 5 forecast samples on 2026-11-03 and the follow-up (`w1-r1-f1`) on 2026-11-04. All 300 forecasts and 225 revised forecasts parsed as valid. Results are in `runs/w1-r1/parsed.csv` and `runs/w1-r1/followups/w1-r1-f1/`. The archived requests contain no tools and the responses no tool use.

## Layout

| Path | Content |
|---|---|
| `config/waves/`, `config/runs/`, `config/followups/` | T0, seed, sample sizes, models · snapshot date and prompt date per run · follow-up settings |
| `rules/`, `templates/` | selection and resolution rules · prompt templates |
| `archive/`, `statements/`, `review/` | tracker bundles (not committed) · frozen statements · statement drafts and reviews |
| `runs/<run>/` | `frame.csv`, `outcomes.csv`, `sample.csv`, `prompts.jsonl`, `run.lock.json`, `raw/`, `parsed.csv`, `followups/<id>/` |
| `pipeline/` | the code; `stage_*.py` are the three runners |

## Limitations

- The OpenAI code (direct and batch) has only been tested with a fake client. Run one sample first: `stage_forecast ... --models gpt-6.1-terra --samples 1`.
- In the follow-up, OpenAI models get their earlier answer back as text only, Claude models with their thinking blocks.
- Statements frozen by `stage_prepare` without review are only checked for length.
- Tracker dates are dates of recording, not of proof, and curators sometimes record many results in one commit. Solves recorded only in Formal Conjectures count (31 Erdős problems are solved there but still open in the Erdős database).
- The literature-find rule and the Lean parser are heuristics (regex-based, with a consistency check that halts on mismatches).
