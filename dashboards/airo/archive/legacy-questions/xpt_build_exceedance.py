#!/usr/bin/env python3
"""Regenerate the `xpt_exceedance` blocks in data/starter_questions.json.

The four quantity questions (#15-#18, bioweapon severity rungs) were elicited
as event-count distributions, so they carried no human baseline the dashboard
could put beside a model probability. redlines/xpt.py converts the elicited
percentile ladder into P(N >= 1) -- the same event the models forecast. This
script is the I/O half: it reads the upstream panel, applies that method at
every elicited horizon for both groups, and writes the result back into the
vendored question set with its provenance.

The panel (data/forecasts_anon.csv, 18 MB, 136,394 forecasts) is NOT vendored
-- upstream ships it in xpt-lib and this repo pins the commit and the file's
sha256, which this script verifies before reading. Only the ~120 derived
numbers land in the tracked question set, so nothing downstream needs the CSV.

    # verify the vendored numbers still reproduce (needs the panel)
    python3 code/xpt_build_exceedance.py --forecasts /tmp/forecasts_anon.csv --check

    # fetch the pinned panel, then rewrite the blocks
    python3 code/xpt_build_exceedance.py --fetch --write

Without the panel there is nothing to do: the derived values are already in
data/starter_questions.json, and tests/test_xpt.py checks them against the
pure method without needing the download.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redlines.config import REPO_ROOT, XRISK_CANARIES_ROOT  # noqa: E402
from redlines.xpt import LADDER, THRESHOLD, group_exceedance  # noqa: E402

# Pinned upstream panel. The commit and sha256 are the same pair already
# recorded in data/starter_questions.json's provenance.xpt_panel, which the
# existing per-horizon `xpt` medians were computed from.
XPT_COMMIT = "251acb5254448c9bdb4caa4b5011481c2c149aef"
XPT_SHA256 = "fbdab7cd0df0879ab82301dee0bbe48c76b7a26fb69eb7891777f19b81e7d9e6"
XPT_URL = ("https://raw.githubusercontent.com/forecastingresearch/xpt-lib/"
           f"{XPT_COMMIT}/data/forecasts_anon.csv")

# The super/expert rosters ARE vendored, in the canaries sibling checkout --
# the same files xpt_seed.py::compute_gaps reads.
CANARIES_XPT = XRISK_CANARIES_ROOT / "questions" / "xpt"

STARTER = REPO_ROOT / "data" / "starter_questions.json"
LADDER_NAMES = [name for name, _ in LADDER]

SOURCE_TMPL = (
    "xpt-lib@{commit} data/forecasts_anon.csv (sha256 {sha}) - setName {set!r}, "
    "multiYearDistrib: answerText \"5th %\"..\"95th %\", questionName \"<year>\", "
    "isCurrent=TRUE. Per forecaster P(N >= {thr:g}) by linear interpolation of the "
    "elicited count CDF, then the group median; see redlines/xpt.py for the "
    "method and its censoring rule. Regenerate with "
    "code/xpt_build_exceedance.py --fetch --write."
)


def verify(path):
    """Fail loudly unless `path` is byte-identical to the pinned panel."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    got = h.hexdigest()
    if got != XPT_SHA256:
        raise SystemExit(
            f"{path}: sha256 {got}\n  expected {XPT_SHA256} (xpt-lib@{XPT_COMMIT}).\n"
            "  Refusing to derive human baselines from an unpinned panel.")
    return path


def fetch(dest):
    print(f"fetching {XPT_URL}\n     -> {dest}", file=sys.stderr)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(XPT_URL, dest)
    return verify(dest)


def rosters():
    """(supers, experts) userId sets, from the vendored anonymized rosters."""
    if not CANARIES_XPT.exists():
        raise SystemExit(f"missing vendored XPT rosters: {CANARIES_XPT}")
    with open(CANARIES_XPT / "supers_anon.csv", encoding="utf-8-sig") as f:
        supers = {r["x"] for r in csv.DictReader(f)}
    with open(CANARIES_XPT / "expertsG1_anon.csv", encoding="utf-8-sig") as f:
        experts = {r["userId"] for r in csv.DictReader(f)}
    return supers, experts


def read_ladders(forecasts_path, set_names):
    """setName -> year -> userId -> {answerText: count}, final forecasts only."""
    want, out = set(set_names), {}
    with open(forecasts_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["isCurrent"] != "TRUE" or r["setName"] not in want:
                continue
            if r["answerText"] not in LADDER_NAMES:
                continue
            try:
                v = float(r["forecast"])
            except (TypeError, ValueError):
                continue
            (out.setdefault(r["setName"], {})
                .setdefault(r["questionName"], {})
                .setdefault(r["userId"], {})[r["answerText"]]) = v
    return out


def build(forecasts_path, questions):
    """{question id -> xpt_exceedance block} for every quantity question."""
    supers, experts = rosters()
    quantity = [q for q in questions if q.get("value_kind") == "quantity"]
    ladders = read_ladders(forecasts_path, [q["id"] for q in quantity])

    blocks = {}
    for q in quantity:
        by_year = ladders.get(q["id"], {})
        block = {"threshold": THRESHOLD, "unit": "probability that at least "
                 f"{THRESHOLD:g} event occurs by the horizon"}
        for year in q["horizons"]:
            per_user = by_year.get(str(year), {})
            entry = {}
            for name, group in (("super", supers), ("expert", experts)):
                got = group_exceedance(lad for u, lad in per_user.items() if u in group)
                if got:
                    entry[name] = {"p": round(got["p"], 4),
                                   "censored": got["censored"],
                                   "n": got["n"], "n_bounded": got["n_bounded"]}
            if entry:
                block[str(year)] = entry
        block["source"] = SOURCE_TMPL.format(commit=XPT_COMMIT, sha=XPT_SHA256,
                                             set=q["id"], thr=THRESHOLD)
        blocks[q["id"]] = block
    return blocks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forecasts", type=Path,
                    help="path to the pinned forecasts_anon.csv")
    ap.add_argument("--fetch", action="store_true",
                    help="download the pinned panel first (18 MB)")
    ap.add_argument("--cache", type=Path,
                    default=Path.home() / ".cache" / "redlines" / "forecasts_anon.csv",
                    help="where --fetch writes the panel")
    ap.add_argument("--write", action="store_true",
                    help="rewrite the xpt_exceedance blocks in the question set")
    ap.add_argument("--check", action="store_true",
                    help="recompute and diff against the vendored blocks; "
                         "exit 1 on any mismatch")
    args = ap.parse_args(argv)

    path = args.forecasts
    if args.fetch and not path:
        path = args.cache if args.cache.exists() else fetch(args.cache)
    if not path:
        ap.error("need --forecasts PATH or --fetch")
    verify(path)

    doc = json.loads(STARTER.read_text())
    blocks = build(path, doc["questions"])

    if args.check:
        bad = 0
        for q in doc["questions"]:
            if q["id"] not in blocks:
                continue
            have, want = q.get("xpt_exceedance"), blocks[q["id"]]
            if have != want:
                bad += 1
                print(f"MISMATCH {q['id']}\n  vendored: {have}\n  computed: {want}")
        print(f"{'FAIL' if bad else 'OK'}: {len(blocks) - bad}/{len(blocks)} "
              "xpt_exceedance blocks reproduce from the pinned panel")
        return 1 if bad else 0

    for q in doc["questions"]:
        if q["id"] in blocks:
            q["xpt_exceedance"] = blocks[q["id"]]
            for year, e in blocks[q["id"]].items():
                if not isinstance(e, dict) or "super" not in e:
                    continue
                s = e["super"]
                mark = {"upper": "<", "lower": ">", None: ""}[s["censored"]]
                print(f"  {q['short']:<28} {year}  super {mark}{100 * s['p']:.1f}% "
                      f"(n={s['n']}, {s['n_bounded']} bounded)")

    if args.write:
        STARTER.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {STARTER}")
    else:
        print("(dry run; pass --write to update the question set)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
