#!/usr/bin/env python3
"""Generate data/eci_conditions.json: the capability scenarios for the
single instrument -- three end-of-2027 frontier-ECI levels.

The policy scenarios (data/leap_policies.json) ask what a named policy does
to the forecast. These ask what a named LEVEL OF AI CAPABILITY does: each
question, given that the US frontier's Epoch Capabilities Index reaches a
stated score by December 31, 2027. The three scores are the 10th, 50th and
90th percentiles of the metr_graph ECI-tab projection recorded in
data/eci_projection_2026-08-21.json (see docs/conditional-forecasts.md,
"ECI projection for the capability-conditional"): a slow, a trend and a fast
world. The runner reads this file through --scenarios and treats it exactly
as it treats the policy file -- same instrument, same tool, same analysis --
so the two scenario sets are one protocol with different scenario text.

    python3 code/make_eci_conditions.py           # writes data/eci_conditions.json
    python3 code/make_eci_conditions.py --check    # verify the file is current

WHAT IS DERIVED AND WHAT IS AUTHORED

  derived    the three levels (percentiles of the projection table), the
             reference ladder of scores the model is shown (looked up in the
             vendored Epoch CSV, best variant per model), the step from the
             current frontier to each level.
  authored   the conditioning instruction, the definitions paragraph, the
             unconditional line, the ids and labels. There is no human panel
             wording to carry here, so the words are ours, and they are kept
             to the same discipline as the policy set: they say nothing about
             how capability relates to any question, and nothing about
             direction. The prompt states the level, not its percentile --
             the model is given the reference ladder and can judge the pace
             itself; the provenance lives in this file's metadata.

TWO CHOICES TO KNOW ABOUT

  "Approximately X", not "at least X". Conditioning on "at least the 10th
  percentile" is nearly the unconditional; a point scenario partitions the
  projection into three worlds, and three point conditionals are what a
  later mixture over the projection would need.

  A fact, not an intervention. LEAP's policy clause says hold other factors
  constant and treat the policy as exogenous. A capability level is not an
  intervention anyone applies to the world -- it does not arrive without the
  investment, compute and progress that produce it -- so the instruction
  says the opposite: treat the level as something learned about the world
  and update everything that would accompany it. P(question | ECI = X), not
  P(question | do(ECI = X)).
"""
import argparse
import csv
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECTION = os.path.join(ROOT, "data", "eci_projection_2026-08-21.json")
CSV = os.path.join(ROOT, "data", "epoch_capabilities_index_2026-08-21.csv")
OUT = os.path.join(ROOT, "data", "eci_conditions.json")

TARGET = "2027EOY"
TARGET_DATE_TEXT = "December 31, 2027"
LEVELS = [("p10", 10), ("p50", 50), ("p90", 90)]

# The ladder the model is shown, by Epoch display name: a handful of
# well-known US releases spanning the scale, oldest first. Scores come from
# the CSV, never typed here.
REFERENCE = [
    "GPT-4 (Mar 2023)",
    "Claude 3.5 Sonnet (Jun 2024)",
    "o1 (medium)",
    "o3 (medium)",
    "GPT-5 (high)",
    "Gemini 3 Pro Preview",
    "GPT-5.4 Pro (xhigh)",
    "GPT-5.5 Pro (xhigh)",
    "Claude Fable 5 (high)",
]
# How each is named in the prompt (the Epoch display name carries reasoning
# settings a reader does not need).
SHORT = {
    "GPT-4 (Mar 2023)": "GPT-4",
    "Claude 3.5 Sonnet (Jun 2024)": "Claude 3.5 Sonnet",
    "o1 (medium)": "o1",
    "o3 (medium)": "o3",
    "GPT-5 (high)": "GPT-5",
    "Gemini 3 Pro Preview": "Gemini 3 Pro",
    "GPT-5.4 Pro (xhigh)": "GPT-5.4 Pro",
    "GPT-5.5 Pro (xhigh)": "GPT-5.5 Pro",
    "Claude Fable 5 (high)": "Claude Fable 5",
}

INSTRUCTION = (
    "For each condition below, assume that the stated level of AI capability "
    "is reached by {date}. Treat it as a fact you have learned about the "
    "world, not as an intervention: update your expectations about "
    "everything that would ordinarily accompany that level of capability -- "
    "investment, compute, algorithmic progress, deployment, and how "
    "governments and developers respond -- as you would upon learning it, "
    "and then forecast each question in that world. Do not hold other "
    "factors fixed where the stated level would change them."
)

UNCONDITIONAL = ("forecast the world as you expect it to unfold, including "
                 "whatever level of AI capability you expect to be reached by {date}.")

DEFINITIONS = (
    "Definitions. ECI: the Epoch Capabilities Index, published by Epoch AI -- a "
    "single score summarising a model's results across dozens of benchmarks, "
    "fit with an item-response model so that scores stay comparable as "
    "benchmarks saturate and new ones are added. Higher is more capable; the "
    "scale has no ceiling. All scores here are on the scale as published by "
    "Epoch on {csv_date}.\n"
    "Frontier ECI: the highest ECI score of any publicly released model from a "
    "US developer, as scored by Epoch.\n"
    "Reference scores (best variant of each model): {ladder}. The highest "
    "score of any released model as of {csv_date} is {top_name}, {top_score}."
)

ASSUME = ("Assume that on {date} the frontier ECI is approximately {level} "
          "(within about two points of it).")

DESCRIPTION = ("That is about {step} points above the highest score as of "
               "{csv_date} ({top_name}, {top_score}).")


def _month(d):
    from datetime import datetime
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b %Y")


def load_ladder():
    """{display name: (score, release date)} -- the best variant per display name."""
    best = {}
    with open(CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                s = float(r["ECI Score"])
            except (TypeError, ValueError):
                continue
            dn = r["Display name"]
            if dn and s > best.get(dn, (-1e9, None))[0]:
                best[dn] = (s, r["Release date"])
    return best


def build():
    proj = json.load(open(PROJECTION, encoding="utf-8"))
    csv_date = proj["source"]["csv_refreshed"]
    row = proj["projection"][TARGET]
    ladder = load_ladder()
    missing = [n for n in REFERENCE if n not in ladder]
    if missing:
        sys.exit(f"reference models not in {CSV}: {missing}")
    ref = [(SHORT[n], round(ladder[n][0]), ladder[n][1]) for n in REFERENCE]
    ladder_text = "; ".join(f"{name} ({_month(d)}) {s}" for name, s, d in ref)
    top = proj["fit"]["anchor"]
    top_name, top_score = SHORT.get(top["model"], top["model"]), round(top["score"])
    scenarios = []
    for key, pct in LEVELS:
        level = round(row[key])
        scenarios.append({
            "id": f"eci{level}",
            "leap_id": None,
            "label": f"Frontier ECI {level} at end of 2027",
            "policy": None,
            "part": None,
            "assume": ASSUME.format(date=TARGET_DATE_TEXT, level=level),
            "description": DESCRIPTION.format(step=level - top_score, csv_date=csv_date,
                                              top_name=top_name, top_score=top_score),
            # Provenance, not shown to the model.
            "projection": {"percentile": pct, "value": row[key], "target": TARGET,
                           "date": row["date"], "source": os.path.relpath(PROJECTION, ROOT)},
        })
    return {
        "title": "Frontier-ECI capability conditions (end of 2027), as the runner prepends them",
        "slug": "eci",
        "kind": "capability",
        "protocol": "unified-joint-eci-v1",
        "source": {
            "panel": None,
            "wave": "Frontier ECI at end of 2027 (metr_graph projection, CSV of 2026-08-21)",
            "status": "no human panel answers these conditions; the levels are the p10/p50/p90 "
                      "of the metr_graph ECI-tab projection at its defaults",
            "documents": [os.path.relpath(PROJECTION, ROOT), os.path.relpath(CSV, ROOT)],
            "outcome_horizons": [],
            "policy_probability_horizons": [],
        },
        "generated_by": os.path.relpath(__file__, ROOT),
        "conditioning": {
            "instruction": INSTRUCTION.format(date=TARGET_DATE_TEXT),
            "unconditional_forecast": UNCONDITIONAL.format(date=TARGET_DATE_TEXT),
            "definitions": DEFINITIONS.format(csv_date=csv_date, ladder=ladder_text,
                                              top_name=top_name, top_score=top_score),
            "horizon": f"every condition is a level reached by {TARGET_DATE_TEXT}.",
        },
        "reference": [{"model": n, "score": s, "release_date": d} for n, s, d in ref],
        "conditions": scenarios,
        "notes": {
            "levels": "p10 / p50 / p90 of the projection's 2027EOY row, rounded to the "
                      "point; the condition is a point ('approximately X'), not a bound.",
            "conditioning": "a fact learned about the world, not an exogenous intervention: "
                            "the instruction is the opposite of LEAP's policy clause on purpose.",
            "percentiles": "not shown to the model; it is given the reference ladder and "
                           "judges the pace itself.",
            "horizon": "the level is dated 2027-12-31; every horizon in the batch is "
                       "elicited under it, and the pilot reports 2030.",
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    doc = build()
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if args.check:
        cur = open(args.out, encoding="utf-8").read() if os.path.exists(args.out) else ""
        if cur != text:
            sys.exit(f"{args.out} is stale — rerun {os.path.relpath(__file__, ROOT)}")
        print("ok")
        return
    open(args.out, "w", encoding="utf-8").write(text)
    for c in doc["conditions"]:
        h = hashlib.sha256(c["assume"].encode()).hexdigest()[:8]
        print(f"  {c['id']:7} p{c['projection']['percentile']:<3} {c['projection']['value']:6.1f}  {h}  {c['label']}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
