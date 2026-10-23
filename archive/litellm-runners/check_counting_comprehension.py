#!/usr/bin/env python3
"""Independent comprehension diagnostic; never writes canonical forecasts."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from redlines.instrument import CURRENT_INSTRUMENT
from redlines.llm import call_tools, load_keys
from redlines.questions import load_ladder
from redlines.registry import DEFAULT_MODEL_SET, MODEL_SETS


CASES = [
    ("ai_upgrade", "A fraud campaign began August 1, 2026. The same operation adds powerful AI on September 12, greatly increasing harm.", False),
    ("new_operation", "An established group launches a distinct hospital ransomware operation whose first malicious action against a target is September 12, 2026. It is operationally separate from its earlier campaigns.", True),
    ("delayed_encryption", "The campaign's first intrusion was August 1, 2026. Encryption occurs September 12 in the same campaign.", False),
    ("new_report", "A September 12, 2026 report first reveals a campaign that began in August.", False),
    ("worm_spread", "A worm campaign began September 9, 2026. It reaches additional victims September 12 through continued propagation of the same campaign.", False),
    ("development_only", "Code was developed in August, but a distinct campaign's first malicious action against a target is September 12, 2026. Planning and development did not themselves act against targets.", True),
    ("post_deadline_harm", "A qualifying campaign's onset is December 30, 2030. Its first losses occur in January 2031, within its first three years. Assess inclusion in the by-2030 onset forecast.", True),
    ("later_elicitation", "For this case only, elicitation is January 10, 2027. The campaign began September 12, 2026 and is still ongoing. Assess inclusion in this new elicitation's by-2030 forecast.", False),
]


def diagnostic_prompt():
    spec = load_ladder()
    cyber = next(q for q in spec["questions"] if q["cause"] == "cyber")
    return (
        "This is a comprehension test of stipulated AIRO counting rules, not a risk forecast. "
        "Do not estimate probabilities or search for real events. All examples stipulate "
        "the existing AI-involvement and other non-date eligibility criteria are met. "
        "Classify only campaign identity, onset eligibility and the harm window. "
        "Unless a case explicitly says otherwise, elicitation is September 10, 2026, "
        "and the target is incident onsets through December 31, 2030. "
        "Return every case exactly once. Explain each classification briefly.\n\n"
        f"Cyber definition:\n{cyber['criteria']}\n\n"
        f"Shared incident dates:\n{cyber['details']['dates']}\n\n"
        "Cases:\n" + json.dumps([{"id": k, "facts": facts} for k, facts, _ in CASES], indent=2)
    )


FINAL_TOOL = {
    "name": "submit_classifications",
    "description": "Return the eligibility classification for every stipulated case.",
    "parameters": {
        "type": "object", "properties": {"cases": {
            "type": "array", "items": {
                "type": "object", "properties": {
                    "id": {"type": "string"}, "eligible": {"type": "boolean"},
                    "reason": {"type": "string"}},
                "required": ["id", "eligible", "reason"]}}},
        "required": ["cases"]},
}


def classify(label, model, prompt):
    usage = {}
    answer, _ = call_tools(model, prompt, [], FINAL_TOOL, max_iters=2,
                          max_tokens=8000, usage=usage,
                          system="Apply only the supplied counting rules to the stipulated facts.")
    cases = answer.get("cases") or []
    got = {c.get("id"): c for c in cases if isinstance(c, dict)}
    expected = {k: eligible for k, _, eligible in CASES}
    passed = len(cases) == len(expected) and set(got) == set(expected)
    checks = []
    for k, eligible in expected.items():
        actual = got.get(k, {}).get("eligible")
        ok = isinstance(actual, bool) and actual == eligible
        checks.append({"id": k, "expected": eligible, "actual": actual, "passed": ok})
        passed = passed and ok
    return {"label": label, "model": model, "passed": passed,
            "checks": checks, "answer": answer, "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    prompt = diagnostic_prompt()
    if args.dry_run:
        print(prompt)
        return 0
    load_keys()
    models = MODEL_SETS[DEFAULT_MODEL_SET]()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "prompt.txt").write_text(prompt)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(classify, label, model, prompt): label for label, model in models}
        for future in concurrent.futures.as_completed(pending):
            label = pending[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"label": label, "passed": False, "error_type": type(exc).__name__}
            results.append(result)
            (args.out / f"model-{len(results)}.json").write_text(json.dumps(result, indent=2) + "\n")
            print(f"{label}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    report = {"instrument_version": CURRENT_INSTRUMENT,
              "completed_at": datetime.now(timezone.utc).isoformat(),
              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
              "passed": len(results) == len(models) and all(r["passed"] for r in results),
              "models": results}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
