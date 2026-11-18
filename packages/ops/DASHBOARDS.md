# Put a dashboard on the production server

AIRO, EEAI and RSI use the same release builder, static server, scheduler, receipts
and rollback command. Each installation selects a dashboard by name. Its own
`current` pointer switches its code, site and schedule together. The serving
process pins every response to one publication. The existing AIRO configuration
and `airo` command remain valid.

## Install another site

1. Merge the dashboard and runtime through the normal checks and deploy AIRO
   with `airo deploy`. Use the checked release as the bootstrap launcher for
   the new instance. Run the remaining setup on the production server with
   its forecasting service account and toolchain.
2. Install `packages/ops/dashboardctl` as `/usr/local/bin/dashboardctl`.
   Create a private `/etc/fri-dashboards/NAME.json` for each installation.
   An installation can point `DASHBOARD_CONFIG_DIR` at another private
   directory. To manage existing AIRO here, symlink `airo.json` to its existing
   runtime config. Keep its existing root, socket, service account and state.
3. For a survey, start from the example below. Replace the example paths with
   absolute production paths. Copy `repository`, `github_repository` and
   `path` from the working AIRO configuration. Give each instance a distinct
   root and socket. Keep the socket directory accessible to the forecast
   account and ingress service group. Keep raw data and private configs
   outside that directory.

```json
{
  "dashboard": "rsi",
  "root": "/srv/forecasts/rsi",
  "socket": "/run/fri-sites/rsi.sock",
  "repository": "<same clone URL as AIRO>",
  "github_repository": "<same owner/repository as AIRO>",
  "path": "<same production PATH as AIRO>",
  "panel_runtime_config": "/etc/fri-dashboards/airo.json",
  "bootstrap_code": "/srv/forecasts/airo/current/code"
}
```

`panel_runtime_config` shares AIRO's private forecast home, operation lock,
Epoch snapshots and automatic model registrations. A survey forecast refreshes
the panel through the primary release before starting paid calls. The
date check in the runner also applies to manual calls. Each survey writes
its own results, attempts, sites and receipts under its own root.

4. Install the example systemd units in `/etc/systemd/system`. Set
   `User` and `Group` to the existing forecasting account and socket group.
   Create the socket directory on boot, for example with a tmpfiles entry
   `d /run/fri-sites 0750 forecast forecast -`. Grant the ingress worker
   traversal and access to the socket (0660). Start the site service before
   the first deploy so the activation probe can reach it.

```sh
systemctl daemon-reload
systemctl enable --now fri-dashboard@rsi.service
dashboardctl rsi deploy --publish-data
dashboardctl rsi status
dashboardctl rsi smoke --run-id install-smoke
```

RSI can start with the real empty survey. Its protected results directory
is created under `state/results`. For EEAI, use `"dashboard": "eeai"` and its
own paths. To move the existing EEAI site without changing any forecast,
copy its published folder to private storage, set `bootstrap_publication`
to that folder and do the first deploy with `--keep-publication`. Seed
`state/results/` with the complete real run JSONL files before the first
data rebuild. For licensed EEAI fonts, seed `state/fonts/` from the licensed
installation. Keep the existing hostname and password gate in place during
cutover. Compare the prior and staged download hashes before switching ingress.

On subsequent deploys, `dashboardctl NAME deploy` selects a checked commit,
builds the new frontend around the published data blocks, preserves the
download bytes and verifies the data snapshot hash. Use `deploy --publish-data`
to rebuild from accrued results. A failed build leaves the current site in
place. Use `dashboardctl NAME rollback` to select the previous release.
The primary release retains its AIRO-specific instrument validation and
state migration. Check `storage` before provisioning additional releases.

## Give a site a hostname and password

Point the site's DNS and TLS-enabled ingress at its configured Unix socket.
If ingress lives outside the production guest, forward that socket through
the installation's private relay and use the relay as the upstream. The
origin serves static files. Every public route to a password-protected
origin must go through the password gate.

[Example nginx virtual host](examples/dashboard.nginx.conf) protects every
URL, including downloads, assets and release metadata. Copy it into the
ingress installation's private configuration, set the hostname, upstream and
certificate paths, and create the password file interactively. Reuse an
existing compatible password file when migrating. Create a new file with
`htpasswd -cB /etc/nginx/dashboard-passwords/rsi reader`; omit `-c` when
updating it. Restrict it to the ingress account. Run `nginx -t` before
reloading. For an intentionally public dashboard, omit the two `auth_basic`
directives and the private cache policy. [nginx HTTP Basic authentication](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html)

Verify the **public hostname** after cutover. On a protected site, requests
without credentials and with an incorrect password must return 401. An
authenticated request should return the new release and the intended page.
For EEAI, repeat the access test for `/eeai-data.zip`. The authenticated
command below prompts for the password.

```sh
curl -sS -o /dev/null -w '%{http_code}\n' https://rsi.example.org/
curl --fail --user reader https://rsi.example.org/release.json
```

## Schedule and recover runs

Use the **one host timer**, `fri-dashboard-tick.timer`. It invokes
`dashboardctl tick-all` every UTC minute. Each installed dashboard reads
its own entries from the same repository file, `packages/ops/jobs.json`,
at the commit it has deployed. Existing entries with no `dashboard` field
belong to the primary AIRO installation, including ForecastBench rounds.
The runtime refreshes panel state, runs the selected instrument on the server,
validates the publication and switches that site's pointer.

Add a reviewed job with one time specification. This example is illustrative:

```json
{"id":"rsi-weekly","dashboard":"rsi","kind":"forecast","weekly_utc":"Fri 15:30"}
```

Use `daily_utc` for `HH:MM`, `weekly_utc` for `Mon` through `Sun` and
`HH:MM`, or `at` for an exact UTC timestamp. Changes take effect when the
owning dashboard deploys. Stagger jobs that share the forecast lock.
To enable scheduling for a site, create its private `jobs-enabled` file in
the runtime root. For migration, verify the new timer includes AIRO and all
previously scheduled jobs, then replace the old tick timer. Keep the serving
services running. Install commands after staging the configs and units:

```sh
systemctl enable --now fri-dashboard-tick.timer
dashboardctl rsi status
```

For an explicitly authorized paid run, use
`dashboardctl rsi run-dashboard --run-id rsi-YYYYMMDD-first`. RSI's production job runs both research-access conditions (eight calls for a four-model panel). Manual and scheduled jobs use the same execution path. A receipt is written before
forecasting. Reusing its ID never spends again. Missed or interrupted jobs
are recorded and alerted without catch-up. For surveys, partial attempts
remain in `state/attempts/<receipt-id>/`; a successful run moves into
`state/results/` before the site is built. If publication alone failed, fix
the cause and deploy with `--publish-data` to publish the saved results.

## Add a fourth dashboard

Package its runner and static builder as project entry points. The runner
accepts an output directory and produces one completed run file or folder.
The builder accepts the completed results directory and an empty site folder,
validates the data and writes `index.html` plus its downloads. Use the dashboard
kit's named data blocks to separate forecast data from the frontend.

Add one entry in `packages/ops/dashboard_projects.py` specifying the package,
web manifest, build and run arguments, public data block, downloads and
asset directories. Declare external downloads in `downloads` for hashing and
in `required` when every valid publication must contain them. Keep private
inputs, raw attempts, passwords and receipts outside the site. Follow the
same config, hosting and schedule steps above.
