"""welfare-preview.html: the welfare page filled for a look at the layout.
Oct 1 is the welfare pilot's one REAL Opus 5.5 call (2026-10-01) under every
prompt; the Timeline shows prompts only from 2026-10-21, so it draws one
point. Oct 22 is INVENTED for all five prompts. Both go through run_one_joint
(a stub loop: no model is called) and redlines.views.welfare.

The invented answers move the pilot's percentiles the way each prompt might
plausibly push a model: `independent` a little lower; `recent` lower and
tighter on near-term growth; `critical` lower and wider; `two-step` (reason
about AI capability first) a fatter upper tail, most at 2050/2100. Oct 22
adds a small drift and per-cell jitter.

The two AI-benefit questions (probabilities, 2026-10-27) were not asked by
the pilot, so they have no Oct 1 point; their Oct 22 answers are INVENTED
too: a median per horizon, moved on the logit by each condition (a slowdown
policy lower, a higher ECI level higher) and each prompt.

    REDLINES_ENV_FILE=/dev/null python3 welfare/tools/preview.py
"""
import hashlib, importlib.util, json, math, os, sys, tempfile
from datetime import date
from pathlib import Path
REPO = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, REPO)
spec_ = importlib.util.spec_from_file_location("run_unified", f"{REPO}/code/run_unified.py")
ru = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(ru)
from redlines import experiments
from redlines.pages import hydrate_page
from redlines.views import welfare

P = ru.PERCENTILE_FIELDS
pilot = json.load(open(f"{REPO}/welfare/reference/welfare-pilot-blob-2026-10-01.json"))
call = next(iter(pilot["rationales"]["calls"].values()))
exp = experiments.load("welfare")
pol = ru.load_policies(os.path.join(ru.ROOT, "data/welfare_conditions.json"))
g, b, h, _, spec = ru.load_questions(pol["questions"])
h = ru.set_horizons(pol, h)
base = {}     # (question, horizon, condition) -> the pilot's percentiles
for q in pilot["questions"]:
    for hz, cell in q["byHorizon"].items():
        base[(q["id"], hz, "unconditional")] = cell["baselines"][0]["q"]
        for bar in cell["bars"]:
            base[(q["id"], hz, bar["id"])] = bar["models"][0]["q"]

# Per prompt, per kind of question (le = years, gdp = % a year):
# (median shift at the near horizon, at the far one, width factor, upper-tail skew)
PROMPTS = {
    "none":        {"le": (0.0, 0.0, 1.0, 0.0),   "gdp": (0.0, 0.0, 1.0, 0.0)},
    "independent": {"le": (-0.3, -0.5, 1.05, 0.0), "gdp": (-0.05, -0.1, 1.0, 0.0)},
    "recent":      {"le": (0.2, 0.1, 0.9, 0.0),    "gdp": (-0.2, -0.05, 0.9, 0.0)},
    "critical":    {"le": (-0.5, -0.9, 1.3, 0.0),  "gdp": (-0.1, -0.2, 1.25, 0.0)},
    "two-step":    {"le": (0.3, 1.2, 1.3, 1.5),    "gdp": (0.05, 0.4, 1.35, 0.6)},
}
DRIFT = {"le": (0.1, 0.3), "gdp": (-0.05, 0.1)}       # Oct 22 against Oct 1, near and far
SKEW = {"p10": 0, "p25": 0, "p50": 0, "p75": 0.4, "p90": 1.0}

def jitter(*key):
    return (int(hashlib.sha256(repr(key).encode()).hexdigest()[:6], 16) / 0xFFFFFF - 0.5)

def answer(qid, hz, cid, prompt, day):
    q = base[(qid, hz, cid)]
    kind = qid.split(":")[0]
    far = hz != ("2050" if kind == "le" else "2030")
    near_s, far_s, wf, skew = PROMPTS[prompt][kind]
    shift = far_s if far else near_s
    if day == "2026-10-22":
        shift += DRIFT[kind][far] + jitter(qid, hz, prompt) * (0.3 if kind == "le" else 0.08)
        wf *= 1.05
    m = q["p50"]
    out = {p: m + shift + (q[p] - m) * wf + skew * SKEW[p] * (1 if far else 0.4) for p in P}
    return {p: round(v, 2) for p, v in out.items()}

# The AI-benefit questions' invented unconditional answers, per horizon.
PROB = {"ai:pancreatic": {"6mo": 0.001, "12mo": 0.002, "2028": 0.005, "2030": 0.02, "2050": 0.2, "2100": 0.5},
        "ai:garments":   {"6mo": 0.01, "12mo": 0.02, "2028": 0.05, "2030": 0.12, "2050": 0.5, "2100": 0.75}}
# Logit shifts: per condition, and per prompt.
COND = {"unconditional": 0, "sq": 0.05, "p1": 0.1, "p2a": -0.25, "p2b": -0.5, "p3a": -0.2, "p3b": -0.35,
        "p4": -0.15, "p5": -0.7, "eci_p10": -0.45, "eci_p25": -0.2, "eci_p50": 0, "eci_p75": 0.25, "eci_p90": 0.5}
PROMPT_LOGIT = {"none": 0, "independent": -0.1, "recent": 0.1, "critical": -0.3, "two-step": 0.35}

def answer_p(qid, hz, cid, prompt):
    x = math.log(PROB[qid][hz] / (1 - PROB[qid][hz])) + COND[cid] + PROMPT_LOGIT[prompt] + jitter(qid, hz, cid, prompt) * 0.3
    return round(1 / (1 + math.exp(-x)), 4)

def stub(prompt, day):
    def loop(model, text, tools, final_tool, usage=None, partial_tool=None, **kw):
        usage.update(turns=31, cost_usd=16.85)
        ids = {k[2] for k in base}
        cells = [{"question_id": qid, "horizon": hz,
                  "percentiles": {cid: (base[(qid, hz, cid)] if day == "2026-10-01"
                                        else answer(qid, hz, cid, prompt, day)) for cid in ids}}
                 for (qid, hz) in {(k[0], k[1]) for k in base}]
        if day != "2026-10-01":
            cells += [{"question_id": qid, "horizon": hz,
                       "probabilities": {cid: answer_p(qid, hz, cid, prompt) for cid in COND}}
                      for qid, hs in PROB.items() for hz in hs]
        e = dict(pilot["eciForecast"]["Opus 5.5"])
        bump = 0 if day == "2026-10-01" else 1.5 + (2.0 if prompt == "two-step" else 0) - (1.0 if prompt == "critical" else 0)
        return {"forecasts": cells, "rationale": call["rationale"] if day == "2026-10-01"
                else f"[INVENTED for the preview: the {prompt} prompt, {day}]",
                "key_sources": call["sources"], "eci_forecast": {k: round(v + bump, 1) for k, v in e.items()}}, []
    return loop

rows = []
for day in ("2026-10-01", "2026-10-22"):
    for cid in exp["pooled"]:
        ru.call_tools = stub(cid, day)
        rows += ru.run_one_joint("Opus 5.5", "anthropic/claude-opus-5-5", g, b, h, f"{day}T1800Z", 0, spec,
                                 pol["conditions"], pol, exp["conditions"][cid], "welfare", arm="joint#1",
                                 panel={"set": "eci_topk"}, today=date.fromisoformat(day))
# A stub call is stamped with the wall clock; stamp it with its run's day, so
# the rationales match their dates and the file is the same on every run.
for r in rows:
    r["elicited_at"] = f"{r['run_date']}T18:30:00+00:00"
log = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
log.write("".join(json.dumps(r) + "\n" for r in rows)); log.close()
blobs = welfare.build(log_path=log.name)
blobs["WELFARE"]["protocol"] = ("PREVIEW: Oct 1 = the pilot's real Opus 5.5 call; "
                                "Oct 22's five prompts are invented, and so is every AI-breakthrough answer")
open(f"{REPO}/welfare-preview.html", "w").write(hydrate_page(f"{REPO}/web/welfare", blobs))
print("wrote welfare-preview.html; snapshots", [s["date"] for s in blobs["TIMELINE"]["snapshots"]])
