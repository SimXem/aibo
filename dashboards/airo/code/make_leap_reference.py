#!/usr/bin/env python3
"""data/leap/axes-<date>.json (internal) -> data/leap_reference.json (tracked).

The LEAP survey material under data/leap/ is internal to FRI and is not
published: the survey documents, the full per-panel answer distributions, and
questions the dashboard never shows. The dashboard does show one thing from
it -- for a handful of questions, each panel's n and the median across
panelists of each percentile asked -- as the reference lines on the axes and
capability panels. This script extracts exactly that into a tracked file, so
a public clone builds the page without the internal source, and the internal
source is needed only to regenerate the extract.

    python3 code/make_leap_reference.py            # write data/leap_reference.json
    python3 code/make_leap_reference.py --check    # verify the tracked extract is current
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE = os.path.join(ROOT, "data", "leap", "axes-2026-09-02.json")
OUT = os.path.join(ROOT, "data", "leap_reference.json")

# The questions the page or the scenario generators refer to, and nothing
# else: the dashboard's revenue and AGI-year axes (with the AGI-before-2100
# probability that accompanies the year), LEAP's forecast of the US frontier
# ECI (the capability panel's reference), and the paper set's three axes.
KEEP = ("revenue", "agi_year", "agi_p", "eci_us", "gdp", "lfpr", "metr")
META = ("survey", "fielded", "question_group", "dimension", "what", "text", "unit")
# The FRI staff panel is never drawn; the three published panels are.
DROP_PANELS = {"fri"}


def build(source=SOURCE):
    with open(source, encoding="utf-8") as fh:
        leap = json.load(fh)
    axes = {}
    for key in KEEP:
        a = leap["axes"].get(key)
        if not a:
            continue
        answers = {}
        for date, pcts in a["answers"].items():
            for pct, panels in pcts.items():
                for panel, v in panels.items():
                    if panel in DROP_PANELS:
                        continue
                    answers.setdefault(date, {}).setdefault(pct, {})[panel] = {
                        "n": v["n"], "median": v["median"]}
        axes[key] = {**{m: a[m] for m in META if m in a}, "answers": answers}
    return {
        "what": "Per-panel aggregates (n and the median across panelists of each asked "
                "percentile) of the LEAP survey questions the dashboard and its condition "
                "sets refer to. Extracted from FRI's internal LEAP pull "
                f"({os.path.relpath(source, ROOT)}, not published) by "
                f"{os.path.relpath(__file__, ROOT)}; the internal file also holds the survey "
                "documents, the full answer distributions and further questions.",
        "pulled": leap.get("pulled"),
        "panels": sorted({p for ax in axes.values() for d in ax["answers"].values()
                          for ps in d.values() for p in ps}),
        "axes": axes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    if not os.path.exists(SOURCE):
        # A public clone: the internal source is absent by design, so there is
        # nothing to regenerate or check against; the tracked extract stands.
        sys.exit(f"{os.path.relpath(SOURCE, ROOT)} is not present (internal source); "
                 f"the tracked {os.path.relpath(args.out, ROOT)} stands as is")
    text = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if args.check:
        cur = open(args.out, encoding="utf-8").read() if os.path.exists(args.out) else ""
        if cur != text:
            sys.exit(f"{args.out} is stale -- rerun {os.path.relpath(__file__, ROOT)}")
        print("ok")
        return
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    doc = json.loads(text)
    for k, a in doc["axes"].items():
        print(f"  {k:9} {a.get('survey', '?'):40.40} dates {list(a['answers'])}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
