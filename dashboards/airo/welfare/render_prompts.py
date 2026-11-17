"""Render the welfare instrument's five prompts and its two tools, as the AIRO
minimal instrument (combined-v11) would ask them on 2026-10-21.

    python3 welfare/render_prompts.py

Writes welfare/prompts/welfare-<condition>.txt (one per prompt variant) and
welfare/prompts/tools.json. These are REFERENCE renders: the live runner should
build the same text from data/combined_conditions.json and the day's ECI
snapshot (code/run_unified.py scenarios_block_grouped), not read these files.

The CONDITIONS block is copied verbatim from the prompt AIRO actually sent on
2026-10-21 (reference/airo-v11-minimal-prompt-skeleton-2026-10-21.txt, from
the published redlines-data.zip), with one edit: Step 2 asks for five
percentiles per condition instead of one probability. Everything else outside
the questions and the delivery paragraph follows the minimal joint prompt's
wording. Stdlib only.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TODAY = "2026-10-21"
SKELETON = HERE / "reference" / "airo-v11-minimal-prompt-skeleton-2026-10-21.txt"
PCTS = ("p10", "p25", "p50", "p75", "p90")

HEAD = """Today is {today}.

Below are {n} questions. Answer
all of them -- and answer every question x horizon cell
under each of the {k} conditions listed in the CONDITIONS section that follows
the questions: once unconditionally, and once under each condition in each of
its 2 groups (policy conditions and capability conditions). Every condition is taken on its own; no
condition from one group is combined with a condition from another.
"""

GROUP = """
===== {heading} =====
"""

QUESTION = """
--- {id} ---
{text}
Horizons for this question: {horizons}
{unit_text}

Resolution criteria:
{criteria}
"""

STEP2_AIRO = "Step 2 -- each question x horizon cell takes {k} probabilities, keyed by the condition ids below:"
STEP2_WELFARE = ("Step 2 -- each question x horizon cell takes five percentiles (p10, p25, p50, p75, p90) "
                 "under each of {k} conditions, keyed by the condition ids below:")

HORIZONS = """
Horizons: {horizons}. Each question names the ones it is asked over and what each
means for it -- answer those and no others.
"""

DELIVERY = """Deliver the percentiles with submit_cells, in as many calls as you like: any
subset of the {cells} question x horizon cells per call, each cell with five
percentiles (p10, p25, p50, p75, p90, in the question's unit, with
p10 <= p25 <= p50 <= p75 <= p90 -- read them as in eci_forecast) under each of
the {k} conditions ({total} numbers, keyed by condition id); a later call for a
cell replaces the earlier one. Then call submit_forecast ONCE,
with your eci_forecast (5 numbers) and a short rationale, the sources you used, and any cells not yet delivered."""


def conditions_block(skeleton, k):
    start = skeleton.index("===== CONDITIONS =====")
    end = skeleton.index("\n=====\n\nHorizons:", start) + len("\n=====\n")
    block = skeleton[start:end]
    old = STEP2_AIRO.format(k=k)
    assert block.count(old) == 1, "the v11 Step 2 sentence changed; update STEP2_AIRO"
    return block.replace(old, STEP2_WELFARE.format(k=k))


def condition_ids(block):
    return [line[4:-4] for line in block.splitlines() if line.startswith("--- ") and line.endswith(" ---")]


def render(spec, block, variant_text):
    qs = spec["questions"]
    k = len(condition_ids(block))
    cells = sum(len(q["horizons"]) for q in qs)
    out = [HEAD.format(today=TODAY, n=len(qs), k=k)]
    for g in spec["groups"]:
        out.append(GROUP.format(heading=g["heading"]))
        for q in (q for q in qs if q["group"] == g["key"]):
            hz = ", ".join(f"{h} ({q['horizon_meaning'][h]})" for h in q["horizons"])
            out.append(QUESTION.format(id=q["id"], text=q["text"], horizons=hz,
                                       unit_text=q["unit_text"], criteria=q["criteria"]))
    out.append("\n" + block)
    all_h = sorted({h for q in qs for h in q["horizons"]})
    out.append(HORIZONS.format(horizons=", ".join(all_h)))
    out.append("\n")
    if variant_text:
        out.append(variant_text + "\n\n")
    out.append(DELIVERY.format(cells=cells, k=k, total=cells * k * len(PCTS)))
    return "".join(out)


def cells_schema(spec, keys):
    qids = [q["id"] for q in spec["questions"]]
    horizons = sorted({h for q in spec["questions"] for h in q["horizons"]})
    pct = {"type": "object", "properties": {p: {"type": "number"} for p in PCTS}, "required": list(PCTS)}
    return {"type": "array", "items": {"type": "object", "properties": {
        "question_id": {"type": "string", "enum": qids},
        "horizon": {"type": "string", "enum": horizons},
        "percentiles": {"type": "object",
                        "description": "five percentiles (p10, p25, p50, p75, p90), in the question's unit "
                                       "and non-decreasing, per condition id: " + ", ".join(keys),
                        "properties": {c: pct for c in keys}, "required": keys}},
        "required": ["question_id", "horizon", "percentiles"]}}


def tools(spec, keys):
    cells = cells_schema(spec, keys)
    eci = {"type": "object", "description": "your forecast: one number per field, p10, p25, p50, p75, p90, "
                                            "in non-decreasing order",
           "properties": {p: {"type": "number", "minimum": 0, "maximum": 1e9} for p in PCTS},
           "required": list(PCTS)}
    return [
        {"name": "submit_cells",
         "description": "Deliver forecasts in pieces: any subset of question x horizon cells, each with five "
                        "percentiles under every condition id. Call it as often as you like; a later call for "
                        "a cell replaces the earlier one. Returns how many cells have been received and which "
                        "are still missing.",
         "parameters": {"type": "object", "properties": {"forecasts": cells}, "required": ["forecasts"]}},
        {"name": "submit_forecast",
         "description": "Submit your final answer: the rationale, the key sources you read, and any question x "
                        "horizon cells not yet delivered with submit_cells.",
         "parameters": {"type": "object", "properties": {
             "eci_forecast": eci, "forecasts": cells, "rationale": {"type": "string"},
             "key_sources": {"type": "array", "items": {"type": "string"}}},
             "required": ["eci_forecast", "rationale"]}},
    ]


def main():
    spec = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    variants = json.loads((HERE / "variants.json").read_text(encoding="utf-8"))["variants"]
    block = conditions_block(SKELETON.read_text(encoding="utf-8"), k=14)
    keys = condition_ids(block)
    assert keys[0] == "unconditional" and len(keys) == 14, keys
    out = HERE / "prompts"
    out.mkdir(exist_ok=True)
    for v in variants:
        (out / f"welfare-{v['condition']}.txt").write_text(render(spec, block, v["text"]), encoding="utf-8")
    (out / "tools.json").write_text(json.dumps(tools(spec, keys), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(variants)} prompts and tools.json to {out}")


if __name__ == "__main__":
    main()
