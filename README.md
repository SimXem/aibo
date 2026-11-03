# Math-problem forecasting pipeline

Models get a list of math problems that were open at a reference date T0 and predict when each will be solved. They are then shown what actually happened between T0 and a snapshot date S. A third stage (a follow-up question) is a placeholder for now.

Every run is a pure function of a config plus archived tracker history. Rerunning an old config reproduces the frame, sample, outcomes and prompts byte for byte (`pipeline.verify`). Model outputs can't be reproduced, so every raw response is archived instead.

## Setup (Linux)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
```

Commands below call `.venv/bin/python` directly; after `source .venv/bin/activate` you can write plain `python` instead.

## Workflow

```bash
.venv/bin/python -m pipeline.fetch                                  # 1. network: archive both trackers as git bundles
.venv/bin/python -m pipeline.build config/runs/w1-r1.yaml           # 2. frame, outcomes, sample (stops if statements are missing)
.venv/bin/python -m pipeline.statements submit config/runs/w1-r1.yaml          # 3a. Message Batch: one draft request per missing statement
.venv/bin/python -m pipeline.statements collect config/runs/w1-r1.yaml --wait   # 3b. -> review/w1-r1__<batch_id>_review_queue.csv
#    a reviewer edits approved_text, fills reviewer + checklist_ok=yes (outcomes are not shown in this file)
.venv/bin/python -m pipeline.statements ingest review/w1-r1__<batch_id>_review_queue.csv   # 4. freeze approved statements
.venv/bin/python -m pipeline.build config/runs/w1-r1.yaml           # 5. render prompts + write runs/<run>/run.lock.json
.venv/bin/python -m pipeline.verify config/runs/w1-r1.yaml --fresh  # 6. rebuild from bundles alone, compare hashes
.venv/bin/python -m pipeline.run config/runs/w1-r1.yaml             # 7. call models (resumable); --stub for a dry run
.venv/bin/python -m pipeline.run_batch submit config/runs/w1-r1.yaml --models claude-opus-5-5   # 7 (alt). same, via Message Batches (Anthropic only, half price)
.venv/bin/python -m pipeline.run_batch collect config/runs/w1-r1.yaml --wait  #    -> raw/*.json; run submit again for parse retries / failed requests
.venv/bin/python -m pipeline.parse config/runs/w1-r1.yaml           # 8. raw/*.json -> parsed.csv (flags, never repairs)
.venv/bin/python -m unittest discover -s tests -t .                 # fixture tests
```

API keys go in `.env` (`ANTHROPIC_API_KEY=...`, `OPENAI_API_KEY=...`). The file is git-ignored, and `.claude/settings.json` denies Claude read and edit access to it.

**Before each new run:** run `fetch`, then write a new `config/runs/<id>.yaml` with a later `snapshot_date` (S), keeping the same wave. If the model set changes so that the latest training cutoff moves, start a new wave (`config/waves/<wave>.yaml`) with a new T0 and seed. Never edit a config, rules file or template that a run has used; copy it to a new version.

## Layout
| Path | Content |
|---|---|
| `config/waves/` | T0, seed, sample sizes, models (id, provider, training cutoff + source, effort), statement drafter |
| `config/runs/` | run id, wave, snapshot date S, date written into the prompt, stages |
| `rules/rules_v1.yaml` | every selection and resolution rule (status vocabularies, headline regex, exclusions, literature rule) |
| `templates/v1/` | forecast, reveal and statement-draft prompts |
| `archive/` | git bundles (not committed; keep them) and `manifest.json` with SHA-256 checksums |
| `statements/` | frozen, reviewed problem statements, keyed by unit and T0 blob SHA |
| `runs/<run>/` | `frame.csv`, `exclusions.csv` (one reason per dropped unit), `outcomes.csv`, `transitions.csv`, `sample.csv`, `sample_log.json`, `prompts.jsonl`, `run.lock.json`, `raw/`, `forecast_batches.json` (batch mode), `parsed.csv` |
| `work/`, `cache/` | disposable clones (rebuilt from bundles) |

## Rules in force (rules_v1)
- **Units:** Erdős problems (`erdos:N`) use the Erdős DB status, with the Formal Conjectures (FC) file as a second status source and the source of the statement text. Every other FC file is a unit (`fc:<path>`).
- **Open at T0:** the Erdős DB state is one of {open, decidable, falsifiable, verifiable}, and the FC file has at least one *headline* theorem tagged `research open`. Headline means the theorem name has no `.variants.` segment; non-Erdős units need 1–3 headline theorems. Erdős problems without an FC file at T0 are excluded, since there is no statement text. "not provable / not disprovable" problems are excluded. The WrittenOnTheWallII collection is excluded.
- **Solved by S:** the Erdős DB state is one of {proved, disproved, solved, independent}, **or** all FC headline theorems are non-open (union rule). The solve date is the earliest recording: for the Erdős DB, the UTC commit date of the status change; for FC, the commit date of the last headline flip.
- **Literature finds** are dropped from both sampling pools. A find is a commit message saying "already known" or similar, or all references added by the FC flip commit predating T0.
- **Sample:** 10 solved problems drawn by hash rank, then 50 more drawn by hash rank from the rest of the eligible set, split across the strata erdos / fc_named / fc_other in proportion to their sizes. Inclusion probabilities are stored per row.
- Commits are taken from the default branch, first-parent only. A date means the end of that day in UTC.

## Known limitations and unverified items
- Model IDs and training cutoffs in `config/waves/wave1.yaml` come from the study brief and were not re-checked. `gpt-6.1-sol` is a guess at the ID string.
- The OpenAI adapter (`pipeline/llm.py`) is untested; no key was available.
- `effort: default` means each model runs at its vendor default (Claude Opus 5.5: medium; Sonnet 5.5: high). This is a design choice that affects the forecasts.
- No refusal fallbacks are used, so a refused request stays refused and is recorded rather than routed to another model.
- The literature rule is a heuristic. `docstring_refs_all_pre_t0` in `outcomes.csv` is a stricter diagnostic; it is not used for selection.
- FC-only solves count (union rule). 31 Erdős problems were solved per FC while the Erdős DB still says open; see `sources_disagree`.
- The Lean parser is regex-based. A per-file check compares the count of `category research` attributes with the declarations parsed, and halts on a mismatch in any file that backs a unit. FC's own `extract_names` cross-check was dropped by decision.
- Tracker dates are dates of recording, not of proof. Curators batch updates (for example, FC marked 14 OpenAI results solved in one commit on 2026-10-11).
