# Production releases in the development cell

On a configured cell, say **deploy** after merging the work. The agent runs
`airo deploy`, then `airo status` and checks the configured public URL. Deployment
is explicit; pushing or merging does not change production by itself.

`airo deploy` fetches `main`, resolves an exact commit, requires all four GitHub
Actions checks on that commit, installs a separate Python environment and the
locked npm dependencies, and combines the new frontend with the existing published
forecast snapshot. All thirteen data blocks, including their question wording,
instrument labels and methodology, and all forecast downloads stay byte-identical.
No forecast jobs run during deployment. A successful activation switches code,
website and schedules together.
The development checkout is never served or run by the production scheduler.

Commands:

- `airo status`: selected commit, schedules, and recent run receipts.
- `airo deploy [--commit FULL_SHA]`: deploy a checked commit reachable from main,
  publishing the new interface with the currently published data. Missing,
  duplicated or incompatible data-block markers fail closed. Snapshot hashes
  detect unexpected data changes and release metadata tracks frontend and data
  provenance separately. Data schema changes need an explicit migration or a
  validated data publication; they must not silently substitute repository data.
- `airo deploy --publish-data`: rebuild the publication from a private copy of
  accrued forecast data. The existing current-instrument integrity checks must
  pass; failure retains the current code and website without fallback. This
  command does not generate forecasts. Scheduled forecast jobs still validate
  new data before publishing. Use this mode for the first fresh publication.
- `airo deploy --keep-publication`: explicitly deploy code and schedules while
  retaining the last good website. Use for a migration or instrument transition
  when deliberately retaining the whole site; this does **not** publish frontend changes. The first
  migration requires a verified private `bootstrap_publication` path. Release
  metadata records the preserved publication separately from the code commit.
  Ordinary deploys never silently fall back when an integrity check fails.
- `airo rollback`: select the previous code and website; keep accrued data.
- `airo smoke --run-id NAME`: exercise the job runner without calling providers.
  Repeating the same run ID does not execute twice.

The entry point is `code/production.py`. A private configuration file selected by
`AIRO_RUNTIME_CONFIG` (default `~/.config/airo/runtime.json`) supplies `root`,
`repository`, `github_repository`, `path` and the Unix `socket`. Do not commit
machine names, environment files, credentials, production data, or receipts.
The installer provides an `airo` wrapper, a persistent serving service and a
systemd timer that calls `airo tick` each minute. Both run inside the cell as the
agent user; the host ingress forwards only public static requests to the socket.
Use Node 22.21 or newer for native environment-proxy support; the runner enables
`NODE_USE_ENV_PROXY` for forecasting. Keep the production toolchain on the private
configured PATH. No supervisor credentials are needed for subsequent deployments.

Under the private runtime root:

- `releases/`: fixed code, dependency environments, package inventories and sites.
- `current`, `previous`: atomic release pointers.
- `state/results`: accrued production results, shared across releases.
- `state/data`: fetched Epoch snapshots, model registrations and generated conditions.
- `home/`: separate forecasting configuration, name registry, round history and logs.
- `runs/`, `logs/`: durable job receipts and diagnostics.

The initial migration must seed the state from the existing production server,
including licensed fonts. Repository results seed missing files, but never
replace accrued data. Corrections to existing production data require a separate,
reviewed data migration. Dependency versions resolved by pip are recorded per
release; npm uses its checked-in lockfile. Rollback reuses installed environments.
Retained releases and data need disk monitoring and backups; automatic deletion
is deliberately absent.

## Scheduling

Change `deploy/jobs.json` and merge/deploy it. The daily UTC wake-up delegates
experiment selection to `experiments/*.toml`; days with nothing due make no paid
calls. ForecastBench entries have explicit years and due dates. Creating a new
round means adding an entry, reviewing its cost/configuration, and deploying.
Submission upload remains manual, as before.

A single lock excludes deployment, rollback and jobs from one another. The
scheduler records a run **before** starting it. Failed/interrupted runs require
inspection and an explicit recovery action; reboot never retries paid work or
catches up missed dates automatically. Check receipts and the existing job
notifications. A timer outage during a scheduled minute means a missed run, not
an automatic later bill. To start scheduling after migration, create the private
`jobs-enabled` file only after disabling the old server's corresponding jobs.

The website is published into a new directory. A frontend deploy verifies its
published data blocks and downloads are unchanged; a data publication must pass
the full instrument validation. Only then is the release switched. Failed builds leave the selected release alone. Failure to
observe a new release through the serving socket automatically restores the
previous release. Forecast jobs retain their raw data even if publication fails.
