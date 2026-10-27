# Welfare instrument: prompts and spec

This folder has what is needed to build a welfare dashboard on AIRO's pipeline. Today's dashboard asks catastrophe probabilities. This one asks for **five percentiles** (p10, p25, p50, p75, p90) on life expectancy and GDP growth, under the same 14 scenario conditions and the same five prompt variants. Since 2026-10-22 it is wired in: [CHANGES.md](CHANGES.md) lists what changed, file by file. Since 2026-10-27 the live set (`data/welfare_questions.json`) also asks two AI-breakthrough questions as probabilities; the files in this folder describe the original five. [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md) is the build brief: reuse AIRO's pipeline, and add code only where percentiles differ from probabilities.

## Files

| File | What it is |
|---|---|
| [questions.json](questions.json) | The 5 questions (10 question x horizon cells). Text and resolution criteria are copied verbatim from the published welfare pilot (`welfare-v1-pilot`, 2026-10-01). Units, bounds and horizon meanings were added here. |
| [variants.json](variants.json) | The five prompt variants. `independent` and `two-step` are reworded for welfare questions; `recent` and `critical` are AIRO's, unchanged; `none` adds nothing. |
| [welfare_conditions.json](welfare_conditions.json) | AIRO's combined scenario set (the 14 conditions and the `eci_forecast` step), copied verbatim under slug `welfare` and pointing at the welfare questions. Its own slug is what sends welfare rows to their own logs. |
| [experiment.welfare.toml](experiment.welfare.toml) | `experiments/welfare.toml`, ready to install. It loads once the two welfare variant keys are in VARIANTS. |
| [render_prompts.py](render_prompts.py) | Renders the reference prompts and tools below. Stdlib only, makes no API calls: `python3 welfare/render_prompts.py` |
| [prompts/welfare-*.txt](prompts/) | The full prompt for each variant, as it would have been sent on 2026-10-21. This is the intended content; the live runner uses its own layout. |
| [prompts/tools.json](prompts/tools.json) | `submit_cells` and `submit_forecast` with a percentile cell schema. |
| [reference/airo-v11-minimal-prompt-skeleton-2026-10-21.txt](reference/airo-v11-minimal-prompt-skeleton-2026-10-21.txt) | The prompt AIRO actually sent on 2026-10-21 (Opus 5.5, variant `none`), with 72 of its 73 question blocks cut. Its CONDITIONS block is the source of the welfare prompts' block. |
| [reference/epoch_capabilities_index_2026-10-21.csv](reference/epoch_capabilities_index_2026-10-21.csv) | The ECI snapshot behind that block. The repo's `data/` stops at 2026-10-01. |
| [reference/welfare-page-pilot.jsx](reference/welfare-page-pilot.jsx) | The pilot page's own React components (charts, table, rationales, app), extracted verbatim. |
| [reference/welfare-pilot-blob-2026-10-01.json](reference/welfare-pilot-blob-2026-10-01.json) | The pilot page's `window.__WELFARE__` data. It is the target shape for the new view's blob. |

All `reference/` files come from the public site (`welfare.html`, `redlines-data.zip`), fetched 2026-10-22. The pilot's own generator (`code/build_welfare_page.py`) and its run log are not in this repo or in the public bundle.

## How the prompt is put together

1. The AIRO minimal head, worded for 5 questions and 14 conditions.
2. Two question groups, LIFE EXPECTANCY and GLOBAL ECONOMIC GROWTH. Each question lists its horizons, its unit and its resolution criteria.
3. AIRO's combined-v11 CONDITIONS block, verbatim, with one change: Step 2 asks for five percentiles per condition instead of one probability. The block contains:
   - the ECI definitions and history, and Step 1, the `eci_forecast` question;
   - the unconditional condition;
   - 8 LEAP Wave 12 policy conditions;
   - 5 capability conditions (eci_p10 to eci_p90).
4. The horizons line.
5. The variant's paragraph, if the variant has one.
6. The delivery paragraph: 10 cells x 14 conditions x 5 percentiles = 700 numbers, plus `eci_forecast`.

## Open choices (defaults used here)

- **"How risk changes."** LEAP's policy instruction ends: "We want your forecast of how risk changes as a result of the policy's implementation, not vice versa." It is kept verbatim, as the pilot kept it, so the policy text stays identical to AIRO's. A welfare-worded version would break that identity.
- **No debrief.** The minimal instrument has no debrief turn, so a model's rationale is its single `submit_forecast` rationale.
- **Pooling.** A model's number is the mean of each percentile across its five calls on one day. This mirrors `redlines.runlog.pool`.
