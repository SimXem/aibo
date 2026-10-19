"""redlines.eci -- AIRO's binding of the Epoch Capabilities Index.

The implementation -- fetch, the three snapshot formats, ranking, the
frontier history, staleness -- is fri_forecaster.eci in this repository
(packages/fri-forecaster), shared with the ForecastBench rounds since
2026-10-19; until then this module carried its own copy. What is AIRO's:

  SNAPSHOT_DIR   data/epoch_capabilities_index_YYYY-MM-DD.csv, tracked, so a
                 run's panel is reproducible from the checkout. Nothing is
                 hand-copied (docs/model-set.md): code/cron_run.sh fetches a
                 snapshot before every elicitation.
  PINNED         the vintage Graph 4's capability-vs-skill ladder was built
                 on. Refreshing it moves every tracked artifact, so it is a
                 deliberate, separate change (re-baseline tests/), not
                 something a newer file in data/ does on its own.
  SUPPLEMENT     the snapshot the registry's per-model `eci` comes from for
                 models PINNED predates (Opus 5, GPT-5.6 Sol, Fable 5.1,
                 GPT-6 Astra); only a model neither file has falls through
                 to latest(). Frozen 2026-10-01, when the snapshot started
                 being fetched before every run: Graph 4 draws two of those
                 models, and its x-axis must not move with the panel's index.
  latest()       the newest snapshot by date in the filename. This is what
                 the MODEL PANEL is selected from (redlines.registry.panel):
                 the k highest-ECI models the registry can run. A panel picked
                 from a stale index is a stale panel, so anything that selects
                 from latest() checks its age and WARNs past STALE_AFTER_DAYS.

    python3 -m redlines.eci          # snapshots, age, the current top of the index
    python3 -m redlines.eci --fetch  # code/cron_run.sh, before every elicitation
"""
import sys
from datetime import date

from .config import REPO_ROOT

try:
    from fri_forecaster import eci as _shared
except ImportError:
    # One repository: the harness's source sits beside this package, so a bare
    # checkout builds without installing it (pip install -e packages/fri-forecaster).
    sys.path.insert(0, str(REPO_ROOT / "packages" / "fri-forecaster"))
    from fri_forecaster import eci as _shared

SNAPSHOT_DIR = REPO_ROOT / "data"
SNAPSHOT_PREFIX = _shared.SNAPSHOT_PREFIX
SNAPSHOT_URL = "https://epoch.ai/benchmarks/eci"
SCORES_URL = _shared.SCORES_URL
SCORES_COLUMNS = _shared.SCORES_COLUMNS
MIN_SCORED = _shared.MIN_SCORED
STALE_AFTER_DAYS = _shared.STALE_AFTER_DAYS
US = _shared.US
PINNED = date(2026, 7, 7)
SUPPLEMENT = date(2026, 9, 8)

load = _shared.load


# Every function reads SNAPSHOT_DIR at call time, so a test can point the
# module at a temporary directory by assignment.
def snapshot_path(day):
    return _shared.snapshot_path(day, SNAPSHOT_DIR)


def snapshots():
    """[(date, path)] of every snapshot under data/, oldest first."""
    return _shared.snapshots(SNAPSHOT_DIR)


def latest():
    """(date, path) of the newest snapshot. Raises if there is none."""
    return _shared.latest(SNAPSHOT_DIR)


def fetch(today=None, url=SCORES_URL, timeout=60):
    """Download Epoch's published scores into data/ as today's snapshot."""
    return _shared.fetch(today, url, timeout, SNAPSHOT_DIR)


def latest_published():
    return _shared.latest_published(SNAPSHOT_DIR)


def frontier_history(path=None, since="2023-03-01", country=US):
    return _shared.frontier_history(path, since, country, SNAPSHOT_DIR)


def ranked(path=None):
    """The snapshot's models, best first: by ECI descending, then Epoch's rank."""
    return _shared.ranked(path, SNAPSHOT_DIR)


def age_days(today=None):
    """Days since the newest snapshot was retrieved (by its filename date)."""
    return _shared.age_days(today, SNAPSHOT_DIR)


def stale_message(today=None):
    """The WARN text if the newest snapshot is older than STALE_AFTER_DAYS, else None."""
    today = today or date.today()
    day, path = latest()
    age = (today - day).days
    if age <= STALE_AFTER_DAYS:
        return None
    return (f"ECI snapshot {path.relative_to(REPO_ROOT)} is {age} days old "
            f"(> {STALE_AFTER_DAYS}); the model panel is selected from it and may no "
            f"longer be the top of the index. Retrieve a new one from {SNAPSHOT_URL} as "
            f"data/{SNAPSHOT_PREFIX}{today.isoformat()}.csv")


def warn_if_stale(today=None, file=sys.stderr):
    """Print the staleness WARN (if any) to `file`; return the message or None."""
    msg = stale_message(today)
    if msg:
        print(f"WARN: {msg}", file=file)
    return msg


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    today = date.today()
    if "--fetch" in argv:
        # code/cron_run.sh, before every elicitation. Exit 1 on failure; the
        # caller decides whether the previous snapshot is still young enough.
        try:
            path = fetch(today)
        except Exception as e:
            print(f"ECI fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        scored = ranked(path)
        print(f"{path.relative_to(REPO_ROOT)}: {len(scored)} scored models; "
              f"top {scored[0]['model']} {scored[0]['eci']:.1f}")
        return 0
    snaps = snapshots()
    print(f"ECI snapshots under {SNAPSHOT_DIR.relative_to(REPO_ROOT)}/:")
    for day, p in snaps:
        idx = load(p)
        tag = "  <- pinned (Graph 4)" if day == PINNED else ""
        tag += "  <- latest" if (day, p) == snaps[-1] else ""
        print(f"  {day}  {len(idx):4d} models  {p.name}{tag}")
    day, path = latest()
    print(f"\nlatest is {(today - day).days} days old (stale after {STALE_AFTER_DAYS})")
    msg = warn_if_stale(today, file=sys.stdout)
    if not msg:
        print("ok: not stale")
    print("\ntop of the index:")
    for r in ranked(path)[:8]:
        ci = f"  [{r['ci_low']}, {r['ci_high']}]" if r.get("ci_low") is not None else ""
        print(f"  {r['rank']:2d}  {r['eci']:6.1f}  {r['model']}{ci}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
