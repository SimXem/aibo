# notify TITLE MESSAGE [PRIORITY] [TAGS] -- one line to the operator's phone,
# for the scripts the box's crontab runs (source this file). The topic is
# NTFY_TOPIC, else the one in ~/.config/redlines/env. Anyone who knows it can
# read the channel, so messages say what failed, never data. A no-op without
# a topic; a failed push is logged, never fatal.
notify() {
    local topic="${NTFY_TOPIC:-$(sed -n 's/^NTFY_TOPIC=//p' "$HOME/.config/redlines/env" 2>/dev/null | tr -d "\"'")}"
    [ -n "$topic" ] || return 0
    curl -fsS -m 20 -H "Title: $1" -H "Priority: ${3:-default}" -H "Tags: ${4:-}" \
        --data-binary "$2" "https://ntfy.sh/$topic" >/dev/null \
        || echo "WARN: ntfy push failed: $1"
}
