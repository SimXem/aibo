# automated-forecasting-monorepo

The Forecasting Research Institute's automated forecasting: a standing panel of
frontier language models, the dashboards that publish its forecasts, and the
forecasts it submits elsewhere.

One engine, and thin projects on top. A project is its questions, its answer
format, where the output goes and when it runs.

```
packages/
  forecaster/       the engine (fri_forecaster): the agent loop, the panel, the
                    Baseline condition, research tools, keys, alerts
  dashboard/        the dashboard kit (dashboard): a page from its chunks and
                    data, the download, the site folder
  ops/              production: releases, the scheduler, the schedule (jobs.json)
dashboards/         forecasts published as a site
  airo/             AIRO, the Automated AI Risk Outlook (redlines)
  eeai/             EEAI, the Economic Effects of AI (eeai)
submissions/        forecasts delivered in someone else's format
  forecastbench/    the ForecastBench rounds (forecastbench)
  leap/             the LEAP survey waves (leap)
code/production.py  the production launcher's fixed path; it runs packages/ops
```

Each directory has its own README. Dependencies point one way: a project uses
the engine and the kit, and no project imports another's code. A finished one-off stays here
as a frozen directory.

Only public data belongs in this repository: no participant data, no personal
information, no credentials, no production receipts.

## Working here

```sh
python3 -m venv .venv
.venv/bin/pip install -e 'packages/forecaster[dev]' -e packages/dashboard -e 'dashboards/airo[test]' \
    -e dashboards/eeai -e submissions/forecastbench -e submissions/leap
npm ci --prefix packages/forecaster     # pi, pinned; the engine's tests skip without it
.venv/bin/python -m pytest -q           # every project's tests; no API key needed
```

Building a dashboard needs nothing installed. Forecasting costs money and needs
API keys. They live outside the repository, in one file every project reads:
`~/.config/fri-forecaster/env` (`KEY=value` lines, mode 600).

Production runs from a separate release, never from a checkout. See
`packages/ops/README.md` for deployment, schedules and alerts.

The code is MIT-licensed (`LICENSE`). AIRO's data, documents and figures carry
their own terms (`dashboards/airo/LICENSE-DATA`).
