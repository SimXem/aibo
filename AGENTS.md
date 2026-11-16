# Development and production

This is automated-forecasting-monorepo: the engine and the scheduler under
`packages/`, the dashboards (AIRO, EEAI) under `dashboards/`, and submissions
(ForecastBench) under `submissions/`. See `README.md` for the layout.

Develop and test in the checkout. Production runs from a separate release.
When the user asks to deploy, merge through the repository's normal PR/check
requirements, then run `airo deploy`. Inspect `airo status` and verify the public
URL from the private runtime configuration before reporting success. A merge by
itself does not deploy. Normal deployment publishes the new frontend with the
existing published forecast snapshot and downloads; it does not require fresh
forecasts. Verify that release metadata names the new frontend commit and retains
the data snapshot hash. `airo deploy --publish-data` explicitly rebuilds forecast
data and requires the instrument integrity checks; scheduled forecast jobs also
validate before publishing. Never silently fall back after a data check fails.
`airo deploy --keep-publication` retains the entire old site and is only for an
explicit code-only deployment. Use `airo rollback` for an unhealthy release.

See `packages/ops/README.md` for schedules, run receipts and recovery. Add or change
scheduled work in `packages/ops/jobs.json`, then merge and deploy. Do not launch paid
forecast jobs merely to test deployment; `airo smoke` exercises the runner without
provider calls. ForecastBench rounds upload validated sets automatically; upload
failures page and can be retried without rerunning forecasts. See
`submissions/forecastbench/README.md` for the private authentication setup.

Keep machine names, personal paths, production data, credentials and deployment
receipts outside git. Read the cell's private runtime configuration for its
installation details. Never copy the coding-provider login into a forecasting
job's agent directory.
