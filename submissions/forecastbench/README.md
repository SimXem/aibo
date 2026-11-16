# ForecastBench submission setup

The scheduled round script builds and validates submission files, uploads them
with a dedicated service account, and reports success or pages on failure.
Installations must configure the private upload settings before enabling it.
See the [round workflow](ROUND.md) and
[ForecastBench's submission instructions](https://github.com/forecastingresearch/forecastbench/wiki/How-to-submit-to-ForecastBench).

## Google Cloud project and uploader identity

Use a dedicated service account for unattended uploads. A personal `gcloud`
login can require interactive reauthentication, even when it has a refresh token.
The examples below use placeholders: keep actual installation details, team
identifiers, credentials and upload receipts in private configuration outside git.

Authenticate as a project administrator for setup, then select a globally unique
project ID. An existing project is also suitable; skip its creation in that case.
Creating service accounts requires `iam.serviceAccounts.create` on the project.

```sh
gcloud auth login
FB_PROJECT_ID='your-globally-unique-project-id'
gcloud projects create "$FB_PROJECT_ID" --name='Automated forecasting'
gcloud services enable iam.googleapis.com --project="$FB_PROJECT_ID"
gcloud iam service-accounts create forecastbench-uploader \
  --project="$FB_PROJECT_ID" \
  --display-name='ForecastBench uploader'
gcloud iam service-accounts describe \
  "forecastbench-uploader@${FB_PROJECT_ID}.iam.gserviceaccount.com" \
  --project="$FB_PROJECT_ID" --format='value(email)'
```

Send that service-account email to the ForecastBench organizers and ask them to
grant access to your team's submission prefix, including future round dates.
Request object creation and, if supported, object metadata reads so uploads can
be verified and an interrupted upload can be retried safely. Metadata reads are
required to recover when the server accepted a file but its response was lost.
Overwrite and delete access are unnecessary for creating new files.
The account needs no project-wide role to write to a separately authorized
ForecastBench bucket.

## Production authentication

Configure authentication on the actual submission runner, using its runtime home
and environment. A successful login in a development shell does not configure
the production runner. Prefer an attached service account or Workload Identity
Federation where the host supports it.

If the host requires a service-account JSON key, the setup administrator needs
`iam.serviceAccountKeys.create` and the project's organization policies must
permit key creation. Create the key directly into a private directory, then
securely provision it to the runner; never commit or paste its contents into logs.

```sh
FB_KEY_DIR="$HOME/.config/forecastbench-uploader"
mkdir -p "$FB_KEY_DIR"
chmod 700 "$FB_KEY_DIR"
(umask 077
 gcloud iam service-accounts keys create "$FB_KEY_DIR/key.json" \
   --iam-account="forecastbench-uploader@${FB_PROJECT_ID}.iam.gserviceaccount.com" \
   --project="$FB_PROJECT_ID")
```

For the managed production runtime, deploy the upload-capable release, then
provision the key over stdin. The runtime validates authentication before
replacing its private credential and settings files:

```sh
airo configure-forecastbench \
  --upload-prefix='gs://your-submission-bucket/your-team-prefix/binary' \
  < "$FB_KEY_DIR/key.json"
airo check-forecastbench-upload --due=YYYY-MM-DD
```

The second command writes and reads a unique `.txt` test object in that round's
folder, then deletes it if permitted. It submits no forecasts and sends no alert.
The production uploader uses Google's authentication library to refresh its
service-account token; it needs neither `gcloud` nor a personal login.

Keep this configuration separate from the forecasting models' agent directory.
Replace keys when needed and revoke retired keys after verifying their replacement.
Network-restricted setup environments need access to
`cloudresourcemanager.googleapis.com`, `serviceusage.googleapis.com`,
`iam.googleapis.com` and the authentication endpoints; uploads also need the
Cloud Storage API endpoints.

## Verify and upload

For a standalone runner, put the key at
`~/.config/forecastbench-uploader/key.json` (or set `FB_UPLOAD_KEY_FILE`) and
configure the prefix and identity in the private `round.env`:

```sh
FB_UPLOAD_PREFIX='gs://your-submission-bucket/your-team-prefix/binary'
FB_UPLOAD_ACCOUNT='forecastbench-uploader@your-project.iam.gserviceaccount.com'
```

Do not append a round date: the uploader takes it from `question_set.json`.
Managed installations read the same settings from the private uploader
`settings.json` written by `airo configure-forecastbench`; explicit environment
settings override those values. If no key file exists, the uploader can instead
use `gcloud` with an already configured service account and private
`CLOUDSDK_CONFIG`. It explicitly selects the configured service account and
never falls back to a personal account. Missing configuration or failed
authentication pages `upload FAILED` and makes the scheduled run fail.

After the organizers grant access, verify an actual upload from the runner using
a test filename and location agreed with them. `gcloud auth list` alone does not
prove that credentials can refresh or that the account can write to the bucket.
Do not place a test forecast into a live round without their agreement.

For a real submission, configure the destination from the round invitation and
run the upload-only command (also used by `scripts/fb_cron.sh` after a successful
round). This retries saved forecasts without any paid model calls:

```sh
set -a
source "$HOME/.config/fri-forecaster/round.env"
set +a
"$PY" -m forecastbench.upload --root "$ROUNDS_DIR/YYYY-MM-DD"
```

The uploader selects only the registry's submitted conditions, checks each
file's identity, build hashes, aggregate coverage and every member's coverage,
and refuses rehearsals or uploads outside the round's UTC date. Existing builds
without the new provenance hashes must be rebuilt with `forecastbench build`;
this reads saved member results without calling forecasting providers.

Uploads use a generation precondition to refuse overwrites. Success requires
the server's object name, size, MD5 checksum, generation and creation timestamp
to match. On a retry, an existing identical object is verified and retained; a
different object fails. No question sets, provenance files or logs are uploaded.
Only the submitted conditions go up, subject to the registry's submission limits.
The private round directory retains `upload-receipt.json` with per-object
confirmations. If a round partially uploads, rerun this command before the
deadline to verify existing files and upload the rest.

Keep the runtime configuration and receipts outside git. Provision credentials
on production and deploy the checked code through the normal release process;
editing the development checkout does not enable live uploads.

References: [service-account creation](https://docs.cloud.google.com/iam/docs/service-accounts-create),
[service-account keys](https://docs.cloud.google.com/iam/docs/keys-create-delete),
[CLI authentication](https://docs.cloud.google.com/sdk/docs/authenticate),
[Cloud Storage uploads](https://docs.cloud.google.com/sdk/gcloud/reference/storage/cp).
