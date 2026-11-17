#!/usr/bin/env python3
"""Cheap, manual tool-use probe; never a published forecast or ensemble run.

Uses one existing AI-incident question and its 12mo horizon, no conditional
scenarios, and the exact condition prompt. No new model-visible instructions.
Prints the prompt by default. --execute explicitly permits one model call,
up to eight turns, no retries. Outputs are private.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from redlines import experiments, news_shadow, recent_news

MODELS = {
    "haiku": ("Haiku 4.5", "anthropic/claude-haiku-4-5-20251001"),
    "sonnet": ("Sonnet 5.5", "anthropic/claude-sonnet-5-5"),
}


def probe_condition(name, snapshot=None):
    """Same prompt settings as each arm, but never pooled or published."""
    experiment = "airo" if name == "recent" else "recent-shadow-noairo"
    c = dict(experiments.load(experiment)["conditions"][name])
    c.update(publish=False, pooled=False, cadence="manual")
    if c.get("news_cache"):
        if not snapshot:
            raise ValueError("recent-shadow-noairo requires --snapshot")
        c["_news_snapshot"] = news_shadow.pin(snapshot, c["url_block_patterns"])
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", choices=["recent", "recent-shadow-noairo"], default="recent-shadow-noairo")
    ap.add_argument("--snapshot")
    ap.add_argument("--model", choices=MODELS, default="haiku")
    ap.add_argument("--date", type=date.fromisoformat, help="fixed prompt date for matched probes; searches remain live")
    ap.add_argument("--out", default=str(Path(recent_news.STATE_DIR) / "probe"))
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--timeout", type=int, default=180, help="wall-clock seconds per call (default: 180)")
    a = ap.parse_args()
    if a.timeout < 1:
        ap.error("--timeout must be positive")
    label, model_id = MODELS[a.model]
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    c = probe_condition(a.condition, a.snapshot)
    c["max_turns"] = 8  # Probe only; the scheduled condition has no forced-turn cap.
    c["sha256"] = experiments.condition_sha256(c)
    spec = importlib.util.spec_from_file_location("probe_runner", ROOT / "code/run_unified.py")
    ru = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ru)
    groups, batch, _, _, instrument = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
    groups = [next(g for g in groups if g["key"] == "ai")]
    batch = {"ai": [next(q for q in batch["ai"] if "12mo" in q["horizons"])]}
    policies = ru.load_policies(ru.COMBINED)
    # Drop capability elicitation along with the conditional scenarios. This is
    # a one-cell tool-use check, not a fresh capability forecast.
    policies["conditions"] = []
    policies.pop("elicits", None)
    policies.pop("elicit", None)
    today = a.date or datetime.now(timezone.utc).date()
    prompt, _, _ = ru.build_prompt_joint(groups, batch, ["12mo"], instrument, [], policies, today)
    prompt = ru.condition_prompt(prompt, c)
    (out / "prompt.txt").write_text(prompt)
    if not a.execute:
        print(prompt)
        return
    from fri_forecaster.keys import load_keys
    load_keys()
    if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("TAVILY_API_KEY"):
        raise SystemExit("probe requires ANTHROPIC_API_KEY and TAVILY_API_KEY")
    ru.MINIMAL_MAX_TURNS = 8
    # Only the arm's explicit per-call settings may reach its tools. In
    # particular Recent must not inherit a cache or URL guard from a shell.
    for key in (news_shadow.PATH_ENV, news_shadow.HASH_ENV, ru.BLOCK_ENV):
        os.environ.pop(key, None)
    # Fresh API-only agent folder; never borrow a coding-provider login.
    with tempfile.TemporaryDirectory(prefix="news-probe-agent-") as agent:
        os.environ["PI_CODING_AGENT_DIR"] = agent
        os.environ["REDLINES_PI_DIR"] = str(out / "trace")
        os.environ["REDLINES_PI_TIMEOUT"] = str(a.timeout)
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        rows = ru.run_one_joint(label, model_id, groups, batch,
                               ["12mo"], run_id, 0, instrument, [], policies, c,
                               "recent-shadow-noairo-probe", today=today)
    for row in rows:
        row["news_probe"] = True
    (out / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    evidence = [e for r in rows for e in r.get("evidence", [])]
    reads = [e for e in evidence if e["tool"] == "read_page" and e["args"].get("url") == news_shadow.URL]
    summary = {"model": label, "condition": a.condition, "timeout_seconds": a.timeout,
               "news_reads": len(reads),
               "successful_news_reads": sum(not e["result"].get("error") for e in reads),
               "tools": [e["tool"] for e in evidence], "usage": rows[0].get("usage") if rows else None,
               "snapshot": {k: v for k, v in c.get("_news_snapshot", {}).items() if k != "path"}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
