#!/usr/bin/env python3
"""Print a run's research trail: what each model searched, read and cited.

The evidence a forecast rests on is on its rows already -- `evidence[]` holds
every tool call of the elicitation, in order, with the arguments and the
result (redlines/llm.py::call_tools captures them; run_unified.py writes them
on the first row of each call). This prints it as a transcript a reader can
follow: query -> the titles and URLs that came back, page -> how much of it
was read, then the rationale and the key sources the model said it relied on.

    python3 code/show_trail.py                          # the newest file in results/runs/
    python3 code/show_trail.py results/runs/2026-08-28T1200Z.jsonl
    python3 code/show_trail.py --grep "hugging face"    # mark where a term shows up
    python3 code/show_trail.py --models "Fable 5" --arm joint#1

--grep marks each query, result, page and rationale that mentions the term,
and ends with a count per call: whether the model asked about it, whether a
search returned it, whether it made the rationale. That is the difference
between a model that saw a thing and a model that used it.
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from redlines.logs import iter_rows  # noqa: E402

RUNS_DIR = os.path.join(ROOT, "results", "runs")


def load(path):
    return list(iter_rows(path))


def calls(rows):
    """{call_id: first row with evidence + the rows of that call}."""
    out = OrderedDict()
    for r in rows:
        cid = r.get("call_id") or f"{r['run_id']}:{r.get('arm')}:{r['label']}"
        c = out.setdefault(cid, {"head": None, "rows": []})
        c["rows"].append(r)
        if r.get("evidence") and c["head"] is None:
            c["head"] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="a run file (default: the newest under results/runs/)")
    ap.add_argument("--grep", help="a term to mark wherever it appears (case-insensitive)")
    ap.add_argument("--models", help="comma-separated label filter")
    ap.add_argument("--arm", help="only this arm (e.g. joint#1)")
    ap.add_argument("--results", type=int, default=5, help="result titles to show per search (default 5)")
    ap.add_argument("--no-rationale", action="store_true")
    ap.add_argument("--recall", metavar="FILE",
                    help="a held-out incident list (data/recent_incidents_*.json): per call, "
                         "which incidents a query asked about, a result returned, a page "
                         "read carried, or the rationale used -- never shown to the model")
    args = ap.parse_args()
    recall = json.load(open(args.recall))["incidents"] if args.recall else None
    path = args.path or max(glob.glob(os.path.join(RUNS_DIR, "*.jsonl")), default=None)
    if not path:
        sys.exit("no run file")
    pat = re.compile(re.escape(args.grep), re.I) if args.grep else None
    mark = lambda s: (" <==" if pat and pat.search(s or "") else "")
    want = {m.strip().lower() for m in args.models.split(",")} if args.models else None
    rows = load(path)
    print(f"# {os.path.relpath(path, ROOT)}: {len(rows)} rows")
    for cid, c in calls(rows).items():
        head = c["head"] or c["rows"][0]
        if want and head["label"].lower() not in want:
            continue
        if args.arm and head.get("arm") != args.arm:
            continue
        ev = head.get("evidence") or []
        n_s = sum(1 for e in ev if e["tool"] == "web_search")
        n_r = sum(1 for e in ev if e["tool"] == "read_page")
        hit = {"asked": 0, "returned": 0, "read": 0, "rationale": 0}
        print(f"\n## {head['label']}  {head.get('arm') or ''}  run {head['run_id']}  "
              f"protocol {head.get('protocol')}  attempts {head.get('attempts')}  "
              f"{n_s} searches, {n_r} page reads, grounded={head.get('grounded')}")
        for i, e in enumerate(ev, 1):
            a, res = e.get("args") or {}, e.get("result") or {}
            if e["tool"] == "web_search":
                q = a.get("query", "")
                if pat and pat.search(q):
                    hit["asked"] += 1
                hits = res.get("results") or []
                err = res.get("error")
                print(f"  {i:2}. search {q!r} -> {len(hits)} results" + (f"  ERROR {err}" if err else "") + mark(q))
                for r in hits[: args.results]:
                    blob = f"{r.get('title')} {r.get('url')} {r.get('content')}"
                    if pat and pat.search(blob):
                        hit["returned"] += 1
                    print(f"        - {r.get('title')!s:70.70}  {r.get('url')}{mark(blob)}")
            elif e["tool"] == "read_page":
                url, total = a.get("url"), res.get("total_chars")
                err = res.get("error")
                body = res.get("text") or ""
                if pat and pat.search(body):
                    hit["read"] += 1
                print(f"  {i:2}. read   {url}  offset {a.get('offset', 0)}  "
                      + (f"{len(body)}/{total} chars" if not err else f"ERROR {err}") + mark(body))
            else:
                print(f"  {i:2}. {e['tool']} {json.dumps(a)[:100]}")
        if not args.no_rationale:
            rat = head.get("rationale") or ""
            srcs = head.get("key_sources") or []
            if pat and pat.search(rat + json.dumps(srcs)):
                hit["rationale"] += 1
            print(f"  rationale: {rat.strip()[:1200]}{mark(rat)}")
            for s in srcs[:12]:
                print(f"  source: {json.dumps(s)[:160]}{mark(json.dumps(s))}")
        if pat:
            print(f"  [{args.grep!r}] asked={hit['asked']} returned={hit['returned']} "
                  f"read={hit['read']} in_rationale={hit['rationale']}")
        if recall:
            found = 0
            for inc in recall:
                kp = re.compile("|".join(re.escape(k) for k in inc["keywords"]), re.I)
                where = []
                for e in ev:
                    a, res = e.get("args") or {}, e.get("result") or {}
                    if e["tool"] == "web_search":
                        if kp.search(a.get("query", "")): where.append("asked")
                        if kp.search(json.dumps(res.get("results") or [])): where.append("returned")
                    elif e["tool"] == "read_page" and kp.search(res.get("text") or ""):
                        where.append("read")
                if kp.search((head.get("rationale") or "") + json.dumps(head.get("key_sources") or [])):
                    where.append("rationale")
                found += bool(where)
                print(f"  recall  {inc['name']:52.52} {'+'.join(sorted(set(where))) or '-'}")
            print(f"  recall  {found}/{len(recall)} incidents surfaced anywhere in this call")


if __name__ == "__main__":
    main()
