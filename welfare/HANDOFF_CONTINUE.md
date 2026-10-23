# Continuing the welfare dashboard (AIBO)

You are picking up a working welfare dashboard built on AIRO's pipeline in this repo (`/home/s/aibo`, the Python package `redlines`). Your job is to tinker with it and improve it, following the user's requests. The first brief is [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md); what was built against it, file by file, is in [CHANGES.md](CHANGES.md). Read both before changing anything.

## The rule that matters most

**Change as little of AIRO's original code as possible, and reuse as much of it as possible.** This rule is now stricter than in the first brief. In order of preference:

1. **Change welfare-owned files only.** These are `redlines/views/welfare.py`, `web/welfare/*`, `tests/test_welfare.py`, `welfare/` (including `welfare/tools/`), `data/welfare_*.json` and `experiments/welfare.toml`. Most changes belong here, as data shaped for AIRO's existing components.
2. **If an AIRO component must behave differently, give it an optional parameter or a blob field that defaults to today's behaviour.** Existing examples are `ctx`, `prompt`, `valueKind: "percentiles"`, `G1.title`, `CAP.subject` and `fmt`. Never fork or copy an AIRO component into `web/welfare/`.
3. **If there is a third way, ask the user first.** That includes editing AIRO's behaviour, its texts, its tests, or anything shared that changes how `index.html` renders.

Before adding code, look for an existing function, field or component that nearly fits. Note every change to a shared file in your commit message and in [CHANGES.md](CHANGES.md).

## Hard constraints

- **No paid calls.** Don't run anything that calls a model, searches the web, elicits, publishes or deploys:
  - `code/run_unified.py` without `--dry-run`;
  - `code/cron_run.sh`, `code/publish_dashboard.sh` or `code/publish_public.sh`;
  - anything that loads keys.
- **Credentials:** prefix every runner or CLI command with `REDLINES_ENV_FILE=/dev/null`. Never read, source or print `.env` or any credential file.
- **AIRO must not move:**
  - Leave unchanged `results/`, `data/combined_conditions.json`, AIRO's experiments and VARIANTS, AIRO's prompt and every `condition_sha256`.
  - `index.html` may change only through `python -m redlines assemble`, and only in its inlined source, never in a data blob. It must render the same as before (see "Checking AIRO did not move").
- **The welfare data must not reach AIRO's download.** `redlines/export.py` `airo_file()` keeps it out.
- **Filesystem:** stay inside this repo, your scratchpad and your memory directory.
- **Git:** work on `main` (this is the user's fork, SimXem/aibo) and commit in logical steps, ending messages with the co-author line. You can't push, because the shell has no GitHub credentials; the user pushes from VS Code.
- **Style:** match the surrounding code. Comments are dated and say why, the build stage is stdlib only, and existing names stay as they are.

## How it fits together

```
data/welfare_questions.json      5 questions, 10 question x horizon cells, five percentiles each ("percentiles" key)
data/welfare_conditions.json     AIRO's combined set copied verbatim, slug "welfare" (a test fails if the copy drifts)
experiments/welfare.toml         5 pooled prompts (none, independent, recent, critical, two-step), cadence manual
        |
code/run_unified.py --experiment welfare
        |   load_questions() when the set names `questions`; CELL_MODES / value_mode() switch probability <-> percentiles
        |   through the tools, take_cells, clean_forecasts_joint (clean_percentiles), Step 2 and the delivery paragraph
        v
results/conditional_runs_welfare/<run>.jsonl   (+ results/welfare_runs/)   forecasts: [{"horizon", "percentiles": {p10..p90}}]
        |
redlines/views/welfare.py  build() -> blobs in AIRO's shapes and names:
        |   TIMELINE (every complete day), GRAPH1, CONDITIONAL, CAPABILITY (newest complete day; each with byPrompt),
        |   METHOD, RATIONALES, plus WELFARE (day, prompts) for the header
        |   pooling = runlog.pool(rows, "percentiles"): each percentile's mean over a model's five calls
        |   "complete day" = every model that answered answered all five prompts
        v
web/welfare/manifest.json -> welfare.html     AIRO's chunks (19-live-timeline, 20-live-graph1, 60-atoms,
                                              65-rationales, 75-conditional, 77-capability, 79-faq, shared/*)
                                              + 85-welfare.jsx (the small App: tabs, prompt toggle, FAQ)
```

**The `percentiles` value kind in AIRO's shared chunks.** All of it is opt-in by data, so AIRO's probability and loss paths are untouched:
- **`60-atoms.jsx`:** `unitFmt`, `unitShift`, `unitTick`, `unitTicks` (a linear axis that need not start at 0), `PctBar` (25th–75th thick, 10th–90th thin) and `PctLegend`.
- **`75-conditional.jsx`:** percentile cells plot levels the way expected-deaths cells do, with each model's bar behind its dot.
  - The axis is per horizon.
  - `promptId` tints the bars in that prompt's colour.
  - `b.prompts` / `cell.baselinePrompts` give each prompt's median as a coloured dot (`TL_CONDITIONS` colours).
  - `ConditionalPanel({ ctx })` and `PromptLegend`.
- **`77-capability.jsx`:** `CapabilityPanel({ ctx })`, `CAP.subject`.
- **`19-live-timeline.jsx`:** percentile rows (ensemble band, unit axis), `TimelinePanel({ prompt })` (one prompt's dot and bar on its date), `q.variantBands`.
- **`20-live-graph1.jsx`:** `LiveGraph1({ ctx })`, `HorizonChart` takes `G`, `q.band`, `G1.title` / `G1.railTitle`.
- **`65-rationales.jsx`:** `ForecastRationales({ fmt })`.

**Elsewhere in AIRO's Python:**
- `runlog.pool(value=)`;
- `views/rationales.build(rows=)`;
- `views/method.build(experiment=, rows=)`;
- `views/timeline.condition_legend(experiment=)`;
- `views/capability.SHORT_LABELS`.

In the CLI, `welfare` is in VIEW_ORDER, BUILDERS, PAGE_ORDER and PAGE_BLOB_BUILDERS. `build --views welfare` writes only to `welfare.html`, and `publish_dashboard.sh` neither builds nor serves it.

## Working loop

```
# tests: there is no pytest on the system python; make a venv in your scratchpad
python3 -m venv $SCRATCH/venv && $SCRATCH/venv/bin/pip install -q "pytest>=8" "openpyxl>=3.1"
REDLINES_ENV_FILE=/dev/null $SCRATCH/venv/bin/python -m pytest -q -p no:cacheprovider        # ~3 min; 441 passed, 26 skipped
REDLINES_ENV_FILE=/dev/null $SCRATCH/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_welfare.py

# the welfare prompt, without calling a model (main() returns before load_keys)
REDLINES_ENV_FILE=/dev/null python3 code/run_unified.py --experiment welfare --dry-run

# pages: welfare.html stays committed in its empty state (no welfare run yet)
REDLINES_ENV_FILE=/dev/null python3 -m redlines assemble --pages demo,welfare
REDLINES_ENV_FILE=/dev/null python3 -m redlines build --views welfare      # must equal what assemble wrote

# the preview the user shares (welfare-preview.html, committed): Oct 1 real pilot, Oct 22 INVENTED
REDLINES_ENV_FILE=/dev/null python3 welfare/tools/preview.py               # deterministic
```

Never run `python -m redlines build` without `--views`. It rewrites AIRO's mirrors in `results/` and the download files. To check the full build, run it in a `git archive HEAD` export inside your scratchpad.

## Seeing what you changed

The pages are React through Babel in the browser, and you have no browser. Render them yourself instead:

1. Download into a folder in your scratchpad, from unpkg.com:
   - `@babel/standalone@7.29.0/babel.min.js`
   - `react@18.3.1/umd/react.development.js`
   - `react-dom@18.3.1/umd/react-dom-server-legacy.browser.development.js`
2. Server-render one or more tabs, optionally with a prompt (`"forecasts"`, `"capability&prompt=two-step"`, `"conditional&prompt=critical"`, `"faq"`), and probe for text or dump the HTML:
   - `node welfare/tools/ssr.js <dl> welfare-preview.html conditional "conditional&prompt=critical"`
   - `PROBES="a|b"` looks for text; `TEXT=400` prints the start; `DUMP=prefix` writes the HTML.
3. Look at a chart: `pip install cairosvg` into your venv, then `python welfare/tools/svgpng.py welfare-preview.html <dump>.html <n> out.png`. `n` is the index of the chart's `<svg>`; the big charts have `viewBox="0 0 880…"` or `"0 0 900…"`. Then Read the PNG.

Do look. The prompt dots overlapping and the 2050 rows squeezed against 2100's axis were caught only this way.

## Checking AIRO did not move

Do this after any change to a shared chunk or to AIRO's Python:

1. Run `assemble --pages demo`. Then `git diff index.html | grep '^[-+]' | grep -v '^+++\|^---' | grep -c 'window.__'` must be `0`.
2. Server-render `git show <base>:index.html` and the new `index.html` for `forecasts capability conditional faq` with `DUMP`, then `cmp` each pair. Each pair must be identical.
3. AIRO's Policy levers and Capability tabs currently show "awaiting a run", because the current instrument has no complete day yet. Exercise the charts with data too:
   - Build cells with `redlines.views.conditional._variant` on the last day of `results/conditional_runs_combined.jsonl` (2026-09-18), for `group_view(spec, "policy")` and `"capability"`.
   - Put them into the `_blobs_for_demo()` blobs.
   - `hydrate_page` with the old chunks (a `git archive <base>` export's `web/demo`) and with the new ones, render both, and compare.
4. Also compare the dry-runs of AIRO's experiments (`airo`, `axes`, `paperaxes`) before and after any runner change.

## Open items and known rough edges

These are candidates for your work. Ask the user before changing AIRO wording.

- **Unavailable cards:** empty panels read AIRO's "Awaiting a complete four-model run under the revised counting rules." Fixing this means a shared atom (`ForecastUnavailable` in `60-atoms.jsx`).
- **"repeats" wording:** Policy levers' run line says "N models × 5 repeats", but the five are prompts.
- **FAQ:** it says "AIRO's instrument" and "AIRO's" ensemble on purpose; both are the risk dashboard's.
- **ECI snapshot:** `data/welfare_conditions.json` carries the ECI history of 2026-10-01. Before a live run, re-copy the combined set if the server has a newer one; the drift test fails until you do.
- **No per-question rationales:** the minimal instrument has no debrief, so the rationale panel shows each call's batch rationale.
- **Timeline starts empty:** one point per question until a second welfare run.
- **Not served anywhere:** `welfare.html` isn't published by any script. Wiring that in is deploying, so it's the user's decision.
- **Today's values:** the dashed lines' numbers in `data/welfare_questions.json` (`today`) are life expectancy in 2026 (UN WPP 2024 via OWID) and growth annualized over 2022–2026 (IMF WEO October 2026), fetched 2026-10-23 (see CHANGES.md). Refresh them when either source updates.
- **Invented preview data:** `welfare-preview.html` contains invented Oct 22 data, stated in its header and in `CHANGES.md`. Keep it that way.

**First live run.** This is the user's call, and it costs money:
- One model: `python code/run_unified.py --experiment welfare --models "Opus 5.5"` then `python -m redlines build --views welfare`. That's 5 calls, about $85 at the pilot's price.
- The whole panel (Opus 5.5, GPT-6 Astra, Sonnet 5.5, Fable 5.1) is 20 calls, roughly $340.
