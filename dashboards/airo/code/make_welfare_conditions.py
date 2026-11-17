#!/usr/bin/env python3
"""The welfare scenario set, data/welfare_conditions.json (2026-10-22): AIRO's
combined set (data/combined_conditions.json, code/make_combined_conditions.py)
copied verbatim, but for the keys the welfare set owns -- its title, slug,
protocol, questions and copied_from.

The combined set quotes the newest Epoch ECI snapshot and is regenerated from
it (code/check_eci_snapshot.py --rebuild), so this copy goes stale whenever
the combined set changes. A welfare run refuses a stale copy
(code/run_unified.py eci_preflight), as AIRO's refuses a stale snapshot.

    python3 code/make_welfare_conditions.py           # re-copy the combined set
    python3 code/make_welfare_conditions.py --check   # is the copy current?

A new combined protocol is a new instrument, so the copy then needs a new
welfare protocol as well, which keeps welfare's rows legible:
    python3 code/make_welfare_conditions.py --protocol welfare-joint-v2
Without one, the copy refuses. copied_from.on is the day the copied content
last changed.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMBINED_FILE = "data/combined_conditions.json"       # what copied_from names
COMBINED = os.path.join(ROOT, COMBINED_FILE)
OUT = os.path.join(ROOT, "data", "welfare_conditions.json")
# The welfare folder's copy of the same file (welfare/README.md), rewritten with OUT.
MIRROR = os.path.join(ROOT, "welfare", "welfare_conditions.json")
# The keys the welfare set owns (tests/test_welfare.py OWN); every other key
# is the combined set's.
OWN = ("title", "slug", "protocol", "questions", "copied_from")
NOTE = ("Every key below except title, slug, protocol, questions and copied_from is the combined "
        "set's, verbatim. Re-copy when the combined set changes (code/make_welfare_conditions.py).")


def build(combined, current, protocol=None, today=None):
    """The welfare set: `combined`'s keys in its order, the welfare set's own
    from `current` (questions and copied_from right after protocol, as the
    first copy had them). -> (doc, changed): changed when the copied content
    or the protocol differs from `current`'s."""
    was = current["copied_from"]
    if combined["protocol"] != was["protocol"] and not protocol:
        raise ValueError(f"the combined set is now {combined['protocol']} (copied from {was['protocol']}): "
                         f"a new instrument, so name welfare's new protocol (now {current['protocol']}) "
                         "with --protocol")
    shared = {k: v for k, v in combined.items() if k not in OWN}
    changed = (shared != {k: v for k, v in current.items() if k not in OWN}
               or (protocol or current["protocol"]) != current["protocol"])
    doc = {}
    for k, v in combined.items():
        if k in ("title", "slug"):
            doc[k] = current[k]
        elif k == "protocol":
            doc[k] = protocol or current["protocol"]
            doc["questions"] = current["questions"]
            doc["copied_from"] = {
                "file": COMBINED_FILE, "protocol": combined["protocol"],
                "on": (today or datetime.now(timezone.utc).date()).isoformat() if changed else was["on"],
                "note": NOTE if changed else was["note"]}
        elif k not in OWN:
            doc[k] = v
    return doc, changed


def text(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Re-copy AIRO's combined set as the welfare set "
                                             "(see this file's docstring)")
    ap.add_argument("--check", action="store_true", help="fail unless the copy is current; write nothing")
    ap.add_argument("--protocol", help="welfare's new protocol, when the combined set's has changed")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    combined = json.load(open(COMBINED, encoding="utf-8"))
    cur_text = open(args.out, encoding="utf-8").read()
    current = json.loads(cur_text)
    try:
        doc, changed = build(combined, current, None if args.check else args.protocol)
    except ValueError as e:
        if args.check:
            sys.exit(f"{os.path.relpath(args.out, ROOT)} is stale: {e} "
                     f"(python3 {os.path.relpath(__file__, ROOT)} --protocol <new>)")
        sys.exit(f"refusing: {e}")
    if args.check:
        if changed or text(doc) != cur_text:
            sys.exit(f"{os.path.relpath(args.out, ROOT)} is stale: the combined set changed since it was "
                     f"copied on {current['copied_from']['on']} -- rerun python3 {os.path.relpath(__file__, ROOT)}")
        print("ok")
        return 0
    paths = [args.out] + ([MIRROR] if os.path.abspath(args.out) == os.path.abspath(OUT) else [])
    for p in paths:
        if not os.path.exists(p) or open(p, encoding="utf-8").read() != text(doc):
            with open(p, "w", encoding="utf-8") as f:
                f.write(text(doc))
            print(f"{os.path.relpath(p, ROOT)}: re-copied from {combined['protocol']} as {doc['protocol']}")
        else:
            print(f"{os.path.relpath(p, ROOT)}: current ({combined['protocol']}, copied {doc['copied_from']['on']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
