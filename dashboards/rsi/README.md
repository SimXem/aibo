# Recursive self-improvement survey

For production releases, protected hosting and paid jobs, use the [dashboard deployment guide](../../packages/ops/DASHBOARDS.md).

The runner and preview read the [version-controlled survey instrument](rsi_dashboard/rsi_forecasting_survey.md) shipped with this package. Each
section includes its definitions, questions, answer formats and resolution
criteria. From this directory build either local view with Python 3.11+.

```sh
PYTHONPATH=../../packages/dashboard python3 -m rsi_dashboard
PYTHONPATH=../../packages/dashboard python3 -m rsi_dashboard --synthetic
```

Open `site/index.html` for the instrument or `site-synthetic/index.html`
for the labeled test answers. The synthetic run checks completeness, units,
quantile ordering and section rationales without a provider. Pass
`--instrument PATH` for a survey file outside the checkout and `--site DIR`
for a different output folder.

## Dashboard preview and hydration

From the repository root, reproduce the supplied design at the private preview
root or build the Baseline view in the same served directory:

```sh
.venv/bin/python -m rsi_dashboard --mockup *mockup*.html --site dashboards/rsi/site
.venv/bin/python -m rsi_dashboard --site dashboards/rsi/site/baseline
```

After running the panel, rebuild with completed results:

```sh
.venv/bin/python -m rsi_dashboard --results dashboards/rsi/results --site dashboards/rsi/site/baseline
```

Open `/baseline/` on the preview. Choose `--site dashboards/rsi/site` to
replace the design mockup at the root. The build reads completed runs in
date order, checks their frozen instrument, prompt hashes, model receipts
and ensemble medians, and embeds the public forecasts and section rationales.
The latest run fills the headline cards and question tables. The Q3.2 chart
shows the selected access condition; the CSV includes every completed run and identifies its condition. Week-on-week change requires a run
exactly seven days earlier. Unfinished runs have no ensemble file and are
skipped. A completed run that fails validation stops the build before writing.


## Run the ensemble

From the repository root, this command starts paid model calls with web research available.

```sh
PYTHONPATH=dashboards/rsi:packages/forecaster python3 -m rsi_dashboard.run
```

The CLI defaults to `--condition full-web`. Choose `--condition fri-blocked` for
the restricted arm or `--condition both` for a paired run. The production
RSI job selects **both**. Four panel members across two arms means eight calls.
Both arms receive the identical dated prompt, panel, reasoning settings and Baseline
tools. The restricted arm excludes the apex and all subdomains of
`forecastingresearch.org` from search results and page reads. Domains such as
`forecastingresearch.substack.com` remain available. This controls source
access; material quoted on permitted third-party sites can still appear.

A paired directory has one frozen plan and a subdirectory per arm. Resume
using the paired directory. The dashboard access selector changes the cards,
chart, questions and rationales together; the CSV has a `web_access` column.
Earlier receipts without recorded access settings are labeled separately.

Each standing panel member receives the dated survey once per arm through
`fri_forecaster.baseline.run`. New runs require an Epoch snapshot dated today in UTC. The default directory is
`$FORECASTER_ECI_DIR` or `~/.cache/fri-forecaster/eci`. For parity with production,
use AIRO’s dated snapshot together with its automatic model rows. Use `--eci-dir DIR` to select another snapshot
directory. The printed run directory contains the frozen prompt and panel in
`plan.json`, validated model responses with five section rationales, research
evidence and usage in each model's JSON, and the harness attempts. Once all
members validate, `ensemble.json` contains the median across models for
each probability and each percentile. Pass `--resume RUN_DIRECTORY` to reuse
validated responses and retry missing members. The preview remains a separate
local build.
