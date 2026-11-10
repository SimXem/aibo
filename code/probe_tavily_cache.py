#!/usr/bin/env python3
"""Opt-in live cache probe: concurrent tools, no model calls, <=4 HTTP attempts."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/fri-forecaster")]


def call_tool(task):
    module, tool, args, log = task
    tools = importlib.import_module(module)
    original = urllib.request.urlopen

    def counted(req, *args, **kwargs):
        # Cross-process accounting and a hard budget, even if upstream fails.
        with open(log, "a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            if len(stream.readlines()) >= 4:
                raise TimeoutError("probe HTTP budget exhausted")
            stream.write(req.full_url + "\n")
            stream.flush()
        return original(req, *args, **kwargs)

    with patch("urllib.request.urlopen", side_effect=counted):
        return getattr(tools, tool)(**args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="authorize paid Tavily calls")
    parser.add_argument("--env-file", type=Path, help="read only TAVILY_API_KEY from this file")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--url", default="https://en.wikipedia.org/wiki/Artificial_intelligence")
    parser.add_argument("--query", default="International AI Safety Report official report")
    args = parser.parse_args()
    if not args.live:
        parser.error("pass --live to authorize real Tavily requests")
    if not 2 <= args.workers <= 16:
        parser.error("--workers must be between 2 and 16")
    if args.env_file:
        from fri_forecaster.keys import parse_env
        key = parse_env(args.env_file).get("TAVILY_API_KEY")
        if key:
            os.environ["TAVILY_API_KEY"] = key
    if not os.environ.get("TAVILY_API_KEY"):
        parser.error("TAVILY_API_KEY is required")

    with tempfile.TemporaryDirectory(prefix="tavily-cache-probe-") as temp:
        log = str(Path(temp) / "http-attempts")
        os.environ.update(FORECASTER_TAVILY_CACHE_DIR=temp,
                          FORECASTER_TAVILY_CACHE_TTL="3600",
                          FORECASTER_BLOCK_URL_PATTERNS="")
        modules = ["redlines.tools", "fri_forecaster.tools"]
        batches = []
        failures = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            def batch(tool, arguments):
                tasks = [(modules[i % 2], tool, kw, log) for i, kw in enumerate(arguments)]
                results = list(pool.map(call_tool, tasks))
                # Cause is per caller, not part of the shared factual response.
                normalized = [{k: v for k, v in r.items() if k != "cause"} for r in results]
                same = all(r == normalized[0] for r in normalized)
                errors = [r.get("error") for r in results if r.get("error")]
                if errors or not same:
                    failures.append({"tool": tool, "errors": errors, "identical": same})
                batches.append({"tool": tool, "calls": len(results), "identical": same,
                                "successful": len(results) - len(errors),
                                "response_sha256": hashlib.sha256(json.dumps(
                                    normalized[0], sort_keys=True).encode()).hexdigest()})
                return results

            pages = batch("read_page", [{"url": args.url}] * args.workers)
            if not failures and pages[0].get("next_offset"):
                batch("read_page", [{"url": args.url, "offset": pages[0]["next_offset"]}]
                      * args.workers)
            else:
                failures.append({"pagination": "page failed or too short to test pagination"})
            if not failures:
                searches = batch("web_search", [dict(query=args.query, cause=f"group-{i}")
                                                for i in range(args.workers)])
                if any(r.get("cause") != f"group-{i}" for i, r in enumerate(searches)):
                    failures.append({"cause": "caller tags were not preserved"})
                if not searches[0].get("results"):
                    failures.append({"search": "no source results returned"})
        attempts = Counter(Path(log).read_text().splitlines()) if Path(log).exists() else Counter()
        expected = {"https://api.tavily.com/extract": 1, "https://api.tavily.com/search": 1}
        if dict(attempts) != expected:
            failures.append({"expected_http_attempts": expected})
        total = sum(b["calls"] for b in batches)
        report = {"passed": not failures, "tool_calls": total,
                  "http_attempts": dict(attempts),
                  "avoided_http_attempts": total - sum(attempts.values()),
                  "batches": batches, "failures": failures,
                  "model_calls": 0, "cache": "isolated temporary directory, removed after probe"}
        print(json.dumps(report, indent=2))
        return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
