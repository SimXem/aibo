"""One shared Baseline call per RSI panel member."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
from statistics import median

from fri_forecaster import baseline, eci, keys, panel

from fri_forecaster.tools import BLOCK_ENV, BLOCK_DOMAINS_ENV

from .conditions import DOMAINS
from .instrument import SOURCE, fields, parse, validate

PROJECT = Path(__file__).resolve().parents[1]


def required_object(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def submission_tool(sections):
    answers = {}
    for section in sections:
        for question in section["questions"]:
            answers[question["id"]] = required_object({name: {"type": "number"} for name in fields(question)})
    rationales = {section["id"]: {"type": "string", "description": section["title"]} for section in sections}
    return {"description": "Submit the survey answers and one rationale per section.",
            "parameters": required_object({"answers": required_object(answers),
                                           "rationales": required_object(rationales)})}


def save(path, record):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def execute(out, plan, harness_run=None):
    access = plan.get("web_access", "full-web")
    domains = DOMAINS[access]
    if plan.get("blocked_domains", []) != domains:
        raise ValueError("Frozen web access settings differ from this condition")
    env = {BLOCK_ENV: "", BLOCK_DOMAINS_ENV: " ".join(domains)}
    sections = parse(plan["survey"])
    tool = submission_tool(sections)

    def one(member):
        key = member["key"]
        receipt = out / f"{key}.json"
        if receipt.exists():
            record = json.loads(receipt.read_text(encoding="utf-8"))
            if record["model"] != member["model"] or record["prompt_sha256"] != plan["prompt_sha256"]:
                raise ValueError(f"{receipt} does not match this run")
            if record.get("web_access") != plan.get("web_access") or record.get("blocked_domains", []) != domains:
                raise ValueError(f"{receipt} belongs to a different web access condition")
            validate(sections, record["response"])
            return record
        result = baseline.run(member["model"], plan["prompt"], workdir=str(out / "attempts" / key),
                              cell_schema={"type": "object"}, key_fields=[], allowed_keys=[],
                              submit_forecast=tool, env=env, harness_run=harness_run)
        response = result["answer"]
        try:
            validate(sections, response)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{key}: invalid submission ({exc}); trace: {result.get('trace')}") from exc
        record = {"web_access": plan.get("web_access"), "blocked_domains": domains, "model": member["model"], "prompt_sha256": plan["prompt_sha256"],
                  "response": response, "usage": result["usage"], "evidence": result["evidence"]}
        save(receipt, record)
        print(f"{key}: validated", flush=True)
        return record

    with ThreadPoolExecutor(max_workers=len(plan["members"])) as pool:
        records = list(pool.map(one, plan["members"]))
    ensemble = {}
    for section in sections:
        for q in section["questions"]:
            qid = q["id"]
            ensemble[qid] = {field: median(r["response"]["answers"][qid][field] for r in records)
                             for field in fields(q)}
    save(out / "ensemble.json", {"condition": "baseline", "web_access": plan.get("web_access"), "blocked_domains": domains, "date": plan["date"],
                                 "prompt_sha256": plan["prompt_sha256"],
                                 "models": [r["model"] for r in records], "answers": ensemble})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument", type=Path, default=SOURCE)
    parser.add_argument("--eci-dir", type=Path, default=eci.default_dir())
    parser.add_argument("--out", type=Path, default=PROJECT / "results", help="directory for new runs")
    parser.add_argument("--resume", type=Path, help="complete a previously started run from its frozen plan")
    parser.add_argument("--condition", choices=[*DOMAINS, "both"], help="default full-web; both uses the same panel twice")
    args = parser.parse_args()
    if args.resume and args.condition:
        parser.error("a resumed run uses its frozen conditions")
    if any(os.environ.get(key, "").strip() for key in (BLOCK_ENV, BLOCK_DOMAINS_ENV)):
        parser.error("RSI sets its URL filters per condition; clear ambient forecast URL filters")
    now = datetime.now(timezone.utc)
    out = (args.resume or args.out / now.strftime("%Y%m%dT%H%M%S.%fZ")).resolve()
    if not args.resume:
        out.mkdir(parents=True)
    with (out / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume:
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            if plan.get("conditions") and plan.get("web_access"):
                parser.error(f"resume a paired run from {out.parent}")
        else:
            survey = args.instrument.read_text(encoding="utf-8")
            parse(survey)
            members, provenance = panel.panel(snapshot_dir=args.eci_dir, require_today=True)
            today = now.date().isoformat()
            prompt = f"Today is {today}.\n\n{survey.rstrip()}\n\nSubmit your answers using submit_forecast."
            plan = {"condition": "baseline", "date": today, "survey": survey, "prompt": prompt,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "system_prompt": baseline.SYSTEM,
                    "members": members, "panel": provenance}
            conditions = list(DOMAINS) if args.condition == "both" else [args.condition or "full-web"]
            if len(conditions) == 1:
                plan.update(web_access=conditions[0], blocked_domains=DOMAINS[conditions[0]])
            else:
                plan["conditions"] = conditions
            save(out / "plan.json", plan)
        print(out, flush=True)
        if "TAVILY_API_KEY" not in keys.load_keys():
            parser.exit(1, "TAVILY_API_KEY is required for Baseline research tools\n")
        conditions = plan.get("conditions")
        for access in conditions or [plan.get("web_access")]:
            directory = out
            member_plan = plan
            if conditions:
                directory = out / access
                directory.mkdir(exist_ok=True)
                member_plan = dict(plan, web_access=access, blocked_domains=DOMAINS[access])
                save(directory / "plan.json", member_plan)
            pending = any(not (directory / (m["key"] + ".json")).exists() for m in plan["members"])
            if pending and plan["panel"].get("snapshot") != datetime.now(timezone.utc).date().isoformat():
                parser.exit(1, "The frozen panel is from a different UTC day. Start a fresh run.\n")
            execute(directory, member_plan)


if __name__ == "__main__":
    main()
