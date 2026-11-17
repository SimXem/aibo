# A ForecastBench round, end to end

`scripts/fb_round.sh <due date>` runs one ForecastBench round unattended: it waits for the
question set, has every model forecast every question through pi, combines the models'
forecasts into the sets you submit, and reports what it cost. What it submits comes from
a **name registry**; how the machine is set up comes from **`round.env`**. Both are
private and live outside the repo (`~/.config/fri-forecaster/`); `examples/` shows their
shape.

```
 Epoch's ECI ──> the panel ──> registry: conditions, their members, a fingerprint
                 (the models this            │
                  machine can run,           │
                  best first)                ▼
 round day:  1 wait    for <due>-llm.json in forecastbench-datasets
             2 sync    each condition against the panel: a moved top N or drifted
                       code registers the condition's next place, then and there
             3 check   each condition's name matches the code (it does, after sync)
             4 run     each member forecasts every question: one pi call each
             5 build   each submitted condition = the mean of its members' forecasts
                       ──> <due>.<team>.<N>.json, ready to upload
             6 report  summary.txt: coverage, files, API cost per member
```

## 1. Picking models by ECI

A **condition** is a rule for what to forecast with, defined by rank on Epoch's ECI
(Epoch Capabilities Index). The example registry has four:

| condition  | members                 | asked under                              | submitted          |
|------------|-------------------------|------------------------------------------|--------------------|
| `ensemble` | the top 4 models by ECI | the ForecastBench prompt, with research  | yes, **publicly**  |
| `unaided`  | the same 4 models       | the ForecastBench prompt, no research    | no: it only runs   |
| `solo`     | the top model by ECI    | the ForecastBench prompt, with research  | yes                |
| `pooled`   | the top 4 models by ECI | each of AIRO's five conditions           | yes                |

**How a member is asked** is its *mode*:

- `research`, `noresearch`: the ForecastBench prompt, a forecaster's system prompt with
  research required (two calls before submitting) or not offered.
- `airo-<condition>`: one of AIRO's conditions (`none`, `independent`, `recent`,
  `critical`, `two-step`). No system prompt, research offered and never required,
  reasoning at each model's top level (`fri_forecaster.baseline`), and the condition's
  one instruction, verbatim, as a paragraph before the question's last line
  (`fri_forecaster.variants`; `none`, AIRO's Baseline, adds nothing). An entry lists them
  in `prompts`, and its forecast is the mean over every member under every prompt.

**What goes up.** ForecastBench takes at most 3 sets a round and, since 2026-11-13, at
most one under the team's own name; the rest carry its anonymous one (`Anonymous N`). A
condition is submitted unless the registry says `"submit": false`, and anonymously unless
it says `"public": true`. A condition that is not submitted still runs, and its members'
forecasts stay in the round's folder for scoring afterwards. The registry's order is the
round's: the submitted conditions run first, in set-number order, so put first the one
that must not miss the day.

The pick happens **every round, at sync**: the round reads the panel (the models this
machine can run, best by ECI first) and a condition whose members are not the panel's
top N gets a new registry entry with them. The entry records why in its `reason` (what
sync found changed, and when), each member in fri-utils' `ModelRun` shape (model,
provider, thinking level, tools, the one-shot baseline's `model_run_key`), and a
fingerprint of the code that shapes forecasts: the system prompt, the question prompt
and the tool descriptions.

A configuration gets a leaderboard name, `<condition>-<place>` (e.g. `ensemble-oak`), and
a registered entry is never edited. When anything that changes forecasts changes
(members, thinking, prompts, tools, the pi version), the condition moves to the next
place in the registry's list. So a leaderboard name always means exactly one
configuration, and places carry no rank: a later configuration never reads as an
upgrade.

```sh
python -m forecastbench.names show                  # each condition's current name
python -m forecastbench.names current ensemble      # its name, or exit 1 if the code drifted
python -m forecastbench.names sync --dry-run < panel.tsv   # what the panel would change
python -m forecastbench.names fingerprint ensemble  # for registering a name by hand
```

## 2. The round

**Wait.** The question set `<due>-llm.json` appears in
[forecastbench-datasets](https://github.com/forecastingresearch/forecastbench-datasets)
at 00:00 UTC on the due date. The script polls every two minutes and gives up at
`WAIT_UNTIL` (08:00 UTC by default).

**Sync.** The panel comes from `panel_members`, a function `round.env` defines, one
model per line, best first: `<Epoch name> TAB <pi model id> TAB <lab>`. On AIRO's box
that is `python -m redlines.registry`, so the round runs the same ensemble as the AIRO
runs (ranked by `fri_forecaster.eci`, one seat per model family, only models the
machine can run). `names sync` then compares every condition with the panel's top N:
a moved top N, or code that no longer matches the registered fingerprint, registers
the condition under its next place with the panel's models and the live code, and the
round runs under the new name. Nothing waits for a hand step; the log and summary say
what was registered and why. Without a hook the ranking is Epoch's published index,
names only (`python -m fri_forecaster.eci --fetch --names`): a moved top N is then
logged, not registered, because a name alone does not say how to run the model.

**Check.** After sync, every condition's registered fingerprint is compared with the
code once more; a mismatch stops the round (exit 3).

**Run.** A **member** is one model at one thinking level in one mode. The four
conditions above need 28: four models with research, the same four without (solo's
model is one of the four), and the four under each of five AIRO conditions. Each member
forecasts every question in the set (about 500) with `forecastbench run`, one pi call per
question ([the call itself](../README.md#how-it-works)):

- a market question gets one forecast; a dataset question one per resolution date;
- `research` members get `web_search` and `read_page` and must make 2 successful research
  calls before `submit_forecast` unlocks; `noresearch` members get only
  `submit_forecast`; `airo-*` members get all three and no floor;
- every member writes `manifest.json` with its settings, and resuming under different
  settings is refused;
- the conditions run one after another, each one's members sharing `CALLS` pi calls at
  once (`round.env`; 12 by default; with more members than that allows they take turns),
  and a member two conditions share runs once; a second pass retries whatever the first
  left unanswered;
- a provider that refuses the API key stops its member at once (`run` exits 2) and the
  round pages "run FAILED" (`fri_forecaster.alert`) there and then, once per provider:
  nothing else mends it.

**Build.** Each submitted condition becomes one forecast set, as soon as its members are
in and again after the second pass: per question and resolution date, the mean of its
members' forecasts. A set covering less than 95% of the market questions or of the
dataset questions is written but marked not ready (`build` exits 1), and so is one with a
member below 95%: every cell would still have a forecast, but from another ensemble than
the name says. The upload looks like this (`<team>` is the team's own name for the public
condition, its anonymous one for the others):

```json
{
 "organization": "<team>",
 "model": "ensemble-oak",
 "model_organization": "<team>",
 "question_set": "2026-10-11-llm.json",
 "forecasts": [
  {"id": "SPY", "source": "yfinance", "forecast": 0.58, "resolution_date": "2026-11-10", "reasoning": null},
  {"id": "42666", "source": "metaculus", "forecast": 0.31, "resolution_date": null, "reasoning": null}
 ]
}
```

**Report.** `summary.txt`: what sync found, coverage for each set, any member that fell
short, the files to upload, and API cost per member.

## On disk

```
<ROUNDS_DIR>/<due>/
  question_set.json                       the round's questions, fetched once
  members/<model>--<thinking>--<mode>/     mode: research, noresearch, airo-<condition>
    manifest.json                         the member's settings, pinned
    results.jsonl                         one line per question answered
    calls/<source>__<id>/attempt-N/       one pi call's inbox and outbox
  <due>.<team>.<N>.json                   forecast set N, ready to upload
  <due>.<team>.<N>.json.provenance.json   its members, their coverage, how they were combined
  logs/  summary.txt
```

## Setup

Copy `examples/round.env.example` to `~/.config/fri-forecaster/round.env` and set
`FB_ORG` (the anonymous name ForecastBench assigned the team), `FB_PUBLIC_ORG` (its own
name, for the one public condition) and `FORECASTER_NAMES` (the registry). API
keys go in `~/.config/fri-forecaster/env`. Every call is billed to API keys: the harness
refuses an agent folder that holds a `pi /login`, drops bearer and OAuth tokens from pi's
environment, and requires the model's provider key.

```sh
SAMPLE=8 scripts/fb_round.sh 2026-10-11 rehearsal   # a cheap end-to-end check on a past set
scripts/fb_round.sh 2026-10-25                       # the real round
```

Unattended, cron runs `scripts/fb_cron.sh <due>` instead: the same round, its output in
`<ROUNDS_DIR>/<due>/logs/cron.out`, then one alert (`fri_forecaster.alert`; where it goes
is the installation's `alerts.json`). Successful builds are automatically uploaded
using the private settings in [the setup guide](README.md). A notice confirms the
uploads; `upload FAILED` pages on upload errors, and `run FAILED` pages on build
failures (unless the round already paged). Retry an upload with
`python -m forecastbench.upload --root <ROUNDS_DIR>/<due>` after sourcing the
private environment; this makes no forecasting calls. One crontab line per due date,
a few minutes after the question set appears:

```
5 0 25 10 * /usr/bin/flock -n /tmp/fb-round.lock <checkout>/scripts/fb_cron.sh 2026-10-25
```

## Modules

| file               | what it does                                                      |
|--------------------|-------------------------------------------------------------------|
| `forecastbench/__init__.py` | the ForecastBench driver: members (`run`) and sets (`build`) |
| `forecastbench/names.py`    | the name registry: conditions, members, fingerprints         |
| `forecastbench/upload.py`   | validated uploads, receipts and upload-only retries           |
| `scripts/fb_round.sh`       | one round, unattended; `scripts/fb_cron.sh` is the scheduler's entry |

The agent loop, the research tools, the panel and the keys are the engine's
(`packages/forecaster`).
