# notify TITLE MESSAGE [PRIORITY] -- one alert from the scripts a scheduled job
# runs (source this file). The shared sender decides where it goes
# (fri_forecaster.alert: the installation's alerts file); this only maps the
# old priorities onto its severities: `high` pages, anything else is a notice.
# NOTIFY_DEPLOYMENT names the deployment (default airo); the interpreter is the
# caller's PY, else the checkout's venv. Never fatal.
notify() {
    local severity=notice
    [ "${3:-default}" = high ] && severity=page
    "${PY:-$REPO/../../.venv/bin/python}" -m fri_forecaster.alert send --deployment "${NOTIFY_DEPLOYMENT:-airo}" \
        --severity "$severity" --title "$1" "$2" || echo "WARN: alert not sent: $1"
}
