#!/usr/bin/env python3
"""Generate the severity-ladder question set — the SAME question per cause class,
asked at every rung of a log-spaced death ladder.

Why this exists: XPT gives excellent human baselines but was never designed as a
severity ladder — it has AI only at ">10% of humans" and extinction, bioweapons
only at 1k/100k, and so on. Plotting those yields lines that each cover a sliver
of the severity axis and cannot be compared across causes. The FRI economist's
point on 2026-08-03 is the fix: LLM forecasts scale, so ask every point on the
spectrum and let the (expensive) human round sample from it later.

Thresholds are absolute death counts so causes are directly comparable at the
same severity. Cyber is deliberately absent: per the paper's lead author, cyber
belongs on a damages ladder, not a deaths ladder (a separate question set).

    python3 code/make_ladder_questions.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "severity_ladder_questions.json"

HORIZONS = ["2030", "2050", "2100"]

RUNGS = [
    (1e3,  "at least 1,000",       "≥1k"),
    (1e5,  "at least 100,000",     "≥100k"),
    (1e6,  "at least 1 million",   "≥1M"),
    (1e7,  "at least 10 million",  "≥10M"),
    (1e8,  "at least 100 million", "≥100M"),
    (1e9,  "at least 1 billion",   "≥1B"),
]
EXTINCTION = (8.2e9, "human extinction", "extinction")

CAUSES = [
    {"key": "ai", "label": "AI-enabled", "color": "#33a8bd",
     "clause": "an event materially caused or enabled by artificial intelligence "
               "(including AI-enabled bio, cyber, or infrastructure attacks, AI-driven "
               "conflict escalation, and loss of control over AI systems)",
     "xpt_anchor": {"3. AI Catastrophic Risk": 8.2e8, "4. AI Extinction Risk": 8.2e9}},
    {"key": "bio", "label": "Engineered / deliberate bio", "color": "#a63d76",
     "clause": "the deliberate release of a biological agent, or the release of a "
               "genetically engineered pathogen (whether deliberate or accidental)",
     "xpt_anchor": {"18. State Actor Bioweapon 100k Deaths": 1e5,
                    "1. Genetically Engineered Pathogen Risk": 8.2e7}},
    {"key": "nuclear", "label": "Nuclear", "color": "#a1801a",
     "clause": "the use of one or more nuclear weapons",
     "xpt_anchor": {"31. Nuclear Weapon Use": 1e3, "5. Nuclear Catastrophic Risk": 8.2e8,
                    "6. Nuclear Extinction Risk": 8.2e9}},
    {"key": "total", "label": "All causes", "color": "#3a4150",
     "clause": "any single global catastrophe, of any cause (natural or anthropogenic)",
     "xpt_anchor": {"9. Total Catastrophic Risk": 8.2e8, "10. Total Extinction Risk": 8.2e9}},
]

TEMPLATE = (
    "What is the probability that {clause} will be the cause of death for "
    "{count} people worldwide, within any 5-year period, by the end of "
    "2030 / 2050 / 2100?\n\n"
    "Deaths are counted as excess mortality directly attributable to the event or "
    "its immediate consequences, per credible reporting from governmental or "
    "international bodies (e.g. WHO, national governments, UN agencies). "
    "Indirect long-run deaths (economic knock-on effects, unrelated later conflict) "
    "do not count. The threshold is cumulative across a single causal event or "
    "closely linked chain of events, not summed over unrelated incidents."
)

EXT_TEMPLATE = (
    "What is the probability that {clause} will cause human extinction, or reduce "
    "the global human population below 5,000, by the end of 2030 / 2050 / 2100?"
)


def build():
    qs = []
    for c in CAUSES:
        for deaths, count, short in RUNGS:
            qs.append({
                "id": f"ladder:{c['key']}:{short}",
                "cause": c["key"], "cause_label": c["label"], "color": c["color"],
                "deaths": deaths, "rung": short,
                "category": "ladder", "value_kind": "probability",
                "horizons": HORIZONS,
                "text": TEMPLATE.format(clause=c["clause"], count=count),
            })
        qs.append({
            "id": f"ladder:{c['key']}:extinction",
            "cause": c["key"], "cause_label": c["label"], "color": c["color"],
            "deaths": EXTINCTION[0], "rung": EXTINCTION[2],
            "category": "ladder", "value_kind": "probability",
            "horizons": HORIZONS,
            "text": EXT_TEMPLATE.format(clause=c["clause"]),
        })
    return {
        "title": "Severity-ladder question set — same cause, every rung",
        "provenance": {
            "authored": "this project (2026-08-05), not XPT",
            "rationale": "XPT has no complete severity ladder for any cause; these are "
                         "written so every cause spans the full death axis and causes are "
                         "comparable at equal severity. XPT questions remain as human-"
                         "baseline anchor points (see `xpt_anchor` per cause in "
                         "code/make_ladder_questions.py).",
            "supersede": "Ezra's 30-page catastrophic-risk questions document, once final, "
                         "should replace these definitions.",
        },
        "notes": {
            "cyber": "absent by design — per Jason (2026-08-03) cyber belongs on a DAMAGES "
                     "ladder, not a deaths ladder; needs its own question set.",
            "coherence": "within a cause, P must be non-increasing as the threshold rises; "
                         "every adjacent pair is a checkable constraint with no resolution.",
        },
        "causes": [{k: c[k] for k in ("key", "label", "color", "xpt_anchor")} for c in CAUSES],
        "rungs": [{"deaths": d, "rung": s} for d, _, s in RUNGS] +
                 [{"deaths": EXTINCTION[0], "rung": EXTINCTION[2]}],
        "questions": qs,
    }


if __name__ == "__main__":
    blob = build()
    OUT.write_text(json.dumps(blob, indent=2) + "\n")
    print(f"{len(blob['questions'])} questions "
          f"({len(blob['causes'])} causes x {len(blob['rungs'])} rungs) -> {OUT.name}")
