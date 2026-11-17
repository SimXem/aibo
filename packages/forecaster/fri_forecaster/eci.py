"""Epoch Capabilities Index: fetch, snapshots, rank -- one implementation.

The published index (https://epoch.ai/data/eci_scores.csv) is the source of
truth for which models are the frontier, FETCHED into dated snapshots and
never hand-copied. AIRO selects its panel from the newest snapshot
(redlines.eci binds this module to its data/ directory and adds the vintages
its charts pin); a ForecastBench round checks that a condition's members are
still the top N (scripts/fb_round.sh). Until 2026-10-19 each carried its own
copy of this code; this is the one.

Snapshots are files named epoch_capabilities_index_YYYY-MM-DD.csv in a
directory: `snapshot_dir`, default $FORECASTER_ECI_DIR, else
~/.cache/fri-forecaster/eci. load() reads the three formats a snapshot has
come in:

  rank format     rank,model,eci,ci_low,ci_high,retrieved -- the leaderboard
                  as retrieved by hand from epoch.ai, integer scores with a
                  confidence interval.
  raw export      Epoch's own CSV export: one row per model VARIANT
                  ("Model version" gpt-5.6-sol_high, "ECI Score" 161.08,
                  "Model name" GPT-5.6 Sol, ...), no interval. Read as the
                  best variant per model name.
  published       Epoch's published per-model scores (Model,Display name,eci,
                  eci_ci_low,eci_ci_high,date,Organization,Country (of
                  organization),...): one row per model, with its interval,
                  release date and developer country. What fetch() writes.

Model names are Epoch's, the strings a registry keys `epoch_name` on. What
is runnable, and the one-seat-per-family rule, belong to the caller's
registry: this module ranks the index and nothing more.

    python -m fri_forecaster.eci [--dir DIR] [--fetch] [--names] [K]
        # the top K (default 8); --names prints model names only, best first,
        # one per line (what a round's `eci_ranked` is expected to print)
"""
import csv
import os
import sys
from datetime import date
from pathlib import Path

SNAPSHOT_PREFIX = "epoch_capabilities_index_"
SCORES_URL = "https://epoch.ai/data/eci_scores.csv"
SCORES_COLUMNS = ("Model", "eci", "eci_ci_low", "eci_ci_high", "date",
                  "Country (of organization)")
# A fetched file is refused (and the previous snapshot kept) below this many
# scored models: a truncated or reshaped download must never become a panel.
MIN_SCORED = 100
# About a month. The index moves whenever a frontier model ships; a model set
# chosen on a snapshot older than this may no longer be the top of the index.
STALE_AFTER_DAYS = 31
US = "United States of America"


def default_dir():
    return Path(os.environ.get("FORECASTER_ECI_DIR") or os.path.expanduser("~/.cache/fri-forecaster/eci"))


def _dir(snapshot_dir):
    return Path(snapshot_dir) if snapshot_dir else default_dir()


def snapshot_path(day, snapshot_dir=None):
    return _dir(snapshot_dir) / f"{SNAPSHOT_PREFIX}{day.isoformat()}.csv"


def snapshots(snapshot_dir=None):
    """[(date, path)] of every snapshot in the directory, oldest first."""
    out = []
    for p in _dir(snapshot_dir).glob(f"{SNAPSHOT_PREFIX}*.csv"):
        stamp = p.stem[len(SNAPSHOT_PREFIX):]
        try:
            out.append((date.fromisoformat(stamp), p))
        except ValueError:
            continue           # not a dated snapshot; not ours to read
    return sorted(out)


def latest(snapshot_dir=None):
    """(date, path) of the newest snapshot. Raises if there is none."""
    snaps = snapshots(snapshot_dir)
    if not snaps:
        raise FileNotFoundError(f"no {SNAPSHOT_PREFIX}*.csv under {_dir(snapshot_dir)} "
                                f"(python -m fri_forecaster.eci --fetch)")
    return snaps[-1]


def _rank_format(rows):
    out = {}
    for r in rows:
        out[r["model"]] = {"model": r["model"], "eci": float(r["eci"]),
                           "ci_low": int(r["ci_low"]) if r.get("ci_low") else None,
                           "ci_high": int(r["ci_high"]) if r.get("ci_high") else None,
                           "rank": int(r["rank"]), "retrieved": r.get("retrieved")}
    return out


def _raw_export(rows):
    best = {}
    for r in rows:
        name, score = r.get("Model name") or r.get("Model version"), r.get("ECI Score")
        if not name or not score:
            continue
        s = float(score)
        if name not in best or s > best[name]["eci"]:
            best[name] = {"model": name, "eci": s, "ci_low": None, "ci_high": None,
                          "variant": r.get("Display name") or r.get("Model version"),
                          "release_date": r.get("Release date")}
    for i, rec in enumerate(sorted(best.values(), key=lambda x: -x["eci"]), 1):
        rec["rank"] = i
    return best


def _float_or_none(v):
    return float(v) if v else None


def _published(rows):
    out = {}
    for r in rows:
        if not r.get("Model") or not r.get("eci"):
            continue
        out[r["Model"]] = {"model": r["Model"], "eci": float(r["eci"]),
                           "ci_low": _float_or_none(r.get("eci_ci_low")),
                           "ci_high": _float_or_none(r.get("eci_ci_high")),
                           "release_date": r.get("date") or None,
                           "country": r.get("Country (of organization)") or None,
                           "organization": r.get("Organization") or None,
                           "access": r.get("Accessibility group") or None}
    for i, rec in enumerate(sorted(out.values(), key=lambda x: (-x["eci"], x["model"])), 1):
        rec["rank"] = i
    return out


def load(path):
    """One snapshot -> {model name: {model, eci, ci_low, ci_high, rank, ...}},
    in any of the three formats."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)
    if "eci" in fields and "model" in fields:
        return _rank_format(rows)
    if "ECI Score" in fields:
        return _raw_export(rows)
    if "eci" in fields and "Model" in fields:
        return _published(rows)
    raise ValueError(f"{path}: not an ECI snapshot in any known format (columns {fields})")


def fetch(today=None, url=SCORES_URL, timeout=60, snapshot_dir=None):
    """Download Epoch's published scores as today's snapshot and return its
    path. Raises (writing nothing) when the download fails or does not look
    like the index -- missing columns, fewer than MIN_SCORED scored models --
    so a bad day leaves the previous snapshot in charge."""
    import urllib.request
    today = today or date.today()
    req = urllib.request.Request(url, headers={"User-Agent": "fri-forecaster (fri_forecaster.eci)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    missing = [c for c in SCORES_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"{url}: columns {missing} missing (got {reader.fieldnames})")
    scored = _published(list(reader))
    if len(scored) < MIN_SCORED:
        raise ValueError(f"{url}: only {len(scored)} scored models (< {MIN_SCORED})")
    path = snapshot_path(today, snapshot_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def latest_published(snapshot_dir=None):
    """(date, path) of the newest snapshot in the published format -- the
    only one that carries release dates and countries, which the frontier
    history needs. Raises if there is none."""
    for day, path in reversed(snapshots(snapshot_dir)):
        with open(path, newline="", encoding="utf-8") as f:
            if "Country (of organization)" in (csv.DictReader(f).fieldnames or []):
                return day, path
    raise FileNotFoundError(f"no published-format {SNAPSHOT_PREFIX}*.csv under {_dir(snapshot_dir)} "
                            f"(python -m fri_forecaster.eci --fetch)")


def frontier_history(path=None, since="2023-03-01", country=US, snapshot_dir=None):
    """Every release from a `country` developer that set a new ECI high, in
    release order, from `since` on: [(date, score, model)]. Same-day releases
    go in score order, so each is a new high when it beats the one before.
    Models released before `since` still raise the bar."""
    path = path or latest_published(snapshot_dir)[1]
    rows = sorted((r for r in load(path).values()
                   if r.get("country") == country and r.get("release_date")),
                  key=lambda r: (r["release_date"], r["eci"]))
    out, high = [], float("-inf")
    for r in rows:
        if r["eci"] > high:
            high = r["eci"]
            if r["release_date"] >= since:
                out.append((r["release_date"], round(r["eci"], 1), r["model"]))
    return out


def ranked(path=None, snapshot_dir=None):
    """The snapshot's models, best first: by ECI descending, then Epoch's rank."""
    idx = load(path or latest(snapshot_dir)[1])
    return sorted(idx.values(), key=lambda r: (-r["eci"], r["rank"]))


def age_days(today=None, snapshot_dir=None):
    """Days since the newest snapshot was retrieved (by its filename date)."""
    today = today or date.today()
    day, _ = latest(snapshot_dir)
    return (today - day).days


def stale_message(today=None, snapshot_dir=None):
    """The WARN text if the newest snapshot is older than STALE_AFTER_DAYS, else None."""
    today = today or date.today()
    day, path = latest(snapshot_dir)
    age = (today - day).days
    if age <= STALE_AFTER_DAYS:
        return None
    return (f"ECI snapshot {path.name} is {age} days old (> {STALE_AFTER_DAYS}); a model "
            f"set chosen from it may no longer be the top of the index. Fetch a new one: "
            f"python -m fri_forecaster.eci --fetch")


def warn_if_stale(today=None, file=sys.stderr, snapshot_dir=None):
    """Print the staleness WARN (if any) to `file`; return the message or None."""
    msg = stale_message(today, snapshot_dir)
    if msg:
        print(f"WARN: {msg}", file=file)
    return msg


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    snapshot_dir = None
    if "--dir" in args:
        i = args.index("--dir")
        snapshot_dir = args[i + 1]
        del args[i:i + 2]
    refetch, names = "--fetch" in args, "--names" in args
    k = next((int(a) for a in args if a.isdigit()), 8)
    if refetch:
        try:
            path = fetch(snapshot_dir=snapshot_dir)
        except Exception as e:
            print(f"ECI fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
    else:
        try:
            path = latest(snapshot_dir)[1]
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 1
    warn_if_stale(snapshot_dir=snapshot_dir)
    top = ranked(path, snapshot_dir)[:k]
    if names:
        print("\n".join(r["model"] for r in top))
    else:
        print(f"{path}: top {len(top)} of {len(load(path))} scored models")
        for r in top:
            ci = f"  [{r['ci_low']}, {r['ci_high']}]" if r.get("ci_low") is not None else ""
            print(f"  {r['rank']:2d}  {r['eci']:6.1f}  {r['model']}{ci}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
