"""Public dashboard fields from completed RSI Baseline runs."""
import hashlib
import json
from datetime import date
from statistics import median

from .conditions import DOMAINS
from .instrument import fields, validate


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_run(folder, source, sections):
    plan = read(folder / "plan.json")
    ensemble = read(folder / "ensemble.json")
    digest = hashlib.sha256(plan["prompt"].encode()).hexdigest()
    if (plan["condition"] != "baseline" or ensemble["condition"] != "baseline"
            or plan["survey"] != source or digest != plan["prompt_sha256"]
            or digest != ensemble["prompt_sha256"] or plan["date"] != ensemble["date"]):
        raise ValueError(f"{folder}: instrument or run metadata mismatch")
    access = plan.get("web_access")
    domains = plan.get("blocked_domains", [])
    expected_domains = DOMAINS.get(access, [])
    if ((access is not None and access not in DOMAINS) or domains != expected_domains
            or ensemble.get("web_access") != access or ensemble.get("blocked_domains", []) != domains):
        raise ValueError(f"{folder}: inconsistent web access condition")
    date.fromisoformat(plan["date"])
    members = plan["members"]
    ids = [m["model"] for m in members]
    if not ids or len(set(ids)) != len(ids) or ids != ensemble["models"]:
        raise ValueError(f"{folder}: inconsistent panel")
    models = []
    for member in members:
        record = read(folder / (member["key"] + ".json"))
        if record["model"] != member["model"] or record["prompt_sha256"] != digest:
            raise ValueError(f"{folder}: mismatched model receipt")
        if record.get("web_access") != access or record.get("blocked_domains", []) != domains:
            raise ValueError(f"{folder}: mismatched model web access condition")
        response = record["response"]
        validate(sections, response)
        models.append({"id": member["model"], "label": member.get("label", member["model"]),
                       "answers": response["answers"], "rationales": response["rationales"]})
    answers = {q["id"]: {f: median(m["answers"][q["id"]][f] for m in models) for f in fields(q)}
               for s in sections for q in s["questions"]}
    if answers != ensemble["answers"]:
        raise ValueError(f"{folder}: ensemble disagrees with model receipts")
    return {"id": folder.parent.name if plan.get("conditions") else folder.name,
            "web_access": access or "legacy", "date": plan["date"], "answers": answers, "models": models}


def load_runs(root, source, sections, publication=False):
    """Read single-condition runs and paired batches from the runner's output."""
    runs = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        plan_path = folder / "plan.json"
        if not plan_path.is_file():
            if publication:
                raise ValueError(f"{folder}: missing frozen run plan")
            continue
        plan = read(plan_path)
        conditions = plan.get("conditions")
        if conditions and conditions != list(DOMAINS):
            raise ValueError(f"{folder}: unexpected paired conditions")
        for access in conditions or [None]:
            part = folder / access if access else folder
            if not (part / "ensemble.json").exists():
                if publication:
                    raise ValueError(f"{part}: incomplete run in publication data")
                continue
            if access:
                subplan = read(part / "plan.json")
                expected = dict(plan, web_access=access, blocked_domains=DOMAINS[access])
                if subplan != expected:
                    raise ValueError(f"{part}: condition differs from frozen paired plan")
            runs.append(load_run(part, source, sections))
    return sorted(runs, key=lambda r: (r["date"], r["id"]))
