# AIRO — Automated AI Risk Outlook

AIRO is a standing panel of frontier language models that forecasts AI-related
catastrophic-risk questions, re-elicited on a twice-weekly schedule so the forecasts
form a time series rather than a snapshot. It is a project of the
[Forecasting Research Institute](https://forecastingresearch.org) (FRI). The
live dashboard is at **https://airo.forecastingresearch.org**, and an accompanying white paper
(linked from the dashboard's FAQ) describes the method and results. The
questions are FRI's Auto-ARC set; the models answer them under grounded,
agentic web search, and the same models are benchmarked for calibration and
skill on ForecastBench and on two simulators, and asked for forecasts
conditional on policy and capability scenarios. The project was called
"Redlines" and then "Auto-ARC" before it became AIRO, so the Python package is
still named `redlines` and some file and blob names carry the old names.

## What's here

One page, `index.html`, assembled from the chunks under `web/demo/`. Its panels:

- **Timeline** — the lead panel of the Forecasts tab: how the bottom-line
  forecasts move between elicitation dates. Before 2026-10-21 only the ensemble
  median is shown; hovering or selecting it reveals the models as ink-gray dots.
  From 2026-10-21 each pooled prompt condition has a consistently colored dot
  for its panel median, with the prompt and model answers available on hover,
  click, tap, or keyboard selection. The legend identifies conditions rather
  than models. The series starts at the agentic-harness cutover on
  2026-09-02 (`redlines/runlog.py::SERIES_START`); earlier elicitations stay in
  the run log and the download but are not drawn on the same axis. A model that
  leaves the panel keeps its historical answers in the details. The five pooled
  prompts' mean is each model's published number. The unpooled sixth call stays
  in the download and is never drawn (`experiments/airo.toml`: `pooled`).
- **Graph 1** — the current forecasts by horizon: the cross-cutting questions
  (general catastrophe, AI catastrophe, human disempowerment) and one
  expected-loss row per AI-related incident cause, with prior human panels
  (XPT, LEAP) as hollow diamonds where a comparable question exists.
- **Graph 2** — the incident severity ladders: probability against a severity
  threshold for four AI-related incident causes, on two charts since 2026-10-19
  — one for deaths (or equivalent morbidity), one for economic damages, each
  rung a separate question on each (`docs/severity-legs-2026-10-19.md`; since
  2026-10-21 damages exclude monetized mortality,
  `docs/damages-without-mortality-2026-10-21.md`) — plus a
  resolution-free coherence check (P of a stronger event must never exceed P of
  a weaker event it implies).
- **Data bank** — the bottom-line forecasts collated with their resolution
  criteria; the download bundle (every forecast and rationale) is linked here
  and from the page header.
- **Capability** — the same questions conditional on the level of the frontier
  Epoch Capabilities Index (ECI): the model first forecasts its own p25/p50/p75
  for the frontier ECI at a target date, then conditions on each.
- **Policy levers** — the same questions conditional on each LEAP Wave 12
  policy scenario (built and elicited every run; hidden from the launch page).
- **Graph 3** — calibration and resolution against ForecastBench, one round
  with a human superforecaster arm (`docs/methodology.md` explains why one).
- **Graph 4** — calibration and skill on rare (1–9%) events, a two-simulator
  average (FreeCiv and a Starsim pandemic) correlated with ECI.
- **Graph 5** — observational conditionals: told "suppose A happened" about
  paired weather questions, does the conditional shift track the association in
  the resolution data? Rank correlation with ECI, under the noise ceiling.
- **Graph 6** — causal conditionals: given a vaccination campaign in a simulated
  epidemic, does the forecast move the way the simulator does? CRPS skill vs
  ECI, from the locked Starsim causal dataset.
- **FAQ** — the questions readers ask, with the elicitation prompt as it was
  actually sent, and Graphs 4, 5 and 6 inside the relevant answers.

## Reproduce

Two runtime tiers, and the split is deliberate. **Rebuilding** every dashboard
blob from the committed inputs is stdlib-only, needs no keys and no network,
and is checked byte-for-byte against the tracked output by the golden tests.
**Eliciting** new forecasts needs the FRI Forecaster harness
(`packages/fri-forecaster/`: stdlib Python, and pi on node) and API keys (next
section).

```bash
python3 -m redlines build            # rebuild all 14 views and mirror them to results/*.json
python3 -m redlines build --views g1 # any subset: g1,g2,g3,g4,observational,causal,databank,
                                     #   timeline,conditional,capability,axes,method,rationales,csv
python3 -m redlines build --list     # list view names and exit
python3 -m redlines assemble         # rebuild index.html from web/demo/ chunks + fresh blobs
python3 -m redlines export-fb        # the provisional ForecastBench-2.0 ingest artifact
python3 -m redlines paper            # paper/fig/*.pdf + paper/numbers.tex (needs matplotlib:
                                     #   pip install -e '.[paper]'; --backend agg needs no TeX)
```

`build` and `assemble` round-trip to the same tracked bytes (see
`docs/architecture.md`). Graph 3 and Graph 4 are derived from external inputs
(the ForecastBench forecast sets and the `forecastbench-sim` corpus); when
those are absent the build reads the tracked mirrors `results/graph3_data.json`
and `results/graph4_combined.json`, so a fresh clone rebuilds and assembles the
page without sibling checkouts. Re-deriving them needs `FB_DATASETS_ROOT` /
`FBSIM_ROOT` and `results/eval_full.json` (see "Data provenance").

### Credential-free contributor setup and checks

Use Python 3.11+ and **Node 22.19+ (22.x)** with npm. For example, on
Debian/Ubuntu x86-64, install the tools with:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip curl xz-utils
curl -fsSL https://nodejs.org/dist/v22.19.0/node-v22.19.0-linux-x64.tar.xz -o /tmp/node.tar.xz
sudo tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
node --version
npm --version
```

On other platforms, use the matching [Node 22 distribution](https://nodejs.org/en/download)
and install Python with venv/pip support through your package manager. From the
repository root, in a fresh clone:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,paper]' -e './packages/fri-forecaster[dev]'
(cd packages/fri-forecaster && npm ci)

# Local-only exclusions for development artifacts (not shared repository changes).
printf '\n.venv/\nredlines.egg-info/\n' >> .git/info/exclude

# Use disk-backed temporary space: the suite can exceed a small /tmp tmpfs.
mkdir -p .venv/tmp
# Isolate tests from any existing Pi coding-provider login; do not remove it.
TMPDIR="$PWD/.venv/tmp" PI_CODING_AGENT_DIR="$(mktemp -d "$PWD/.venv/tmp/pi.XXXXXX")" \
    python -m pytest -q -rs

python3 -m redlines build
python3 -m redlines assemble
git diff --exit-code   # on a fresh clone, tracked outputs must be byte-identical
```

The root pytest configuration collects **both** `tests/` and
`packages/fri-forecaster/tests/`. The latter includes real Pi tool-loop tests
against a local scripted model: no forecasting keys, provider login, or paid
calls are needed. Do not omit `npm ci`: it installs Pi 0.99.2 from the committed
lockfile; without Node and Pi these tests silently skip. Dependency installation
needs network access, but rebuilding uses committed inputs and tracked Graph 3/4
mirrors, not new forecasts. The optional `paper` extra above enables matplotlib
tests too.

Read the `-rs` skip summary: external ForecastBench/simulator inputs, internal
LEAP sources, missing current-instrument forecasts and the not-yet-plotted human
timeline can still cause skips. Missing Node/Pi is **not** an expected skip for
this setup. Do not run acquisition, scheduling or publishing scripts to test or
rebuild the dashboard.

## Elicit new forecasts

```bash
pip install -e . -e ./packages/fri-forecaster   # the harness (the pi loop)
(cd packages/fri-forecaster && npm ci)                       # pi 0.99.2, pinned there
python code/run_unified.py --dry-run     # print each condition's prompt, call nothing
python code/run_unified.py --experiment airo --workers 2   # what the cron runs
python code/run_unified.py --experiment airo --condition ai-banned --smoke
```

What a run asks is an **experiment** (`experiments/<name>.toml`,
`redlines/experiments.py`): a set of **conditions**, each one configured way of
running the instrument (the scenario set, the prompt variant, the minimal or
standard instrument, the loop, the models, a URL guard, whether its rows
publish), with settings shared at the top of the file and overridden per
condition. `experiments/airo.toml` is the published series; `pooled` names the
conditions whose mean is each model's published number. Rows carry the
experiment, the condition and `condition_sha256`, a hash of its settings.
`--condition` runs some of an experiment's conditions; `--smoke` one model,
into `results/experiments/`. A condition's `cadence` says when the cron runs it
(weekdays, UTC, "1st wed" for monthly, or "manual"):
`python -m redlines.experiments due` prints what is due today, one group a line.

Every call goes through pi (redlines/pi_loop.py) by way of the FRI
Forecaster harness in `packages/fri-forecaster/` (its README, "Requirements"):
node 22 and pi 0.99.2, whose `cli.js` `FORECASTER_PI` names. The harness hands
pi the prompt on stdin since 2026-10-19; an earlier one passed it as one
argument, which Linux caps at 128 KiB, and the runner refuses a prompt past
that rather than let pi fail. pi has been the published loop since
combined-v9 and the only one since 2026-10-22, when the litellm loop before it
left the repo.

Keys go in `~/.config/redlines/env` (mode 600), one `KEY=value` per line:
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`,
`XAI_API_KEY`, `TAVILY_API_KEY`. A repo-local `.env` is read as a fallback;
`REDLINES_ENV_FILE=<path>` pins the run to exactly one file. An already-set
environment variable always beats every file. `code/cron_run.sh` sources the
same file, and `tests/test_llm.py` pins the two parsers to agree.

`TAVILY_API_KEY` is required rather than optional: without it every model still
answers, from parametric memory with no current evidence, and the run looks
identical from the outside, so the runner refuses instead;
`--allow-ungrounded` makes that an explicit choice.

**The published protocol** (since 2026-08-27; rows are tagged with a protocol
id, currently `unified-joint-combined-v12`, see `redlines/conditional.py`) is the
single instrument: one call per model that answers every question ×
horizon cell unconditionally *and* under each scenario in one submission, with
no coherence relation stated in the prompt (coherence is measured afterwards).
The prompt calls the scenarios "conditions", LEAP's word, and so do the set
files and the rows written before 2026-10-21 (`condition`, which
`redlines.logs.read_row` renames on reading); the code, the newer rows and the
download say scenario.
The prompt is 73 questions (four AI incident types × 9 severity rungs on the
deaths ladder and × 8 on the damages ladder — since 2026-10-19 each rung is a
deaths question and a damages question, `docs/severity-legs-2026-10-19.md` —
plus five cross-cutting questions: the two 10%-of-population catastrophe
questions, human disempowerment, and since 2026-09-15 the two extinction
questions in XPT's wording, `docs/extinction-questions-2026-09-15.md`) over six
horizons, two of them rolling. Since
2026-09-02 each model is asked once per run (`repeats = 1`); the same-day
repeats that preceded it bought a re-asking spread, and their budget went to
the agentic search harness instead, so the views draw no interval on a
single-draw day. The model panel is the top four runnable models by ECI in the
newest Epoch snapshot, one seat per model family (`redlines.registry.panel()`,
`docs/model-set.md`). The unconditional slice lands in
`results/runs/<stamp>.jsonl`, the series every panel reads; the whole
instrument is appended to `results/conditional_runs*.jsonl`.
A condition's `scenarios` names its scenario set: `data/combined_conditions.json`
(the LEAP policies plus the model's own capability percentiles, what the
published series asks), `data/eci_conditions.json` (fixed ECI levels),
`data/axes_conditions.json` (risk against an x-axis quantity). See
`docs/conditional-forecasts.md`. A cron on the serving box pulls main
(`code/pull.sh`, so what is merged is what runs) and runs
`code/cron_run.sh` at 12:00 UTC, which refreshes the panel from Epoch's index
(`code/refresh_panel.sh`), runs whatever is due (the published series on
Wednesdays and Fridays) and publishes the rebuilt page with
`code/publish_dashboard.sh`.
Each call ends with a debrief turn (since 2026-09-15): per question group, the
sources that mattered most, the most compelling arguments, the most likely
pathway to catastrophe and the base rate, in the model's own words, exported
as `results/debriefs.csv`. The
axes instruments left the schedule on 2026-09-14; run them by hand with
`--experiment axes` (or `paperaxes`) when a fresh axes date is wanted.

### The question set

The Auto-ARC question workbook and its definitions under `data/auto-arc/` are
the single source: `code/make_autoarc_questions.py` generates
`data/autoarc_ladder.json` and `data/autoarc_crosscutting.json` from them, the
runner and every panel read only the generated files, and
`tests/test_autoarc_generator.py` fails if either is hand-edited. Definition
changes are versioned as instruments (`redlines/instrument.py`): damages
without monetized mortality (2026-10-21,
`docs/damages-without-mortality-2026-10-21.md`) is instrument
`airo-incidents-prospective-v3`, the 2026-10-19 split of every rung into a
deaths question and a damages question was `airo-incidents-prospective-v2`,
the 2026-09-10 counting rules
(`docs/counting-rules-specification-2026-09-10.md`) were
`airo-incidents-prospective-v1`, each superseded instrument's generated
questions are archived under `data/instruments/<version>/`, and rows carry the
instrument id so a view never answers a revised question with an older
probability.

### Rebuild the Graph 4 corpus (deterministic; needs the forecastbench-sim checkout)

From inside the `forecastbench-sim` checkout:

```bash
cp /path/to/this-repo/code/mine_lowprob_corpus.py worlds/freeciv/scripts/
uv run python worlds/freeciv/scripts/mine_lowprob_corpus.py \
    --data-dir data/games --snapshot-turn 40 \
    --rate-lo 0.01 --rate-hi 0.09 --min-n 40 --workers 8 \
    --out-dir data/lowprob
```

Produces `data/lowprob/{lowprob_classes,lowprob_selected_classes,lowprob_questions}.json`.
The reference run (1,019 games, snapshot turn 40) yields 425,270 binary
questions in 564 classes, of which 35 tail classes (1–9%) with 25,919 resolved
instances feed Graph 4; `data/lowprob_classes.json` records `min_n: 40`. The
pandemic side is `code/pandemic_build_corpus.py` in the same environment. The
model evals that ran on these corpora (`run_eval.py`, `pandemic_smoke.py`; API
keys + `FBSIM_ROOT`) called litellm and are archived in `archive/litellm-runners/`.

## Layout

```
index.html                  BUILD ARTIFACT: the one page; `redlines build`/`assemble` write it
web/
  demo/                     the page's source: numbered chunks + manifest.json (Timeline is 19-live-timeline.jsx)
  shared/                   question-rail.jsx, responsive.jsx — helpers the chunks share
  img/                      the FRI logo and the ForecastBench parity figure (web/fonts/ is ignored:
                            Season Sans is licensed for the live site only; clones use the fallback stack)
packages/fri-forecaster/    the FRI Forecaster harness -- pi, the research tools, the ForecastBench
                            driver -- as its own distribution, pip-installable from this repository
                            (its README). It was the agent-box repository from 2026-10-11 to
                            2026-10-19 and rejoined with its history.
redlines/                   the pipeline package (stdlib only)
  __main__.py               CLI: build / assemble / export-fb / paper
  config.py                 paths (env-overridable), round pins, thresholds
  registry.py               the single model table (ids, labels, ECI, colors) + panel()
  eci.py                    the Epoch Capabilities Index: fri_forecaster.eci (one implementation,
                            shared with the ForecastBench rounds) bound to data/ and the pinned vintages
  questions.py              schema-checked loaders for the Auto-ARC question set
  instrument.py             question-version boundaries and dated incident onset windows
  experiments.py            experiments and their conditions (experiments/*.toml); the prompt variants
  logs.py                   row files, one per run, and read_row (old rows' field names)
  runlog.py                 run-log loading, the series start, replicate pooling
  coherence.py              every coherence constraint the question set implies
  conditional.py            per-model deltas under a scenario vs the same-call baseline
  historical.py, rail.py, roster.py   historical severity markers; the shared question rail; the bench roster
  stats.py                  deciles / brier / bss / spearman / wilson — one implementation each
  hydrate.py, pages.py      window.__NAME__ blob injection; manifest-driven page assembly
  export.py                 forecasts.csv, rationales.csv, the download bundle, the ForecastBench export
  llm.py, tools.py          ACQUISITION ONLY: key loading + the agentic tool-use loop; the Tavily tools
  pi_loop.py                call_tools through FRI's agent-box (pi): the published loop since combined-v9
  views/                    one pure build() per panel: graph1..graph4, observational, causal,
                            databank, timeline, conditional, capability, axes, method
  paper/                    the paper's figures (graph1, graph3, graph4, incident_ladders,
                            conditional, capability, causal) and numbers.tex; style.py
experiments/                what runs ask: airo.toml (the published series), axes.toml, paperaxes.toml
code/                       acquisition scripts, generators and thin shims (see each docstring)
  run_unified.py            THE forecast runner; --experiment, --condition, --dry-run
  cron_run.sh, publish_dashboard.sh   the weekly run and the box-side publish
  pull.sh, refresh_panel.sh           what every box job runs first: the code, then the panel
  make_autoarc_questions.py the question generator: data/auto-arc/* -> data/autoarc_*.json
  make_*_conditions.py      the scenario sets (LEAP policies, ECI levels, self-elicited, axes, combined)
  make_eci_trend*.py, eci_projection_metrgraph.py   the ECI trend / projection inputs
  validate_launch_run.py, audit_cyber.py   launch-run audits
  mine_lowprob_corpus.py, pandemic_build_corpus.py   the Graph 4 corpus (needs forecastbench-sim)
  graph3_comparability.py   the Graph 3 methodology decomposition (needs FB_DATASETS_ROOT)
  observational/            Graph 5: the observational bench, vendored (spec.md, mining, scoring)
data/
  auto-arc/                 the Auto-ARC question workbook (.xlsx) and definitions (.md) by date
  autoarc_ladder.json, autoarc_crosscutting.json   the generated question sets (never hand-edited)
  instruments/              the previous instrument's definitions and question sets, archived by date
  epoch_capabilities_index_<date>.csv   Epoch ECI snapshots (2026-07-07 pinned for Graph 4; newest picks the panel;
                            fetched before every scheduled run since 2026-10-01)
  eci_projection_*.json, eci_trend_*.json   the ECI trend inputs
  live_metr_eci_frontier.json   the METR frontier the capability prompt quoted 2026-09-10 .. 09-18 (record only)
  leap_policies.json, leap_reference.json   the LEAP-derived scenario set and panel aggregates (the
                            survey documents and raw pull under data/leap/ are internal, gitignored)
  *_conditions.json         the scenario sets experiments ask (`scenarios`)
  human_baselines.json      prior human-panel forecasts of comparable questions (XPT, LEAP)
  historical_events.json, recent_incidents_2026-09.json   severity-axis markers; recent-incident context
  lowprob_classes.json, lowprob_selected_classes.json   the FreeCiv question classes (564) and the 35 tail classes
  observational/            Graph 5 inputs: pairs_selected.json, noise_ceiling.json, candidate provenance
  causal/                   Graph 6: the LOCKED Starsim causal dataset (README, MANIFEST.sha256, models.csv)
results/
  runs/                     the unconditional series, one dated .jsonl per run
  forecast_runs_unified.jsonl   the historical run log before per-run files
  conditional_runs*.jsonl   the whole instrument per scenario set; *_runs/ the per-run copies
  *_data.json, graph4_combined.json   the tracked view blobs (mirrors of what the page embeds)
  eval_panel2/, pandemic/, observational/   Graph 4 and Graph 5 eval outputs and logs
  experiments/, validation/ held arms (e.g. the ECI top-4 arm) and the launch-run audits
  coherence_experiment.json the joint-elicitation experiment (docs/coherence-experiment.md)
paper/                      figures, numbers.tex and dashboard screenshots for the white paper
tests/                      golden tests for build/assemble/paper, the generators, the runner's guards
docs/                       see below
archive/                    dead scripts, retired question sets and forecasts, superseded runs (archive/README.md)
  causal/                   Graph 6: the Starsim causal bench's generating code, frozen at causal-v4-locked
  litellm-runners/          the research runners that called litellm (the Graph 4 eval, the coherence
                            experiment, the observational roster run), archived 2026-10-22
archive/jason-demo.html     the original mock dashboard the live page grew from (Jason Abaluck)
```

## Data provenance

- **Epoch Capabilities Index.** `data/epoch_capabilities_index_<date>.csv` are
  snapshots of Epoch AI's ECI leaderboard. `redlines/eci.py` is the one reader:
  the 2026-07-07 vintage is pinned for Graph 4, the newest picks the panel, and
  a snapshot older than 31 days raises a warning.
- **ForecastBench** (Karger et al., ICLR 2025), CC BY-SA 4.0. Graph 3 reads the
  processed forecast sets published on forecastbench.org; `docs/methodology.md`
  gives the download and why the numbers move when it is re-pulled.
- **forecastbench-sim** (`forecastingresearch/forecastbench-sim`, pinned at
  commit `24d88de`) supplies the FreeCiv worlds, the question generator and
  resolver, the Starsim pandemic world and the model eval harness behind
  Graph 4 and Graph 6. `code/mine_lowprob_corpus.py` and the eval scripts run
  inside that repo's `uv` environment. The 1,019 recorded games and the 25.9k
  instance corpus are regenerated deterministically there, not committed here;
  the small class files under `data/` and the eval outputs under `results/`
  are.
- **LEAP** survey scenarios. The LEAP survey documents and the raw pull of
  panel answers are internal to FRI and are not in this repository
  (`data/leap/` is gitignored). What is tracked is derived from them:
  `data/leap_policies.json` (the Wave 12 policy scenarios the models are
  prompted with, verbatim in the prompt shown on the FAQ),
  `data/leap_reference.json` (each panel's n and median per asked percentile
  for the questions the page draws as reference lines, extracted by
  `code/make_leap_reference.py`), and the axes scenario sets. The generators
  that read the internal files exit with a message when they are absent, and
  their tests skip.
- **Internal sources, not published.** The 31-model ECI table was first
  transcribed from an internal FRI analysis; the runner's LLM layer was
  vendored on 2026-08-28 from an internal FRI checkout (`redlines/llm.py`,
  `redlines/tools.py`), so nothing in the run path depends on it; the Graph 6
  dataset was locked from FRI's ForecastBench-Sim ICLR work. Where a doc names
  one of those checkouts it is describing history, not a dependency.
- **The download.** The page's "Download forecasts" button serves
  `results/forecasts.csv`, `results/rationales.csv` and the bundle
  `results/redlines-data.zip` (both CSVs, the raw logs, the questions and
  scenarios, a README), all built by `python3 -m redlines build --views csv`
  (`redlines/export.py`) and not tracked. One line per (call, question,
  horizon, scenario) for every model in every run; the `protocol` column
  separates the elicitations (the combined instrument's `unified-joint-combined-v*`
  tags, the earlier joint and batch pilots) — do not pool across them.

## Docs

- `docs/architecture.md` — the acquire → artifact → build → render pipeline, its invariants, external boundaries and open items.
- `docs/methodology.md` — Graph 3 comparability (why one ForecastBench round), the grounding tools, the simulator corpora and the Graph 4 subsetting.
- `docs/model-set.md` — model selection: the top-k-by-ECI panel, one seat per family, reachability and Graph 4's roster.
- `docs/conditional-forecasts.md` — the LEAP Wave 12 policy conditionals, the capability and self-elicited capability conditionals, the combined and axes instruments.
- `docs/conditional-benches.md` — Graphs 5 and 6: can the models forecast conditionals? (observational weather pairs; Starsim interventions).
- `docs/coherence-experiment.md` — joint elicitation vs one question per call, and why the constraints are measured, not stated.
- `docs/question-swap.md` — the design record of the move to the Auto-ARC question set.
- `docs/extinction-questions-2026-09-15.md` — the extinction pair: why, whose wording, what it compares with, what changed, what is still the team's call.
- `docs/eci-top4-arm.md` — the ECI-ranked panel: where the selection rule came from and what it changed.
- `docs/counting-rules-specification-2026-09-10.md` — the incident counting rules (onset windows, cyber campaign boundaries) behind instrument `airo-incidents-prospective-v1`.
- `docs/cyber-validation-2026-09-10.md`, `docs/cyber-validation-prospective-2026-09-10.md`, `docs/cyber-source-review-prospective-2026-09-10.md` — the September 2026 audits of the cyber forecasts and their sources (with `.json` evidence files beside them).

## License

Code is MIT; the data, documentation and figures are CC BY 4.0 (cite "AIRO,
Forecasting Research Institute, https://airo.forecastingresearch.org"). Three
things are not covered: `archive/causal/` (a frozen copy from
`forecastbench-sim`, GPL-3.0), the Epoch Capabilities Index snapshots (Epoch
AI's), and the Season Sans web fonts, which are not in the repository (licensed for the live site only).
See `LICENSE` (MIT) and `LICENSE-DATA` (CC BY 4.0 and the carve-outs).
