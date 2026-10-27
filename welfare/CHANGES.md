# Welfare dashboard: what changed

Eleven commits on `main` (b353e77..52b9c36), not pushed. 27 files, +4,379 / −205 lines in all. Most of that is copied data and the two assembled pages. The page is AIRO's own panels (Timeline, horizon chart, Capability, Policy levers, FAQ), not the pilot's components: the first five commits used the pilot's, and the last two replaced them.

Checks: the full `pytest` suite passes (441 passed, 26 skipped). AIRO is byte-identical to before in each of these:

- every experiment's `--dry-run` prompt
- the submit tools' JSON
- every scenario block, so every `sha256` stamp
- `index.html`'s data blobs and its rendering: every tab server-renders byte-identically, the Policy levers and Capability charts also with a day of conditional data drawn. Its inlined source changed, because the shared chunks did.
- `results/`
- AIRO's `forecasts.csv`, `rationales.csv` and download-bundle file list

## Commits

| Commit | Step |
|---|---|
| b353e77 | Data, experiment and the two reworded variants |
| 3c16baa | Runner: a set's own questions, and a percentile cell mode |
| 9b3e626 | Welfare view |
| 8ec7da4 | Welfare page and tests |
| f5650a8 | Export: keep the welfare instrument out of AIRO's download |
| 7776a3f | Shared panels: a `percentiles` value kind in AIRO's charts |
| 0d647e6 | Welfare page: AIRO's panels drawn from the welfare log |
| 5166313 | Timeline: each prompt's own percentile bar, in its colour |
| 4f4aee5 | Welfare page: a prompt toggle (mean of five, or one prompt) on Forecasts, Capability and Policy levers |
| 8f65826 | Prompt colours on Policy levers and Capability, an axis per horizon for percentile cells, the "Benefit" title, no cost in the header |
| 52b9c36 | The welfare page is titled AIBO (Automated AI Benefit Outlook) |
| (2026-10-23) | Today's value: a faint dashed line on the Timeline and the horizon chart, per question |
| (2026-10-27) | Two AI-breakthrough questions asked as probabilities in the same call, drawn as AIRO's |
| 25b8b1e (merge) | forecastingresearch/airo main `64d8429` merged in; AIBO adapted to it |

## New files

| File | Lines | What it is |
|---|---|---|
| `data/welfare_questions.json` | 163 | Copy of `welfare/questions.json` |
| `data/welfare_conditions.json` | 410 | Copy of `welfare/welfare_conditions.json` (the combined set under slug `welfare`) |
| `experiments/welfare.toml` | 34 | Copy of `welfare/experiment.welfare.toml` |
| `redlines/views/welfare.py` | 267 | The view, registered as `welfare`. It reads `results/conditional_runs_welfare.jsonl` using the existing pooled and panel filters and the newest protocol, keeps the days on which every model answered all five prompts, and averages each percentile over a model's five calls with `runlog.pool`. It builds the blobs AIRO's panels read, in their shapes: `TIMELINE` (every complete day), `GRAPH1`, `CONDITIONAL`, `CAPABILITY`, `METHOD` and `RATIONALES` (the newest day). It adds `WELFARE` for the header (day, prompts, cost). |
| `web/welfare/manifest.json` | 28 | Page target `welfare.html`, the seven blobs, and AIRO's chunks: head, shell, `19-live-timeline`, `20-live-graph1`, `60-atoms`, `65-rationales`, `75-conditional`, `77-capability`, `79-faq`, `shared/*`. `80-app.jsx` is left out. |
| `web/welfare/00-welfare-data.html` | 1 | The `WELFARE` blob marker |
| `web/welfare/85-welfare.jsx` | 93 | A small app composing AIRO's panels: Forecasts (Timeline on a question rail, then Graph 1), Capability, Policy levers, and an FAQ built from AIRO's items, prompt disclosure and panel list. The header has the run date, cost and the five prompts. |
| `welfare.html` | 2,445 | The assembled page, empty state (every panel shows AIRO's unavailable card) |
| `tests/test_welfare.py` | 346 | 15 tests, fixtures only (listed below) |

## Changed files

| File | +/− | Change |
|---|---|---|
| `code/run_unified.py` | +148 / −55 | Covered in "The runner in detail" below |
| `redlines/experiments.py` | +15 | VARIANTS gains `welfare-independent` and `welfare-two-step`, verbatim from `welfare/variants.json`, with a dated comment. Existing variants are untouched. |
| `redlines/runlog.py` | +15 / −5 | `pool(reps, value="probability")`: averages `"percentiles"` field by field through a small `_mean` helper. The probability path is unchanged. |
| `redlines/views/rationales.py` | +6 / −3 | `build(rows=None)`: the welfare view passes its own unconditional rows. |
| `redlines/views/capability.py` | +9 / −7 | The local `short` label table becomes the module constant `SHORT_LABELS` ("Own 90th percentile", …) so the welfare view can reuse it. Output is unchanged. |
| `redlines/__main__.py` | +36 / −8 | `welfare` added to VIEW_ORDER, BUILDERS, PAGE_ORDER and PAGE_BLOB_BUILDERS. `_build_welfare` injects all the welfare blobs into `welfare.html`, never into `index.html`, and writes no `results/` mirror. Docstrings updated for the second page. |
| `redlines/views/method.py` | +18 / −13 | `build(today, experiment, rows)`: the FAQ's prompt disclosure for another experiment (the welfare baseline prompt). AIRO's output is unchanged. |
| `redlines/views/timeline.py` | +6 / −6 | `condition_legend(variants, experiment)`: the prompt legend for the welfare experiment. |
| `web/demo/60-atoms.jsx` | +37 | `unitFmt`, `unitShift`, `unitTick`, `unitTicks` (a linear axis that need not start at 0), `PctBar` (25th–75th thick, 10th–90th thin) and `PctLegend`. |
| `web/demo/75-conditional.jsx` | +47 / −26 | `percentiles` cells plot levels as expected-deaths cells do (unconditional row on top, line at its ensemble median), on a linear unit axis, each model's dot with its bar, a few pixels apart. The table shows the p50, the 10th–90th and the shift. |
| `web/demo/77-capability.jsx` | +3 / −2 | "risks"/"Risk" come from `CAP.subject` when set; the percentile legend. |
| `web/demo/19-live-timeline.jsx` | +26 / −8 | `percentiles` rows: unit axis, the ensemble's bar at each date, unit formatting, no log switch. Since 2026-10-23 a row that is not a loss row draws its own `q.marks` (dashed lines, included in a percentiles axis; `inside` puts the label at the plot's right edge). AIRO's rows have none. |
| `web/demo/20-live-graph1.jsx` | +20 / −10 | Same for the horizon chart, with the ensemble's bar where AIRO draws its interval. The title and rail heading come from the blob when set. Since 2026-10-23 it draws `q.marks` as the Timeline does (`inside`: label centred above the line). |
| `web/demo/65-rationales.jsx` | +6 / −5 | The rationale's forecast table takes a number format (default: AIRO's percent). |
| `index.html` | +139 / −51 | Reassembled because the chunks above changed. No blob changed, and the page renders the same. |
| `redlines/export.py` | +18 / −4 | `OTHER_PAGES` and `airo_file()` keep the welfare set, logs, run folder and smoke files out of AIRO's CSVs and bundle. Without this the first welfare run would have crashed `build --views csv` and changed AIRO's download. |
| `tests/test_experiments.py` | +4 / −1 | "Every variant is an AIRO condition" becomes "every variant is asked by AIRO or by welfare". |
| `tests/test_publish_views.py` | +5 / −1 | `welfare` is exempt from "publish_dashboard.sh rebuilds every view"; AIRO's publish does not build or serve it. |

## The runner in detail (`code/run_unified.py`)

- `load_questions(path)`: a scenario set that names `questions` loads that file and returns `load_batch`'s tuple. `run()` uses it instead of the ladder and cross-cutting files.
- `build_prompt`: if a question has no severity, the heading has no severity label. It prints `unit_text`, and writes each horizon as `2050 (the year 2050)` when the question carries `horizon_meaning`.
- `build_prompt_joint`: if questions carry meanings, the horizons line lists them bare and adds "and what each means for it". It also fills the new `{deliver}` and `{meant}` template fields.
- `CELL_MODES`, `PROBABILITY`/`PERCENTILES`, `PERCENTILE_FIELDS` and `value_mode(spec)` set the mode, taken from the question set's `percentiles`.
- `_cells_schema`, `submit_cells_tool`, `submit_tool_joint`: the cell key is `probabilities` or `percentiles` (five numbers per condition id).
- `clean_percentiles`: five finite, non-decreasing numbers within the question's `bounds`. It reuses `clean_elicit` and adds a finiteness check.
- `clean_forecasts_joint(..., mode, bounds)`: entries become `{"horizon", "percentiles": {...}}`.
- `scenarios_block(_grouped)`: the Step 2 sentence reads "five percentiles (p10, …, p90) under each of 14 conditions". All three block shapes take the mode.
- `minimal_joint_prompt`: the anchor is the regex `MINIMAL_DELIVERY`, which matches the delivery paragraph in either mode.
- `run_one_joint`: the mode reaches the tools, `take_cells`, the cleaner and the scenario-block hash.
- `run()`: the log line says "700 numbers" for welfare.

## Tests (`tests/test_welfare.py`)

1. The welfare set equals the combined set on every shared key, so drift in the copy fails.
2. The experiment has five manual pooled prompts; `due welfare` lists them, and a Wednesday's due list does not.
3. Questions render with no severity label and with units, horizon meanings and the horizons sentence.
4. Step 2 and the delivery paragraph ask for five percentiles (700 numbers).
5. Each variant lands immediately before the delivery paragraph.
6. The tools ask for five numbers per condition.
7. Percentile cleaning keeps a good cell, and a stringified cell.
8. Percentile cleaning drops missing, unordered, out-of-bounds, NaN, infinite and boolean values, and cells outside the question's horizons.
9. Probability mode is unchanged: cleaning, schema and `pool`.
10. AIRO's prompt still asks for probabilities.
11. `run_one_joint` writes percentile rows.
12. AIRO's download leaves the welfare files out.
13. The view pools five calls per model into AIRO's blob shapes: Policy levers, Capability, Timeline, Graph 1, the FAQ prompt and the rationales.
14. An incomplete day gives way to the last complete one; the Timeline keeps every complete day; no rows gives empty panels.
15. The page is AIRO's panels, and assembles with and without data.

## Known differences from `welfare/prompts/`

- The ECI history is the repo's snapshot (2026-10-01), not 2026-10-21. Re-copy the combined set if the server has a newer one.
- The horizons sentence wraps at a different point.
- `eci_forecast`'s maximum is the set's own 1000, as AIRO sends, rather than 1e9.

## Today's value (2026-10-23)

Each question in `data/welfare_questions.json` has a `today` entry (`value`, `year`, `source`; listed under `provenance.added_here`, explained in `provenance.today_note`). The view passes it as the question's `marks`, and the Timeline and the horizon chart draw it as a faint dashed line labelled "Today (period): value". The models never see it: the welfare dry-run prompt is byte-identical with and without it.

The values are on the series and definitions the questions resolve on, fetched on 2026-10-23: life expectancy in 2026, and growth as the questions measure it, annualized over the latest five-year period, 2022–2026:

| Question | Line | Kind | Latest actual | Source |
|---|---|---|---|---|
| U.S. life expectancy | 79.8 | UN medium-variant projection | 79.3 (2023) | UN WPP 2024 via [Our World in Data](https://ourworldindata.org/grapher/life-expectancy-unwpp) |
| High-income life expectancy | 81.9 | UN medium-variant projection | 81.4 (2023) | same |
| Low-income life expectancy | 65.5 | UN medium-variant projection | 64.9 (2023) | same |
| Advanced economies growth | 2.16% (2022–2026) | ((1+g1)…(1+g5))^(1/5) − 1 over 3.0, 1.7, 2.0, 2.0, 2.1; 2026 projected | 2.0% (2025) | IMF WEO October 2026, Online Table A1 |
| EMDE growth | 4.30% (2022–2026) | the same over 4.3, 4.5, 4.5, 4.5, 3.7; 2026 projected | 4.5% (2025) | same |

- Life expectancy is period life expectancy at birth, as the questions define it. OWID's income groups may differ slightly from the World Bank FY2026 list the questions fix; the pilot's rationale names Russia as one difference.
- Growth uses the questions' formula on the IMF's PPP-weighted group aggregates, from the published one-decimal annual rates. 2022 is the newest start that ends the window in 2026; 2021–2025 would include the pandemic rebound (6.2% and 7.0%).
- Refresh these when the UN publishes WPP 2026 (OWID expects to update in 2027) or the IMF publishes the April 2027 WEO.

## AI breakthroughs (2026-10-27)

Two benefit questions, answered as **probabilities** on AIRO's six horizons (within 6 and 12 months, by 2028, 2030, 2050, 2100), in the same welfare call and five-prompt rotation as the percentile questions:

- **`ai:pancreatic`:** AI-enabled treatments raise the all-stage five-year relative survival of U.S. pancreatic cancer patients above 50%. It resolves on the cohort diagnosed in the 12 months before the resolution date, as SEER eventually measures it, so the five-year publication lag doesn't make the near horizons impossible. Treatment only; earlier detection alone doesn't count. Today: 13.7% (SEER, 2016–2022 diagnoses; ovary 52.0%, colorectal 65.4%, lung 29.5%).
- **`ai:garments`:** a commercially operating line in a low- or lower-middle-income country makes a mainstream garment, sewn and assembled mainly by AI-directed robots, at 1 million units a year or more, at a fully loaded unit cost no higher than manual production at that country's garment wages.

Both use AIRO's criteria clauses (`data/autoarc_crosscutting.json`): the Dafoe definition, the but-for "substantial involvement of AI" test, perfect knowledge, the rolling resolution date and an expert panel. They are a new first group (AI BREAKTHROUGHS) in the prompt and on every rail. The life expectancy and growth questions, their horizons and their charts are unchanged; every percentile entry in every blob is identical to before.

| File | Change |
|---|---|
| `data/welfare_questions.json` | The group, the two questions (`value_kind: "probability"`), and AIRO's `rolling` table so `6mo`/`12mo` sort, date and label as AIRO's do. |
| `code/run_unified.py` (shared) | `question_mode(q, spec)` reads a question's own `value_kind`. `value_mode` returns `MIXED` only when a set's questions disagree. In a mixed set the cell schema carries both `probabilities` and `percentiles` (requiring neither), `take_cells` and `clean_forecasts_joint(modes=)` take each question's own key (a probability outside [0,1] is dropped), Step 2 and the delivery paragraph ("Deliver the forecasts …") name both, and `cell_numbers` counts the total per question (868 numbers, was 700). When questions carry `horizon_meaning`, the Horizons line still dates the rolling horizons. **AIRO is untouched:** its sets are one mode, so the airo, axes and paperaxes dry-runs and the submit tools' JSON are byte-identical. |
| `redlines/views/welfare.py` | Probability questions go through AIRO's own builders, unchanged: `views.conditional._variant` for Policy levers and Capability (tabs 2030, 2050, 2100; Capability's bars take the welfare labels and ECI levels), `views.timeline._prob_row` for the Timeline, and graph1's series arithmetic with `views.graph1._ensemble` for the horizon chart. Prompt dots stay on percentile cells only (AIRO's probability rows draw none). |
| `web/welfare/manifest.json` | Adds `../demo/10-mock-graph1.jsx`, which holds `niceMax`, read by a probability row's linear axis (index.html already loads it). |
| `web/welfare/85-welfare.jsx` | Subtitle and FAQ: two probability questions, five percentile ones. |
| `welfare/tools/preview.py` | Invented Oct 22 probabilities for both questions (per condition and prompt, on the logit). The pilot didn't ask them, so there's no Oct 1 point. |
| `tests/test_welfare.py` | 7 questions, the mixed prompt and tools, mixed cleaning, rolling horizons, and the AI questions first in AIRO's probability shapes. |

The full panel's run is still 20 calls. Each call asks 168 more numbers (868 instead of 700), so expect a somewhat higher price per call than the pilot's $16.85.

## On upstream AIRO 64d8429 (2026-10-27)

Upstream's 42 commits since the fork point (`2931769`) are merged into `main` (`25b8b1e`; `upstream` remote, a merge since `main` is pushed): shared Tippy tooltips, the Timeline rework, prompt-aware model rationales, pi-only calls, production releases and the recent-news shadow. Nothing was sent to AIRO.

Conflicts were resolved to upstream's code with the fork's opt-in additions re-applied: `code/run_unified.py` (the cell mode through upstream's `call_tools` call and `news_cache` block), `views/timeline.py` (`condition_legend(experiment=)` on upstream's publish filter), `views/rationales.py` (`build(rows=)`), `tests/test_experiments.py`, and the chunks `19-live-timeline.jsx`, `20-live-graph1.jsx` and `65-rationales.jsx` (upstream's `PointTooltip` and rationale panel, with the fork's prompt end label, percentile band line, horizon header and an opt-in `fmt`).

AIBO's adaptations:

- `web/welfare/manifest.json` adds `../shared/tooltips.jsx`.
- The welfare test and the preview patch `ru.call_tools` (upstream removed `loop_for`).
- The rationale calls of welfare's two reworded prompts take AIRO's condition labels.
- Shared, opt-in: `views/rationales.py` keeps a percentile cell's median in a call's forecasts map.

AIRO equals upstream:

- the `airo`, `axes` and `paperaxes` prompts;
- `index.html`'s data blobs;
- every tab's server render, and Policy levers and Capability filled with a day of data;
- upstream's CI reproduce check passes.

Nothing upstream runs or publishes welfare (`cadence = "manual"`; `production.py` publishes only `index.html` and the downloads), and `data/combined_conditions.json` did not change, so the welfare copy needs no re-copy.

## The preview

[`welfare-preview.html`](../welfare-preview.html), at the repo root: download it and open it in a browser. The Oct 1 forecasts are the welfare pilot's one real Opus 5.5 call. **Every Oct 22 forecast is invented**, and so is every AI-breakthrough answer, to show the layout with five prompts: the Timeline, Policy levers, Capability, the horizon chart and the ECI forecast. No model was run for it. `welfare.html` is the real page and stays empty until the first live run.

[`welfare-previews/`](../welfare-previews/) keeps each day's last committed version as `welfare_preview_YYYYMMDD.html` (22, 23 and 27 Oct 2026); each carries its own note on which data is invented. `welfare/tools/` regenerates it (`preview.py`, deterministic) and renders pages without a browser (`ssr.js`, `svgpng.py`). [HANDOFF_CONTINUE.md](HANDOFF_CONTINUE.md) is the brief for whoever continues.

Not committed: `.vscode/`.
