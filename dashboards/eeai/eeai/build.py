"""The run files -> the page's data (window.__EEAI__) and the page.

    python3 -m eeai build                       # eeai/results/runs -> eeai/site/ (index.html, eeai-data.zip, web/)
    python3 -m eeai build --runs DIR --site DIR # other run files, another folder
    python3 -m eeai build --out FILE            # only the page (and the download beside it)

The site folder is self-contained: any static web server can serve it.

Pure: reads eeai/data and the run files, calls nothing. The ensemble is the
median across the panel of each value on its own -- of the medians, and of the
10th and of the 90th percentiles -- within a run. A run's rows are the ones
under the current instrument or one it continues (survey.instruments).

A question is asked at several dates. The page shows, for each date, the
forecast of the latest run that asked about it: a run stops asking once a
date has passed, so a past date keeps its last forecast. When the record
(eeai/data/history.csv) has a value for a date, that is the outcome the
forecast is set against.

The page is assembled from eeai/web/ by the dashboard kit (packages/dashboard).
"""
import json
import statistics
from pathlib import Path

from . import config, export, survey as S


def load_runs(runs_dir=None, instrument=None):
    """[(run_id, rows)] oldest first, rows under `instrument` (a name or a list of names) only."""
    instrument = [instrument] if isinstance(instrument, str) else instrument
    runs = []
    for p in sorted(Path(runs_dir or config.RUNS).glob("*.jsonl")):
        # split("\n"), not splitlines(): fetched pages carry U+2028 and the like inside strings.
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").split("\n") if line.strip()]
        rows = [r for r in rows if instrument is None or r.get("instrument") in instrument]
        if rows:
            runs.append((p.stem, rows))
    return runs


def _asked_at(run_id, run_date):
    """When a run was made, as an ISO time: from its id (2026-11-11T2258Z), else its date."""
    from datetime import datetime
    try:
        return datetime.strptime(run_id, "%Y-%m-%dT%H%MZ").strftime("%Y-%m-%dT%H:%M:00Z")
    except ValueError:
        return f"{run_date}T00:00:00Z"


def _median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 4) if values else None


def ensemble(survey, question, rows):
    """{horizon: {scenario: {percentile: median across the models}}} for one run's rows of one question."""
    out = {}
    for h, s, p in S.asked(survey, question):
        v = _median([((r["forecasts"].get(h) or {}).get(s) or {}).get(p) for r in rows])
        if v is not None:
            out.setdefault(h, {}).setdefault(s, {})[p] = v
    return out


def _part1(survey, calls):
    out = {}
    for p in survey["part1"]:
        answers = {label: c["part1"][p["id"]] for label, c in calls if p["id"] in c["part1"]}
        if p["kind"] in ("probabilities", "allocation"):
            ens = {f: _median([a[f] for a in answers.values()]) for f in p["fields"]} if answers else None
            # The medians of shares need not sum to 100: rescaled so they do.
            if ens and sum(ens.values()):
                ens = {f: round(v * p["sum"] / sum(ens.values()), 2) for f, v in ens.items()}
        else:
            ens = _median(list(answers.values()))
        out[p["id"]] = {"title": p["title"], "kind": p["kind"], "ensemble": ens, "models": answers}
    return out


def build(survey=None, history=None, runs=None):
    survey = survey or S.load()
    history = history if history is not None else S.history()
    runs = runs if runs is not None else load_runs(instrument=S.instruments(survey))
    scenarios = [{"id": S.UNCONDITIONAL, "label": "Unconditional", "summary": None}] + [
        {"id": s["id"], "label": s["label"], "summary": s["indicators"][0]["text"]} for s in survey["scenarios"]["items"]]
    blob = {"instrument": survey["instrument"], "source": survey["source"], "scenarios": scenarios,
            "synthetic": any(r.get("synthetic") for _, rows in runs for r in rows),
            # The zip main() writes beside the page; the "Download data" button's link.
            "download": export.NAME if runs else None,
            "runs": [], "latest": None, "part1": None, "questions": []}
    per_run = []
    for run_id, rows in runs:
        calls = [(r["label"], r["call"]) for r in rows if r.get("call")]
        by_q = {}
        for r in rows:
            by_q.setdefault(r["question_id"], []).append(r)
        per_run.append((run_id, rows[0]["run_date"], by_q, calls))
        blob["runs"].append({"run_id": run_id, "date": rows[0]["run_date"],
                             "models": sorted({r["label"] for r in rows})})
    latest = per_run[-1] if per_run else None
    if latest:
        run_id, run_date, by_q, calls = latest
        panel = next((r.get("panel") for rows in by_q.values() for r in rows if r.get("panel")), None) or {}
        order = [m["label"] for m in panel.get("members") or []]
        labels = sorted({r["label"] for rows in by_q.values() for r in rows},
                        key=lambda x: (order.index(x) if x in order else len(order), x))
        blob["latest"] = {"run_id": run_id, "date": run_date, "models": labels,
                          "panel_snapshot": panel.get("snapshot"),
                          "grounded": all(c.get("grounded") for _, c in calls) if calls else None}
        blob["part1"] = _part1(survey, calls)
    for q in survey["questions"]:
        item = {k: q[k] for k in ("id", "title", "short", "category", "unit", "decimals", "uncertainty", "stem", "details")}
        item["preamble"] = q.get("preamble")
        series = history.get(q["history"], [])
        item["history"] = [[d, v] for d, v in series]
        item["ensemble"], item["models"], item["series"] = {}, [], []
        asked_on = {}
        for run_id, run_date, by_q, _ in per_run:
            ens = ensemble(survey, q, by_q.get(q["id"], []))
            if ens:
                # `models`: each model's own answers in that run, for the tooltips' breakdown.
                item["series"].append({"run_id": run_id, "date": run_date, "at": _asked_at(run_id, run_date),
                                       "ensemble": ens,
                                       "models": {r["label"]: r["forecasts"] for r in by_q.get(q["id"], [])}})
                # Each date keeps the forecast of the latest run that asked about it.
                item["ensemble"].update(ens)
                asked_on.update({h: run_date for h in ens})
        # `actual`: the record's value for the date, once there is one -- the
        # outcome its forecast (made on `asked`) is set against.
        item["horizons"] = []
        for h in q["horizons"]:
            got = S.actual(series, h["id"])
            item["horizons"].append({"id": h["id"], "text": h["text"], "added": bool(h.get("added")),
                                     "date": f"{h['id']}-01-01", "asked": asked_on.get(h["id"]),
                                     "actual": {"date": got[0], "value": got[1]} if got else None})
        if latest:
            rows = latest[2].get(q["id"], [])
            rank = {label: i for i, label in enumerate(blob["latest"]["models"])}
            item["models"] = [{"label": r["label"], "forecasts": r["forecasts"], "rationale": r["rationale"],
                               "problems": r.get("problems") or []}
                              for r in sorted(rows, key=lambda r: rank.get(r["label"], 99))]
        blob["questions"].append(item)
    return blob


def page(blob):
    """The page's text: eeai/web/'s chunks with the data spliced in."""
    from dashboard import page as kit
    return kit.render(config.PAGE_DIR, {"EEAI": blob})


def main(args):
    survey = S.load()
    runs = load_runs(args.runs, S.instruments(survey))
    blob = build(survey, runs=runs)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(blob), encoding="utf-8")
    else:
        # The whole site in one folder: the page as index.html, the download
        # (written below), and the files the page links to (the logo; the
        # licensed fonts when a box has them under eeai/web/fonts).
        from dashboard import site as kit
        out = kit.write_site(Path(args.site) if args.site else config.SITE, page(blob),
                             assets={f"web/{sub}": config.PAGE_DIR / sub for sub in ("img", "fonts")}) / "index.html"
    if runs:
        export.bundle(out.with_name(export.NAME), survey, runs, args.runs)
    if args.json:
        Path(args.json).write_text(json.dumps(blob, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out}: {len(runs)} run(s), {len(blob['questions'])} questions"
          + (f", latest {blob['latest']['date']} ({', '.join(blob['latest']['models'])})" if blob["latest"] else ", no runs yet")
          + (" -- SYNTHETIC DATA" if blob["synthetic"] else ""))
    return 0
