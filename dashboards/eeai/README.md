# EEAI: the Economic Effects of AI dashboard

EEAI asks the standing model panel FRI's "Economic Effects of AI" expert survey
and draws the answers. v0, 2026-11-11.

## What is in this directory

The whole dashboard. Outside it EEAI uses only the harness
(`packages/forecaster`: the panel, the Baseline condition, the agent loop,
search) and AIRO's Epoch snapshots (`dashboards/airo/data/`).

```
eeai/
  README.md            this file
  make_questions.py    the survey documents -> data/questions.json, data/history.csv
  survey.py            what the question set asks for
  instrument.py        the prompt, the answer tools, the cleaning
  run.py               ask the panel -> results/runs/<stamp>.jsonl
  build.py             the run files -> the page
  export.py            the download (eeai-data.zip)
  synthetic.py         made-up answers, for the page and the tests
  data/                questions.json, history.csv (tracked); source/ (FRI's documents, not tracked)
  web/                 the page's source: chunks, manifest, img/; fonts/ (licensed, not tracked)
  tests/               pytest eeai/tests
  results/             the run files (not tracked)
  site/                the built site (not tracked)
```

Run every command from this directory (`dashboards/eeai`).

## What is asked

The survey's questions, in one call per model (`python3 -m eeai prompt` prints
it), each also asked at nearer dates that FRI added (instrument
`eeai-survey-v2`; v1 was the survey's own dates only, and its rows continue):

- **AI progress.** The probability of each of the survey's three scenarios for
  AI capability at the end of 2030 (slow, moderate, rapid), the relative
  importance of the five capability indicators, and two milestone probabilities
  (a household robot; reliability).
- **Economic outcomes.** 15 questions about the US economy at the beginning of
  2027, 2028 and 2029 (added) and of 2030 and 2050 (the survey's)
  (GDP, labor and total factor productivity, participation, unemployment, youth
  unemployment, three job-category shares, wealth inequality, labor share,
  median household income, life satisfaction, AI-assisted work hours, AI
  electricity use). Each is asked unconditionally and under each scenario; the
  five the survey tags "uncertainty" also ask the 10th and 90th percentiles,
  unconditionally and under rapid. 396 numbers (156 of them the survey's own),
  and a rationale per question. A near date is the survey's 2030 wording with
  its years moved back, so a five-year growth window stays five years and
  every forecast is a later point on the charted series. Once a date has
  passed, the panel is no longer asked about it and its last forecast stands.

Wording, definitions and resolution sources are the survey's, verbatim
(`eeai/make_questions.py` -> `eeai/data/questions.json`). Where a human
respondent saw a chart, the model gets the series (`eeai/data/history.csv`).

Not asked, by decision: Part 2 (short-term forecasts) and Part 4 (policies),
whose dates have passed or are weeks away; the items that measure the respondent
(the knowledge quiz, the worldview items, policy support, the cognitive tasks);
and the occupation ranking, whose occupation subsets are in a sheet outside the
survey.

## How it is asked

The Baseline condition on the shared panel, both from `packages/forecaster`:

- `fri_forecaster.panel`: the four highest-ECI models we can run, one seat per
  model family, from the newest Epoch snapshot under the repository's `data/`
  (`EEAI_ECI_DIR` names another directory).
- `fri_forecaster.baseline`: no system prompt, web search and page reading
  offered (Tavily) and never required, reasoning at the top level, no debrief.
  This is AIRO's published `none` condition.
- The models cannot search or read FRI's own pages (`forecastingresearch.org`
  and its subdomains, and FRI's Substack): the human panel's answers to this
  survey are published there, and the first smoke call read them. The list is
  `eeai.config.BLOCKED_URLS`; each call records it. A snippet on someone
  else's page can still quote FRI.

```bash
python3 -m eeai prompt                        # the prompt, the tools, the panel; calls nothing
python3 -m eeai run --smoke                   # PAID: the top model only
python3 -m eeai run                           # PAID: the panel -> eeai/results/runs/<stamp>.jsonl
python3 -m eeai run --resume RUN_ID           # PAID: the models that run does not have yet
python3 -m eeai build                         # the run files -> eeai/site/
python3 -m eeai run --synthetic --out DIR     # made-up answers, to look at the page
python3 -m eeai build --runs DIR --site DIR
```

A run refuses to start without `TAVILY_API_KEY`. Keys are read as the harness
reads them (`fri_forecaster/keys.py`).

## The page

`python3 -m eeai build` writes `eeai/site/`: `index.html` (assembled from
`eeai/web/` by the dashboard kit, `packages/dashboard`), `eeai-data.zip`, and the logo and fonts the
page links to. The folder is self-contained; any static web server can serve
it. The panel's number is the median across models of each value. The page
draws what is asked: points at each date, joined to the latest data by
straight lines, not quarterly paths. When the record
(`eeai/data/history.csv`) has a value for a date, the forecast for it stays on
the chart as a ring tied to the outcome, and "Forecasts against outcomes" lists
the miss of the unconditional forecast and of each scenario's.

Each chart area (the GDP panel; the other indicators) has a small toggle at
the right of its controls: "Current" (the timeline above) or "History", which
plots the panel's forecast for the selected date against when it was asked,
run by run, with the outcome as a level line once the record has it. The two
page-wide controls are the forecast shown and the horizon (the date the
numbers are about, and how far the timeline runs). The view is kept in the
page address (`#split=1&horizon=2030&history=hero,grid`). Using a control
redraws the page and keeps that control where it was on the screen.

Hovering a forecast shows the panel's median and each model's own answer, one
column per series shown. On the small charts, the links under each chart
("Model forecasts and rationale", "Question and definition") open full-screen:
the forecasts for every date, each model's rationale, the question as asked.

Motion is small and optional: the modal fades in and out, the control just
used presses in, and the forecasts (not the record or the axes) fade in when a
control redraws a chart. A reader who asks for reduced motion gets none.

One control switches every chart between the unconditional forecast and the
forecasts conditional on AI progress (the three scenarios, with no
unconditional line). `eeai-data.zip` (`eeai/export.py`) holds the forecasts, rationales and AI progress answers as CSV,
the questions, the history and the run files. The page's "Download data"
buttons serve it.

## Open

- **Schedule and deployment.** Nothing runs on a schedule; `packages/ops/jobs.json`
  has no EEAI job. The site folder is copied by hand to wherever it is shown.
- **Fresh data.** The history ends where the survey's charts did (early 2025),
  and nothing refreshes it. A forecast shows as resolved only when the record
  gets a value for its date, so the first dates (the beginning of 2027) need a
  refresh from FRED and, for life satisfaction, AI-assisted work hours, AI
  electricity and the job shares, by hand. Until a scenario is known (the end
  of 2030) a miss against a scenario's forecast shows which scenario the
  economy is tracking, not that the forecast was wrong.
- **Beyond the survey.** The design mock-ups also show a quarterly GDP path, 12
  sector forecasts, AI adoption and macro demand scenarios, and attributed
  forecast updates. None is in the survey; each would be a new instrument
  version, and a new series.
- The AI electricity question points to an embedded document the survey's
  respondents could open and the models cannot.
