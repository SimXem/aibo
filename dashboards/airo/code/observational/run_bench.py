"""Conditional-coherence MVP — elicitation runner. See spec.md.

Usage:
  python3 run_bench.py pilot   # 3 pairs (pos/neg/control) x all models, K=1;
                               # writes results_pilot.jsonl + pilot_raw.txt.
                               # READ pilot_raw.txt BEFORE the full run.
  python3 run_bench.py         # full run; resumable via results.jsonl
"""
import json, os, re, sys, datetime, time
import anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
PAIRS = json.load(open(f"{HERE}/pairs_selected.json"))
MODELS = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5"]
K = 5
HORIZON_DAYS = 30
PILOT = len(sys.argv) > 1 and sys.argv[1] == "pilot"
if PILOT:
    want = ["associated_pos_0.85", "hemispheric_probe", "control_independent"]
    PAIRS = [next(p for p in PAIRS if p["category"] == c) for c in want]
    K = 1
OUT = f"{HERE}/results{'_pilot' if PILOT else ''}.jsonl"
RAW = open(f"{HERE}/pilot_raw.txt", "w") if PILOT else None

PROMPT = """You are forecasting two yes/no questions about the same 30-day window.

Question A: {q_a}
Question B: {q_b}

Today is {due_date}. Both questions resolve on {res_date}.

You may reason briefly first. Then end your reply with one JSON object, alone on its final line, with exactly these keys:
  "p_a":             probability that Question A resolves YES
  "p_b":             probability that Question B resolves YES
  "p_b_given_a":     probability that B resolves YES, supposing you learned only that A resolved YES
  "p_b_given_not_a": probability that B resolves YES, supposing you learned only that A resolved NO
All four are numbers in [0,1]."""

def fill(q, due, res):
    return q.replace("{forecast_due_date}", due).replace("{resolution_date}", res)

def parse(txt):
    for o in reversed(re.findall(r"\{[^{}]*\}", txt)):
        try:
            d = json.loads(o)
            vals = {k: float(d[k]) for k in ("p_a", "p_b", "p_b_given_a", "p_b_given_not_a")}
            if all(0.0 <= v <= 1.0 for v in vals.values()):
                return vals
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return None

def main():
    client = anthropic.Anthropic()
    due = datetime.date.today()
    res = due + datetime.timedelta(days=HORIZON_DAYS)
    due_s, res_s = due.isoformat(), res.isoformat()

    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            r = json.loads(line)
            done.add((r["pair_id"], r["model"], r["rep"]))

    with open(OUT, "a") as fh:
        for pair in PAIRS:
            prompt = PROMPT.format(
                q_a=fill(pair["q_a"], due_s, res_s),
                q_b=fill(pair["q_b"], due_s, res_s),
                due_date=due_s, res_date=res_s)
            for model in MODELS:
                for rep in range(K):
                    key = (pair["pair_id"], model, rep)
                    if key in done:
                        continue
                    for attempt in range(4):
                        try:
                            # max_tokens=16000: thinking tokens count against the
                            # cap on adaptive-thinking models; 4096 truncates.
                            resp = client.messages.create(
                                model=model, max_tokens=16000,
                                messages=[{"role": "user", "content": prompt}])
                        except anthropic.RateLimitError:
                            time.sleep(20 * (attempt + 1)); continue
                        except anthropic.APIStatusError as e:
                            print(f"SKIP {key}: {e.status_code}"); break
                        if resp.stop_reason != "end_turn":
                            print(f"RETRY {key}: stop_reason={resp.stop_reason}"); continue
                        text = "".join(b.text for b in resp.content if b.type == "text")
                        if RAW:
                            RAW.write(f"\n===== {pair['pair_id']} {model} =====\n{text}\n")
                            RAW.flush()
                        vals = parse(text)
                        if vals is None:
                            print(f"RETRY {key}: unparseable"); continue
                        fh.write(json.dumps({
                            "pair_id": pair["pair_id"], "model": model, "rep": rep,
                            "due_date": due_s, "res_date": res_s, **vals}) + "\n")
                        fh.flush()
                        break
                    else:
                        print(f"GIVE UP {key}")
            print(f"{pair['pair_id']} done")
    if PILOT:
        print("\nPILOT COMPLETE. Read pilot_raw.txt before launching the full run.")

if __name__ == "__main__":
    main()
