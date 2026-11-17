"""Pool the members and write the submission file.

The system's forecast for a value is the equal-weight mean of the members'
values (a mean of percentiles keeps them in order, and a mean of shares that
each sum to 100 still sums to 100). Every member must have every entry: a
partial ensemble is a different system, so the build refuses one unless told
--allow-partial, and then says which values rest on fewer members.

The file is named <model>.<question_set>.json and is checked with the
organisers' validator before the build reports success.
"""
import json
import statistics
import sys
from pathlib import Path

from . import instrument, run, validate_submission


def pool(question_set, rows):
    """-> (forecasts, short): the submission's entries, and
    [(question id, entry, members that have it, members)] for each entry some
    member lacks."""
    members = list(dict.fromkeys(r["label"] for r in rows))
    by_question = {}
    for r in rows:
        by_question.setdefault(r["question_id"], {})[r["label"]] = r["values"]
    forecasts, short = [], []
    for q in question_set["questions"]:
        keys = instrument.value_keys(q)
        for e in instrument.entries(q):
            have = {m: vals[e["entry"]] for m, vals in by_question.get(q["id"], {}).items() if e["entry"] in vals}
            if len(have) < len(members):
                short.append((q["id"], e["entry"], sorted(have), members))
            entry = {"id": q["id"], "dimension": e["dimension"], "scenario": e["scenario"],
                     "resolution_date": e["resolution_date"]}
            for k in keys:
                entry[k] = round(statistics.fmean(v[k] for v in have.values()), 6) if have else None
            forecasts.append(entry)
    return forecasts, short


def submission(question_set, rows, *, organization, model, model_organization):
    forecasts, short = pool(question_set, rows)
    return {"organization": organization, "model": model, "model_organization": model_organization,
            "benchmark": question_set["benchmark"], "question_set": question_set["question_set"],
            "forecasts": forecasts}, short


def main(args):
    with open(args.questions, encoding="utf-8") as f:
        question_set = json.load(f)
    rows = [r for r in run.load_rows(args.run) if r["question_set"] == question_set["question_set"]]
    if not rows:
        sys.exit(f"{args.run}: no rows for question set {question_set['question_set']}")
    members = list(dict.fromkeys(r["label"] for r in rows))
    built, short = submission(question_set, rows, organization=args.organization, model=args.model,
                              model_organization=args.model_organization)
    for qid, entry, have, _ in short:
        print(f"SHORT   {qid} {entry}: {len(have)} of {len(members)} members ({', '.join(have) or 'none'})")
    if short and not args.allow_partial:
        sys.exit(f"not built: {len(short)} entries lack a member. Ask again (run --resume), or pass --allow-partial.")
    errors, warnings = validate_submission.validate(built, question_set)
    for line in errors:
        print(f"ERROR   {line}")
    for line in warnings:
        print(f"WARNING {line}")
    if errors:
        sys.exit(f"not built: the validator found {len(errors)} errors")
    out = Path(args.out) / f"{args.model}.{question_set['question_set']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    values = sum(len(instrument.value_keys(q)) * len(instrument.entries(q)) for q in question_set["questions"])
    print(f"{out}: {len(built['forecasts'])} entries, {values} values, mean of {len(members)} members "
          f"({', '.join(members)}); validator: {len(errors)} errors, {len(warnings)} warnings")
    return 0
