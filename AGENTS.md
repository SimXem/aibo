# Airo development and production

Develop and test in the checkout. Production runs from a separate release.
When the user asks to deploy, merge through the repository's normal PR/check
requirements, then run `airo deploy`. Inspect `airo status` and verify the public
URL from the private runtime configuration before reporting success. A merge by
itself does not deploy. Use `airo rollback` for an unhealthy release.

See `deploy/README.md` for schedules, run receipts and recovery. Add or change
scheduled work in `deploy/jobs.json`, then merge and deploy. Do not launch paid
forecast jobs merely to test deployment; `airo smoke` exercises the runner without
provider calls. ForecastBench submission upload is still manual.

Keep machine names, personal paths, production data, credentials and deployment
receipts outside git. Read the cell's private runtime configuration for its
installation details. Never copy the coding-provider login into a forecasting
job's agent directory.
