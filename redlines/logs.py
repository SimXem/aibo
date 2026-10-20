"""Instrument logs, one file per run.

A conditional log keeps its name -- results/conditional_runs_<slug>.jsonl --
but lives on disk as a folder of the same name without the suffix, holding
one <run_id>.jsonl per run. A single growing file passed GitHub's 100 MB
limit with the 2026-09-18 run (every row carries its call's rationale and
sources). Callers keep passing the .jsonl name; these helpers resolve it. A
path that is an actual file (an experiment's own log) is read as it is.

THE SCENARIO FIELDS. A row names the scenario its probabilities are
conditional on `scenario` (None for the unconditional), the set it came from
`scenario_set`, and its call's whole list `joint_scenarios`. Rows written
before 2026-10-21 use the prompt's and LEAP's word for all three
(`condition`, `condition_set`, `joint_conditions`), from before `condition`
came to mean the configured way a call is run (redlines.experiments). read_row
gives an old row the new names, so every reader sees one shape; the files on
disk are records and are never rewritten. An old row's condition is its
prompt variant ("none" before the variants): until 2026-10-21 a variant was
all that set one call of a run apart from another, and the airo experiment's
conditions are named after them.
"""
import json
from pathlib import Path

LEGACY_FIELDS = {"condition": "scenario", "condition_set": "scenario_set",
                 "joint_conditions": "joint_scenarios"}


def shard_dir(path):
    p = Path(path)
    return p.with_suffix("") if p.suffix == ".jsonl" else p


def log_files(path):
    """The files that make up a log, oldest run first."""
    p = Path(path)
    if p.is_file():
        return [p]
    d = shard_dir(p)
    return sorted(d.glob("*.jsonl")) if d.is_dir() else []


def log_exists(path):
    return bool(log_files(path))


def read_row(line):
    """One JSON line -> a row in the current shape (LEGACY_FIELDS)."""
    row = json.loads(line)
    if "scenario" not in row and "condition" in row:
        for old, new in LEGACY_FIELDS.items():
            if old in row:
                row[new] = row.pop(old)
        row["condition"] = row.get("variant") or "none"
    return row


def iter_rows(path):
    for f in log_files(path):
        with open(f) as fh:
            for line in fh:
                if line.strip():
                    yield read_row(line)


def run_file(path, run_id):
    """Where a run's rows go: <log folder>/<run_id>.jsonl, folder created."""
    d = shard_dir(path)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{run_id}.jsonl"


def log_names(results_dir, prefix="conditional_runs"):
    """Every log under results_dir by its .jsonl name, from files or folders."""
    names = {p.with_suffix(".jsonl") if p.is_dir() else p
             for p in Path(results_dir).glob(prefix + "*") if p.is_dir() or p.suffix == ".jsonl"}
    return sorted(names)
