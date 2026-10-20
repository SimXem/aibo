# fri_forecaster: a ForecastBench round, end to end

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
             5 build   each condition = the mean of its members' forecasts
                       ──> <due>.<team>.<N>.json, ready to upload
             6 report  summary.txt: coverage, files, API cost per member
```

## 1. Picking models by ECI

A **condition** is a rule for what to submit, defined by rank on Epoch's ECI (Epoch
Capabilities Index). The example registry has three:

| condition  | members                          | research |
|------------|----------------------------------|----------|
| `ensemble` | the top 4 models by ECI          | yes      |
| `unaided`  | the same 4 models                | no       |
| `solo`     | the top model by ECI             | yes      |

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
python -m fri_forecaster.names show                  # each condition's current name
python -m fri_forecaster.names current ensemble      # its name, or exit 1 if the code drifted
python -m fri_forecaster.names sync --dry-run < panel.tsv   # what the panel would change
python -m fri_forecaster.names fingerprint ensemble  # for registering a name by hand
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

**Run.** A **member** is one model at one thinking level, with research on or off. The
three conditions above need 8: four models with research, the same four without (solo's
model is one of the four). Each member forecasts every question in the set (about 500)
with `forecastbench run`, one pi call per question
([the call itself](../README.md#how-it-works)):

- a market question gets one forecast; a dataset question one per resolution date;
- research members get `web_search` and `read_page` and must make 2 successful research
  calls before `submit_forecast` unlocks; others get only `submit_forecast`;
- every member writes `manifest.json` with its settings, and resuming under different
  settings is refused;
- research members run in parallel, then the others; a second pass retries whatever the
  first left unanswered.

**Build.** Each condition becomes one forecast set: per question and resolution date, the
mean of its members' forecasts. A set covering less than 95% of the market questions or
of the dataset questions is written but marked not ready (`build` exits 1). The upload
looks like this:

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

**Report.** `summary.txt`: what sync found, coverage for each set, the files to upload, and
API cost per member.

## On disk

```
<ROUNDS_DIR>/<due>/
  question_set.json                       the round's questions, fetched once
  members/<model>--<thinking>--<research|noresearch>/
    manifest.json                         the member's settings, pinned
    results.jsonl                         one line per question answered
    calls/<source>__<id>/attempt-N/       one pi call's inbox and outbox
  <due>.<team>.<N>.json                   forecast set N, ready to upload
  <due>.<team>.<N>.json.provenance.json   its members and how they were combined
  logs/  summary.txt
```

## Setup

Copy `examples/round.env.example` to `~/.config/fri-forecaster/round.env` and set
`FB_ORG` (the team name ForecastBench assigned) and `FORECASTER_NAMES` (the registry). API
keys go in `~/.config/fri-forecaster/env`. Every call is billed to API keys: the harness
refuses an agent folder that holds a `pi /login`, drops bearer and OAuth tokens from pi's
environment, and requires the model's provider key.

```sh
SAMPLE=8 scripts/fb_round.sh 2026-10-11 rehearsal   # a cheap end-to-end check on a past set
scripts/fb_round.sh 2026-10-25                       # the real round
```

Unattended, cron runs `scripts/fb_cron.sh <due>` instead: the same round, its output in
`<ROUNDS_DIR>/<due>/logs/cron.out`, then one ntfy push (`NTFY_TOPIC` in `round.env` or
the keys file) saying how many sets are ready to upload. One crontab line per due date,
a few minutes after the question set appears:

```
5 0 25 10 * /usr/bin/flock -n /tmp/fb-round.lock <checkout>/scripts/fb_cron.sh 2026-10-25
```

## Modules

| file               | what it does                                                      |
|--------------------|-------------------------------------------------------------------|
| `harness.py`       | one pi call: inbox, run, outbox, evidence and usage, merged answer |
| `pi_tools.ts`      | the pi extension: research tools, submit tools, research floor    |
| `tools.py`         | `web_search` / `read_page` (Tavily), stdlib only                  |
| `tool_cli.py`      | the research tools as a CLI for `pi_tools.ts`; backs off on 429s  |
| `keys.py`          | API keys from the environment or an env file                      |
| `forecastbench.py` | the ForecastBench driver: members (`run`) and sets (`build`)      |
| `names.py`         | the name registry: conditions, members, fingerprints              |
