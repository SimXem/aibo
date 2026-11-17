"""Alerts: one line to whoever must act, from any job in the repo.

A caller says WHAT happened and never where it goes:

    alert.send("forecastbench", "key refused", "anthropic's API key was refused ...", severity="page")
    python -m fri_forecaster.alert send --deployment airo --severity page --title "run failed" "exit 1 ..."

`deployment` names the thing that runs (airo, forecastbench, scheduler, ...).
`severity` is `page` (someone must act, usually before a deadline) or `notice`
(degraded, no deadline). There is no success message: silence has to be
watched from outside the box.

WHERE it goes is the installation's, read when the alert is sent, from
$FRI_ALERTS_FILE, else ~/.config/fri-forecaster/alerts.json:

    {"channels": [
      {"kind": "ntfy", "topic": "..."},
      {"kind": "ntfy", "topic": "...", "deployments": ["forecastbench"], "severities": ["page"]}
    ]}

A channel takes every alert unless it names `deployments` or `severities`.
A new transport (Slack, PagerDuty) is one function in TRANSPORTS and a `kind`
in that file; no caller changes. The file is private: a channel's address is
its only lock, so messages say what failed and where the log is, never data.

Without that file nothing is sent and the line goes to stderr: right for a
laptop and for tests. A production installation must have one; `check` says so
(the deployment runs it) and `test` sends one line down every channel.

Sending never raises and never fails the caller's job: a failed push is
reported on stderr, and send() returns how many channels took the alert.
With $FRI_ALERT_LEDGER set (the scheduler sets it per job) each alert is also
appended there, so the scheduler knows what a job already said.
"""
import json
import os
import socket
import sys
import time
import urllib.request

SEVERITIES = ("page", "notice")


def config_path():
    return os.environ.get("FRI_ALERTS_FILE") or os.path.expanduser("~/.config/fri-forecaster/alerts.json")


def channels(path=None):
    """The installation's channels; [] when it has no alerts file."""
    path = path or config_path()
    if not os.path.exists(path):
        return []
    with open(path) as f:
        found = json.load(f).get("channels", [])
    for ch in found:
        if ch.get("kind") not in TRANSPORTS:
            raise ValueError(f"{path}: unknown channel kind {ch.get('kind')!r} (known: {', '.join(TRANSPORTS)})")
        if set(ch.get("severities", SEVERITIES)) - set(SEVERITIES):
            raise ValueError(f"{path}: severities are {', '.join(SEVERITIES)}")
    return found


def takes(channel, deployment, severity):
    return (deployment in channel.get("deployments", [deployment])
            and severity in channel.get("severities", SEVERITIES))


def _post(url, body, headers, timeout=20):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def ntfy(channel, title, message, severity):
    """https://ntfy.sh: {"kind": "ntfy", "topic": ..., "server": optional}."""
    server = channel.get("server", "https://ntfy.sh").rstrip("/")
    _post(f"{server}/{channel['topic']}", message.encode(),
          {"Title": title.encode("ascii", "replace").decode(),
           "Priority": "high" if severity == "page" else "default",
           "Tags": "rotating_light" if severity == "page" else "warning"})


TRANSPORTS = {"ntfy": ntfy}


def send(deployment, title, message, severity="page", log=None, post=None):
    """Send one alert down every channel that takes it. -> channels reached."""
    if severity not in SEVERITIES:
        raise ValueError(f"severity is one of {', '.join(SEVERITIES)}")
    title = f"{deployment}: {title}"
    body = message + (f"\nlog: {log}" if log else "") + f"\non {socket.gethostname()}"
    try:
        chosen = [c for c in channels() if takes(c, deployment, severity)]
    except (ValueError, OSError) as e:
        print(f"ALERT NOT SENT (bad alerts file: {e}): [{severity}] {title}: {message}", file=sys.stderr)
        chosen = None
    sent = 0
    for ch in chosen or []:
        try:
            (post or TRANSPORTS[ch["kind"]])(ch, title, body, severity)
            sent += 1
        except Exception as e:   # a dead channel must not take the job, or the next channel, with it
            print(f"WARN: alert not delivered by {ch['kind']} ({type(e).__name__}): {title}", file=sys.stderr)
    if chosen == []:
        print(f"ALERT (no channel configured): [{severity}] {title}: {message}", file=sys.stderr)
    ledger = os.environ.get("FRI_ALERT_LEDGER")
    if ledger:
        try:
            with open(ledger, "a") as f:
                f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "deployment": deployment,
                                    "severity": severity, "title": title, "sent": sent}) + "\n")
        except OSError:
            pass
    return sent


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m fri_forecaster.alert", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="send one alert")
    s.add_argument("--deployment", required=True)
    s.add_argument("--severity", default="page", choices=SEVERITIES)
    s.add_argument("--title", required=True)
    s.add_argument("--log", help="where to look, added to the message")
    s.add_argument("message")
    sub.add_parser("check", help="exit 1 unless this installation has a channel for a page")
    sub.add_parser("test", help="send one test line down every channel")
    args = ap.parse_args(argv)
    if args.cmd == "send":
        send(args.deployment, args.title, args.message, severity=args.severity, log=args.log)
        return 0   # never the caller's failure
    try:
        found = channels()
    except (ValueError, OSError) as e:
        print(f"alerts: {e}", file=sys.stderr)
        return 1
    if not any("page" in c.get("severities", SEVERITIES) and "deployments" not in c for c in found):
        print(f"alerts: no channel in {config_path()} takes a page from every deployment", file=sys.stderr)
        return 1
    if args.cmd == "check":
        print(f"alerts: {len(found)} channel(s): {', '.join(sorted({c['kind'] for c in found}))}")
        return 0
    sent = 0
    for ch in found:   # every channel, whatever it filters on
        try:
            TRANSPORTS[ch["kind"]](ch, "alerts: test", f"A test of this alert channel; nothing is wrong.\non {socket.gethostname()}", "notice")
            sent += 1
            print(f"alerts: test sent by {ch['kind']}")
        except Exception as e:
            print(f"alerts: test NOT delivered by {ch['kind']} ({type(e).__name__})", file=sys.stderr)
    return 0 if sent == len(found) else 1


if __name__ == "__main__":
    sys.exit(main())
