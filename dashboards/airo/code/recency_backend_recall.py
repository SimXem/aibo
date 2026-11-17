#!/usr/bin/env python3
"""Which news backend surfaces last quarter's AI incidents, given only generic
queries? No model in the loop.

The queries are derived from the question set's cause labels (data/
autoarc_ladder.json) plus three generic phrasings -- nothing names an event.
Each backend gets the identical queries over the same window, and the union
of what comes back is scored against the held-out incident list
(data/recent_incidents_2026-09.json), which no model ever sees.

    python3 code/recency_backend_recall.py --days 90 --n 10

Backends: Tavily's news index (exact dates), Tavily's general index (the
coarse time_range bucket that covers the window), and AskNews (natural-
language search over its licensed news index, bounded by timestamps), in two
strategies. Keys from the environment: TAVILY_API_KEY, ASKNEWS_API_KEY.
Writes results/experiments/recency_backends/<date>.json.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from redlines.tools import TAVILY_URL, search_body  # noqa: E402

ASKNEWS_URL = "https://api.asknews.app/v1/news/search"


def queries():
    ladder = json.load(open(os.path.join(ROOT, "data", "autoarc_ladder.json")))
    qs = [c["label"] for c in ladder["causes"]]
    return qs + ["AI incident", "artificial intelligence system caused harm",
                 "AI safety incident report"]


def tavily(query, n, start, end, mode):
    key = os.environ["TAVILY_API_KEY"]
    if mode == "news":
        body = search_body(query, n, recent_days=(end - start).days, today=end)
    else:
        days = (end - start).days
        bucket = "day" if days <= 1 else "week" if days <= 7 else "month" if days <= 31 else "year"
        body = dict(search_body(query, n), time_range=bucket)
    req = urllib.request.Request(TAVILY_URL, data=json.dumps(dict(body, api_key=key)).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    return [{"title": x.get("title"), "url": x.get("url"), "text": x.get("content") or "",
             "published": x.get("published_date"), "domain": urllib.parse.urlparse(x.get("url") or "").netloc}
            for x in d.get("results", [])]


def asknews(query, n, start, end, strategy, diversify):
    key = os.environ["ASKNEWS_API_KEY"]
    params = {"query": query, "n_articles": n, "return_type": "dicts", "method": "nl",
              "historical": "true", "strategy": strategy,
              "start_timestamp": int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
              "end_timestamp": int(datetime(end.year, end.month, end.day, 23, 59, tzinfo=timezone.utc).timestamp()),
              "diversify_sources": "true" if diversify else "false"}
    req = urllib.request.Request(ASKNEWS_URL + "?" + urllib.parse.urlencode(params),
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    return [{"title": x.get("eng_title"), "url": x.get("article_url"), "text": x.get("summary") or "",
             "published": x.get("pub_date"), "domain": x.get("domain_url"), "page_rank": x.get("page_rank"),
             "source": x.get("source_id")}
            for x in d.get("as_dicts", [])]


BACKENDS = {
    "tavily_news":        lambda q, n, s, e: tavily(q, n, s, e, "news"),
    "tavily_general":     lambda q, n, s, e: tavily(q, n, s, e, "general"),
    "asknews_knowledge":  lambda q, n, s, e: asknews(q, n, s, e, "news knowledge", False),
    "asknews_diverse":    lambda q, n, s, e: asknews(q, n, s, e, "news knowledge", True),
    "asknews_latest":     lambda q, n, s, e: asknews(q, n, s, e, "latest news", False),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--backends", default=",".join(BACKENDS))
    ap.add_argument("--incidents", default=os.path.join(ROOT, "data", "recent_incidents_2026-09.json"))
    args = ap.parse_args()
    end = date.today()
    start = end - timedelta(days=args.days)
    incidents = json.load(open(args.incidents))["incidents"]
    qs = queries()
    print(f"window {start} .. {end}, {len(qs)} queries x n={args.n}: {qs}")
    out = {"window": [start.isoformat(), end.isoformat()], "n": args.n, "queries": qs, "backends": {}}
    for name in args.backends.split(","):
        fn = BACKENDS[name]
        results, errors, t0 = [], [], time.time()
        for q in qs:
            try:
                got = fn(q, args.n, start, end)
                for g in got:
                    g["query"] = q
                results += got
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError) as e:
                body = e.read()[:200].decode(errors="replace") if hasattr(e, "read") else ""
                errors.append(f"{q!r}: {type(e).__name__} {e} {body}")
        seen = {}
        for r in results:
            seen.setdefault(r["url"], r)
        uniq = list(seen.values())
        hits = {}
        for inc in incidents:
            kp = re.compile("|".join(re.escape(k) for k in inc["keywords"]), re.I)
            hits[inc["name"]] = sorted({r["query"] for r in uniq if kp.search(f"{r['title']} {r['text']} {r['url']}")})
        found = sum(1 for v in hits.values() if v)
        domains = {}
        for r in uniq:
            domains[r["domain"]] = domains.get(r["domain"], 0) + 1
        top = sorted(domains.items(), key=lambda kv: -kv[1])[:8]
        ranks = sorted(r["page_rank"] for r in uniq if r.get("page_rank"))
        print(f"\n== {name}: {len(results)} results, {len(uniq)} unique urls, {len(errors)} errors, "
              f"{time.time() - t0:.0f}s -> {found}/{len(incidents)} incidents surfaced")
        for inc in incidents:
            v = hits[inc["name"]]
            print(f"   {inc['name']:52.52} {('via ' + '; '.join(v)) if v else '-'}")
        print(f"   top domains: " + ", ".join(f"{d} x{c}" for d, c in top))
        if ranks:
            print(f"   page_rank of returned sources: median {ranks[len(ranks)//2]}, best {ranks[0]}, worst {ranks[-1]}")
        for e in errors[:3]:
            print(f"   ERROR {e}")
        out["backends"][name] = {"results": len(results), "unique": len(uniq), "found": found, "hits": hits,
                                 "domains": domains, "errors": errors,
                                 "sample": [{k: r.get(k) for k in ("title", "url", "published", "query", "page_rank")}
                                            for r in uniq[:60]]}
    d = os.path.join(ROOT, "results", "experiments", "recency_backends")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{end.isoformat()}.json")
    json.dump(out, open(p, "w"), indent=1)
    print(f"\n-> {os.path.relpath(p, ROOT)}")


if __name__ == "__main__":
    main()
