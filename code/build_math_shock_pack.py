#!/usr/bin/env python3
"""Build the math-shock pack (redlines/math_shock.py) from a run of the
math-problem knowledge-shock project. Reads that checkout, never writes to it.

    python code/build_math_shock_pack.py --source ../math_problem_knowledge_shock --run w1-r1

Writes <AIRO_PRETASK_DIR, default private/pretasks/>/math-shock-<run>.json --
outside git -- and prints its SHA-256 for code/run_math_shock.py to pin.

Checks, any failure stops the build:
  - the run's sample, sample log and every statement file match the hashes in
    its run.lock.json, and the statements are approved;
  - PARITY with the project's own rendered prompts: the math prompt rendered
    from the pack, in each recorded conversation's order and on its run date,
    equals that conversation's forecast prompt byte for byte; and the reveal
    rendered from the pack and that conversation's parsed forecasts equals the
    project's follow-up prompt up to where the project asks for revised
    forecasts (each follow-up of the run that has been built).
Stdlib only: the project's YAML configs are not read; run.lock.json holds T0,
S and the run date.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from redlines import math_shock as ms  # noqa: E402

APPROVED = ("approved", "auto-approved (no human review)")   # the project's APPROVED_STATUSES


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def jsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def check_hash(path, want, what):
    got = ms.sha256_bytes(Path(path).read_bytes())
    if got != want:
        sys.exit(f"{what}: {path} has SHA-256 {got}, run.lock.json says {want}")


def build(source, run_id):
    src = Path(source).resolve()
    run = src / "runs" / run_id
    lock = json.loads((run / "run.lock.json").read_text())
    if lock["run_id"] != run_id:
        sys.exit(f"{run}/run.lock.json is for run {lock['run_id']!r}")
    if lock["statements_status"] not in APPROVED:
        sys.exit(f"statements are {lock['statements_status']!r}, not approved")
    for name in ("sample.csv", "sample_log.json", "prompts.jsonl"):
        check_hash(run / name, lock["artifacts"][name], name)
    statements = {}
    for name, want in sorted(lock["statement_files"].items()):
        path = src / "statements" / name
        check_hash(path, want, "statement")
        s = json.loads(path.read_text(encoding="utf-8"))
        if not s.get("approved") or not s.get("approved_text"):
            sys.exit(f"{path}: not an approved statement")
        statements[s["unit_id"]] = s["approved_text"]
    sample = read_csv(run / "sample.csv")
    missing = [r["unit_id"] for r in sample if r["unit_id"] not in statements]
    if missing:
        sys.exit(f"no approved statement for {missing}")
    commit = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip() or None
    pack = {
        "pack": f"math-shock-{run_id}", "format": ms.PACK_FORMAT,
        "source": {"project": "math_problem_knowledge_shock", "commit": commit, "run_id": run_id,
                   "wave": lock["wave"], "rules_version": lock["rules_version"],
                   "config_hash": lock["config_hash"],
                   "run_lock_sha256": ms.sha256_bytes((run / "run.lock.json").read_bytes()),
                   "statements_status": lock["statements_status"]},
        "t0": lock["t0"], "snapshot_date": lock["snapshot_date"], "source_run_date": lock["run_date"],
        "sample_log": json.loads((run / "sample_log.json").read_text()),
        "problems": [{"unit_id": r["unit_id"], "code": r["code"], "role": r["role"], "stratum": r["stratum"],
                      "display_name": r["display_name"], "solved": int(r["solved"]),
                      "solve_date": r["solve_date"], "outcome_type": r["outcome_type"],
                      "statement": statements[r["unit_id"]]} for r in sample],
        "templates": {"forecast": (src / "templates" / "v1" / "forecast.txt").read_text(encoding="utf-8"),
                      "reveal_solved": (src / "templates" / "followup_v1" / "reveal_solved.txt")
                      .read_text(encoding="utf-8")},
    }
    return pack, run


def parity(pack, run):
    """The project's recorded prompts, re-rendered from the pack."""
    convs = {(c["model"], int(c["sample_idx"])): c for c in jsonl(run / "prompts.jsonl")}
    for c in convs.values():
        mine = ms.math_prompt(pack, c["order"], pack["source_run_date"])
        if mine != c["forecast_prompt"]:
            sys.exit(f"parity: the math prompt for {c['model']} s{c['sample_idx']} differs from the project's")
    print(f"parity: {len(convs)} math prompts reproduced byte for byte")
    parsed = {}
    if (run / "parsed.csv").exists():
        for r in read_csv(run / "parsed.csv"):
            parsed.setdefault((r["model"], int(r["sample_idx"])), []).append(r)
    n = 0
    for fu in sorted((run / "followups").glob("*/prompts.jsonl")):
        for f in jsonl(fu):
            key = (f["model"], int(f["sample_idx"]))
            codes = convs[key]["order"]
            mine = ms.reveal(pack, codes, parsed[key])
            # The two agree up to the end of REVEAL_CUT's sentence, less its full stop.
            stem = mine[:mine.rindex(":\n\n")]
            if not f["followup_prompt"].startswith(stem + "."):
                sys.exit(f"parity: the reveal for {f['model']} s{f['sample_idx']} ({fu.parent.name}) "
                         "differs from the project's")
            n += 1
    print(f"parity: {n} reveals reproduced up to the project's re-forecast request")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", required=True, help="a checkout of the math-problem knowledge-shock project")
    ap.add_argument("--run", default="w1-r1", help="its run id (runs/<id>/)")
    ap.add_argument("--out-dir", default=None, help=f"default: ${ms.PRETASK_DIR_ENV} or private/pretasks/")
    args = ap.parse_args()
    pack, run = build(args.source, args.run)
    parity(pack, run)
    out = ms.pack_path(pack["pack"], args.out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(pack, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")
    if out.exists() and out.read_bytes() != data:
        sys.exit(f"{out} exists with other contents; a changed pack is a new pack (move the old one first)")
    out.write_bytes(data)
    st = ms.stats(pack)
    print(f"{out}: {st['n_items']} problems, {st['n_solved']} solved ({st['n_guaranteed']} guaranteed, "
          f"{st['n_random_solved']} of {st['n_random']} random); pool {st['n_pool_solved']}/{st['n_eligible']} "
          f"({st['pool_pct']}%); T0 {pack['t0']}, S {pack['snapshot_date']}")
    print(f"pack {pack['pack']} sha256 {ms.sha256_bytes(data)}")


if __name__ == "__main__":
    main()
