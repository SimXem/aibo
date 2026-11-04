# Math-problem forecasting pipeline

Models get a list of math problems that were open at a reference date T0 and predict when each will be solved. A follow-up then shows each model which problems were solved between T0 and a snapshot date S, next to its own forecast, and asks it to revise its forecasts for the problems that are still open.

Every run is a pure function of a config plus archived tracker history. Rerunning an old config reproduces the frame, sample, outcomes and prompts byte for byte (`pipeline.verify`). Model outputs can't be reproduced, so every raw response is archived instead.

## Setup (Linux)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
```

Commands below call `.venv/bin/python` directly; after `source .venv/bin/activate` you can write plain `python` instead.

API keys go in `.env` (`ANTHROPIC_API_KEY=...`, `OPENAI_API_KEY=...`). The file is git-ignored, and `.claude/settings.json` denies Claude read and edit access to it.

## Workflow

Three runners cover the whole workflow. Each one can be re-run safely: finished work is skipped, and batches left over from an interrupted run are collected first.

```bash
.venv/bin/python -m pipeline.stage_prepare  config/runs/w1b-r1.yaml          # steps 1-6: data, sample, statements, lock
.venv/bin/python -m pipeline.stage_forecast config/runs/w1b-r1.yaml          # steps 7-8: forecasts, parse
.venv/bin/python -m pipeline.stage_followup config/followups/w1b-r1-f1.yaml  # steps 9-12: reveal + revised forecasts, parse, export
```

| Runner | Steps | Paid API calls | Useful options |
|---|---|---|---|
| `stage_prepare` | 1 fetch both trackers (network) · 2 build frame, outcomes, sample · 3 draft missing statements in one Message Batch · 4 freeze the drafts **without human review** · 5 render prompts and write `run.lock.json` · 6 rebuild from the bundles alone and compare hashes | only step 3, and only for sampled problems without a frozen statement (batch price) | `--no-fetch` (use the archived bundles), `--rounds`, `--poll` |
| `stage_forecast` | 7 call the models (Anthropic models via Message Batches, others directly; parse retries and failed requests resent) · 8 parse into `parsed.csv` | step 7 | `--models`, `--samples N`, `--direct`, `--stub` (offline dry run) |
| `stage_followup` | 9 render and lock the follow-up turn (only once; an existing lock is checked, never rewritten) · 10 call the models · 11 parse · 12 export `dates_long.csv` and `dates_summary.csv` | step 10 | `--direct`, `--stub` |

`stage_forecast` runs every model in the wave unless `--models` is given, so it includes `gpt-6.1-sol` (direct calls, full price, untested adapter). `--stub` replaces the models with a fixed offline answer, which is useful for checking a new config end to end at no cost.

**Statements without human review.** `stage_prepare` freezes every new draft as it is, marks it `auto_approved` with an automatic word-count check (`auto_checks`), and the lock then says `statements_status: auto-approved (no human review)`. Statements that are already frozen are always reused and never overwritten. The 60 statements of wave 1 were reviewed (see Sources), and wave 1b uses the same sample, so it needs no new drafts. For a reviewed set, use the single-step commands below instead of `stage_prepare`.

**Before each new run:** write a new `config/runs/<id>.yaml` with a later `snapshot_date` (S) and the actual `run_date`, keeping the wave, then run `stage_prepare` (it fetches first). If the model set changes so that the latest training cutoff moves, start a new wave (`config/waves/<wave>.yaml`) with a new T0 and seed. Never edit a config, rules file or template that a run has used; copy it to a new version.

<details>
<summary>Single steps (what the runners call)</summary>

```bash
.venv/bin/python -m pipeline.fetch                                     # 1. network: archive both trackers as git bundles
.venv/bin/python -m pipeline.build config/runs/w1b-r1.yaml             # 2. frame, outcomes, sample (stops if statements are missing)
.venv/bin/python -m pipeline.statements submit config/runs/w1b-r1.yaml          # 3a. Message Batch: one draft per missing statement
.venv/bin/python -m pipeline.statements collect config/runs/w1b-r1.yaml --wait   # 3b. -> review/<run>__<batch_id>_review_queue.csv
#    human review: edit approved_text, fill reviewer + checklist_ok=yes (outcomes are not shown in this file)
.venv/bin/python -m pipeline.statements ingest review/<run>__<batch_id>_review_queue.csv   # 4. freeze reviewed statements
.venv/bin/python -m pipeline.build config/runs/w1b-r1.yaml             # 5. render prompts + write runs/<run>/run.lock.json
.venv/bin/python -m pipeline.verify config/runs/w1b-r1.yaml --fresh    # 6. rebuild from bundles alone, compare hashes
.venv/bin/python -m pipeline.run config/runs/w1b-r1.yaml               # 7. direct calls (resumable); --stub for a dry run
.venv/bin/python -m pipeline.run_batch submit  config/runs/w1b-r1.yaml # 7 (alt). Message Batches (Anthropic only, half price)
.venv/bin/python -m pipeline.run_batch collect config/runs/w1b-r1.yaml --wait
.venv/bin/python -m pipeline.parse config/runs/w1b-r1.yaml             # 8. raw/*.json -> parsed.csv (flags, never repairs)
.venv/bin/python -m pipeline.followup build   config/followups/w1b-r1-f1.yaml   # 9. render + lock the follow-up turn (no API)
.venv/bin/python -m pipeline.followup submit  config/followups/w1b-r1-f1.yaml   # 10. Message Batch (or: run [--stub])
.venv/bin/python -m pipeline.followup collect config/followups/w1b-r1-f1.yaml --wait
.venv/bin/python -m pipeline.followup parse   config/followups/w1b-r1-f1.yaml   # 11. -> followups/<id>/parsed.csv
.venv/bin/python -m pipeline.followup export  config/followups/w1b-r1-f1.yaml   # 12. -> dates_long.csv + dates_summary.csv
.venv/bin/python -m unittest discover -s tests -t .                    # fixture and runner tests (no network, no API)
```
</details>

## Runs so far

| Run | Wave | Effort | State |
|---|---|---|---|
| `w1-r1` | `wave1` | vendor default: Claude Opus 5.5 and GPT-6.1 Sol `medium`, Claude Sonnet 5.5 and Claude Fable 5.1 `high` | Claude Opus 5.5 forecasts done (5 samples); follow-up `w1-r1-f1` done |
| `w1b-r1` | `wave1b` | `high` for every model | configured, not run yet |

Both runs use the same T0 (2026-06-30), seed, sample and statements, and the same snapshot S (2026-11-02), so they differ only in effort and in the problem order within each prompt (the order is seeded by the config hash).

## Effort

Effort is set per model in the wave config (`effort`), or for all models at once with `default_effort`; without either it is `high`. The value is sent as `output_config.effort` (Anthropic) or `reasoning.effort` (OpenAI); `default` sends nothing, so the vendor default applies. `high` is accepted by all four models. Vendor defaults, checked on 2026-11-04: Claude Opus 5.5 `medium`, Claude Sonnet 5.5 `high`, Claude Fable 5.1 `high`, GPT-6.1 Sol `medium`. The statement drafter runs at `high`.

## Sources

**Erdős Problems database.** [github.com/teorth/erdosproblems](https://github.com/teorth/erdosproblems), branch `main`, Apache-2.0. The pipeline reads `data/problems.yaml`, which the repository calls its "ground truth": per problem the status (`informal_status`, falling back to `status`), prize and tags. The status at T0 decides whether a problem is open; the status history over first-parent commits gives the solve date (the UTC date of the commit that moved the status into the solved set). Since 2026-10-06 erdosproblems.com no longer displays statuses or solved counts; the repository data is still updated. Archived head: `e8eb305` (committed 2026-11-03).

**Formal Conjectures.** [github.com/google-deepmind/formal-conjectures](https://github.com/google-deepmind/formal-conjectures), branch `main`, Apache-2.0. Lean 4 files under `FormalConjectures/`, one problem per file, grouped into collections (`ErdosProblems`, `GreensOpenProblems`, `Wikipedia`, `Paper`, `Books`, `OEIS`, …). The pipeline reads each theorem's `@[category research open|solved]` attribute, its docstring and its statement, and follows the attribute through the first-parent history. The `ErdosProblems/` files are the second status source for Erdős problems and the source of their statement text. Archived head: `91de790` (committed 2026-11-03).

Both repositories are archived as git bundles in `archive/` (checksums in `archive/manifest.json`), and every later stage reads only from clones made from those bundles.

**Problem statements.** The plain-language statement shown to the models is drafted by Claude Opus 5.5 (effort `high`, `templates/v1/statement_draft.txt`) from the T0 docstring and Lean statement of the problem's headline theorems, and frozen in `statements/`, keyed by unit and T0 file version. The 60 wave-1 statements were reviewed by Claude on the author's delegation, against the T0 Lean files including helper definitions: 33 drafts kept, 27 corrected (missing definitions, attribution, word limit). The review files are in `review/`.

**Model facts.** Model IDs, training cutoffs and effort levels come from the vendors' model pages, checked on 2026-11-04:

| Model | API ID | Training data cutoff | Source |
|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | Jun 2026 | [Anthropic models overview](https://platform.claude.com/docs/en/about-claude/models/overview) |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | Jun 2026 | same |
| Claude Fable 5.1 | `claude-fable-5-1` | Jun 2026 | same |
| GPT-6.1 Sol | `gpt-6.1-sol` | Apr 30, 2026 | [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |

T0 = 2026-06-30 is the latest of these cutoffs (end of month). Anthropic lists the reliable knowledge cutoff as Jun 2026 as well.

**Model outputs.** Anthropic models are called through the Messages API and the Message Batches API, OpenAI models through the Responses API. Every response is archived unchanged in `runs/<run>/raw/` (and `followups/<id>/raw/`), including request parameters and token usage. Thinking text is not returned by these models (the thinking blocks come back empty), so only the answers and the thinking token counts are on record.

## Layout
| Path | Content |
|---|---|
| `config/waves/` | T0, seed, sample sizes, models (id, provider, training cutoff + source, effort), statement drafter |
| `config/runs/` | run id, wave, snapshot date S, date written into the prompt, stages |
| `config/followups/` | follow-ups: base run, models, template, reveal mode. A follow-up continues finished base conversations with one more user turn |
| `rules/rules_v1.yaml` | every selection and resolution rule (status vocabularies, headline regex, exclusions, literature rule) |
| `templates/v1/` | forecast, reveal and statement-draft prompts |
| `templates/followup_v1/` | follow-up prompts (`reveal_solved.txt`: solved problems next to the model's own forecast, sampling design and population solve rate stated, then re-forecast of the still-open ones) |
| `pipeline/stage_*.py` | the three runners |
| `archive/` | git bundles (not committed; keep them) and `manifest.json` with SHA-256 checksums |
| `statements/` | frozen problem statements, keyed by unit and T0 blob SHA (`auto_approved: true` marks unreviewed ones) |
| `review/` | statement-draft batches and review queues |
| `runs/<run>/` | `frame.csv`, `exclusions.csv` (one reason per dropped unit), `outcomes.csv`, `transitions.csv`, `sample.csv`, `sample_log.json`, `prompts.jsonl`, `run.lock.json`, `raw/`, `forecast_batches.json`, `parsed.csv`, `followups/<id>/` (`prompts.jsonl`, `followup.lock.json`, `batches.json`, `raw/`, `parsed.csv`, `dates_long.csv`, `dates_summary.csv`) |
| `work/`, `cache/` | disposable clones (rebuilt from bundles) |

## Rules in force (rules_v1)
- **Units:** Erdős problems (`erdos:N`) use the Erdős DB status, with the Formal Conjectures (FC) file as a second status source and the source of the statement text. Every other FC file is a unit (`fc:<path>`).
- **Open at T0:** the Erdős DB state is one of {open, decidable, falsifiable, verifiable}, and the FC file has at least one *headline* theorem tagged `research open`. Headline means the theorem name has no `.variants.` segment; non-Erdős units need 1–3 headline theorems. Erdős problems without an FC file at T0 are excluded, since there is no statement text. "not provable / not disprovable" problems are excluded. The WrittenOnTheWallII collection is excluded.
- **Solved by S:** the Erdős DB state is one of {proved, disproved, solved, independent}, **or** all FC headline theorems are non-open (union rule). The solve date is the earliest recording: for the Erdős DB, the UTC commit date of the status change; for FC, the commit date of the last headline flip.
- **Literature finds** are dropped from both sampling pools. A find is a commit message saying "already known" or similar, or all references added by the FC flip commit predating T0.
- **Sample:** 10 solved problems drawn by hash rank, then 50 more drawn by hash rank from the rest of the eligible set, split across the strata erdos / fc_named / fc_other in proportion to their sizes. Inclusion probabilities are stored per row.
- Commits are taken from the default branch, first-parent only. A date means the end of that day in UTC.

## Known limitations
- The OpenAI adapter (`pipeline/llm.py`) is untested; no key was available. Batch mode is Anthropic-only, so OpenAI models always use direct calls.
- `config/waves/wave1.yaml` still says the cutoffs were "not re-checked"; it can't be edited because `w1-r1` used it. The values in it are the ones verified above.
- Statements frozen by `stage_prepare` are not reviewed: only their word count is checked, not quantifiers, constants or attribution.
- No refusal fallbacks are used, so a refused request stays refused and is recorded rather than routed to another model.
- The literature rule is a heuristic. `docstring_refs_all_pre_t0` in `outcomes.csv` is a stricter diagnostic; it is not used for selection.
- FC-only solves count (union rule). 31 Erdős problems were solved per FC while the Erdős DB still says open; see `sources_disagree`.
- The Lean parser is regex-based. A per-file check compares the count of `category research` attributes with the declarations parsed, and halts on a mismatch in any file that backs a unit. FC's own `extract_names` cross-check was dropped by decision.
- Tracker dates are dates of recording, not of proof. Curators batch updates (for example, FC marked 14 OpenAI results solved in one commit on 2026-10-11).
