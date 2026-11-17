#!/usr/bin/env python3
"""The cellcheck cell list (experiments/cellcheck/cells.html): every cell the
experiment asks, with the exact prompt the runner builds for it, collapsed.
No model is called.

    python experiments/cellcheck/build_cells_page.py [--date YYYY-MM-DD] [--out PATH]
"""
import argparse, html, os, sys
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "code"))
import run_cellwise as rc  # noqa: E402
import run_unified as ru  # noqa: E402
from redlines import experiments, registry  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ap.add_argument("--date", type=date.fromisoformat, default=date.today(),
                help="the run date the prompts are rendered for (default: today)")
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "cells.html"))
args = ap.parse_args()
out, today = args.out, args.date
exp = experiments.load("cellcheck")
policies, groups, by_group, horizons, spec = rc.load_instrument(os.path.join(ROOT, "data/combined_conditions.json"), today)
sids = [c["id"] for c in policies["conditions"]]
label = {c["id"]: c["label"] for c in policies["conditions"]}
group = {c["id"]: c["group"] for c in policies["conditions"]}
label["unconditional"], group["unconditional"] = "No condition: the world as the model expects it", "unconditional"
pair_of = {"unconditional": "expected policy · expected capability"}
for s in sids:
    pair_of[s] = (f"{label[s]} · capability at the model's own ECI p50" if group[s] == "policy"
                  else f"expected policy · {label[s].replace('Frontier ECI 6 months from the run date = ', 'frontier ECI in 6 months = ')}")
# The horizon grid: the scenarios asked at each of 2030, 2050 and 2100 under
# every prompt's deal (read from the experiment file, where the seeded draw
# put them); a cell outside it is one of the extra random cells.
GRID_H = ("2030", "2050", "2100")
asked = {(cid, *p.split("|")) for cid, c in exp["conditions"].items() for p in c["pairs"]}
five = set.intersection(*({s for cid, h2, s in asked if h2 == h} for h in GRID_H))
deal = {}
for h in GRID_H:
    for cid in exp["conditions"]:
        mine = sorted(s for c2, h2, s in asked if c2 == cid and h2 == h and s in five)
        if len(mine) == 1:
            deal[(cid, h)] = mine[0]
models = [l for l, _ in registry.MODEL_SETS[exp["conditions"]["none"]["model_set"]]()]

def esc(s): return html.escape(s)

def marked(prompt, variant, cid):
    t = esc(prompt)
    v = experiments.VARIANTS.get(variant)
    if v: t = t.replace(esc(v), f'<mark class="v">{esc(v)}</mark>', 1)
    if cid != "unconditional":
        item = next(c for c in policies["conditions"] if c["id"] == cid)
        a = esc(item.get("assume") or "")
        if a and a in t: t = t.replace(a, f'<mark class="s">{a}</mark>', 1)
    return t

rows, n = [], 0
sections = []
for cid, c in exp["conditions"].items():
    sel = rc.selection(c, argparse.Namespace(cells=None, severities=None, causes=None, horizons=None, scenarios=None))
    plan = rc.plan_calls(groups, by_group, horizons, sids, sel, c["bundle"], None)
    eci = rc.eci_prompt(policies, today, c["variant"])
    items = []
    for k in plan:
        n += 1
        h, s = k["hs"][0], k["cid"]
        kind = "grid" if deal.get((cid, h)) == s else "random"
        p = rc.call_prompt(k, spec, policies, today, c["variant"], None, c["research"], c["eci_step"])
        items.append(f'''<details class="cell"><summary><span class="n">{n}</span>
<span class="h">{esc(h)}</span><span class="sc"><b>{esc(s)}</b> <span class="lab">{esc(pair_of[s])}</span></span>
<span class="tag {kind}">{kind}</span><span class="len">{len(p):,} chars</span></summary>
<pre>{marked(p, c["variant"], s)}</pre></details>''')
    vtext = experiments.VARIANTS.get(c["variant"])
    sections.append(f'''<section><h2>{esc(cid)} <span class="sub">prompt variant: {esc(c["variant"])}</span></h2>
<p class="vt">{esc(vtext) if vtext else "Adds no instruction (the baseline prompt)."}</p>
<details class="eci"><summary>ECI step asked first (once per model per repeat) · {len(eci):,} chars</summary><pre>{marked(eci, c["variant"], "unconditional")}</pre></details>
{''.join(items)}</section>''')

page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cellcheck Cells</title><style>
:root{{--bg:#fbfaf7;--fg:#1f2328;--soft:#59636e;--line:#d8dde3;--panel:#fff;--v:#fde68a;--s:#bfdbfe;--grid:#0e7c7b;--rand:#8e2a63}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e6e8eb;--soft:#9aa4af;--line:#30353c;--panel:#1d2025;--v:#6b5a12;--s:#1e3a5f;--grid:#5cc4c2;--rand:#e48ab7}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 64px}}h1{{font-size:24px;margin:0 0 6px}}
h2{{font-size:18px;margin:32px 0 4px}}.sub{{font-weight:400;color:var(--soft);font-size:14px}}
.intro{{color:var(--soft);max-width:72ch}}.vt{{margin:0 0 10px;color:var(--soft);font-style:italic}}
details{{background:var(--panel);border:1px solid var(--line);border-radius:6px;margin:6px 0}}
summary{{cursor:pointer;padding:8px 12px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}}
.n{{color:var(--soft);min-width:2ch;font-variant-numeric:tabular-nums}}.h{{font-weight:600;min-width:4ch}}
.sc{{flex:1;min-width:240px}}.lab{{color:var(--soft);font-size:13px}}.len{{color:var(--soft);font-size:12px}}
.tag{{font-size:12px;border:1px solid;border-radius:10px;padding:0 8px}}.grid{{color:var(--grid)}}.random{{color:var(--rand)}}
.eci summary{{color:var(--soft);font-size:14px}}
pre{{margin:0;padding:12px;border-top:1px solid var(--line);white-space:pre-wrap;word-wrap:break-word;font:12.5px/1.45 ui-monospace,monospace;max-height:70vh;overflow:auto}}
mark.v{{background:var(--v);color:inherit}}mark.s{{background:var(--s);color:inherit}}
.key span{{padding:0 6px;border-radius:3px}}.deal{{border-collapse:collapse;margin:8px 0 4px;font-size:14px}}.deal th,.deal td{{border:1px solid var(--line);padding:3px 10px;text-align:left}}.deal th{{color:var(--soft);font-weight:600}}</style></head><body><main>
<h1>Cellcheck: the {n} cells asked</h1>
<p class="intro">Each cell is the headline question, <b>catastrophe:ai</b> (an AI-related catastrophe killing at least 10% of the population),
asked alone in its own call: one horizon, one scenario, one prompt. Each is asked 5 times by {esc(" and ".join(models))}
(experiments/cellcheck.toml), after an ECI step whose answer the cell prompt quotes. Prompts are shown as on {today.isoformat()};
on the run day the date, the rolling horizons (6 and 12 months) and the ECI target date move with it, and
the numbers shown as <code>[from the ECI step]</code> are the model's own answers to that step.</p>
<p class="key">Marked: <span style="background:var(--v)">the prompt variant's instruction</span>
<span style="background:var(--s)">the scenario's assumption</span>.
<span class="tag grid">grid</span> one of the fifteen horizon-grid cells: the same five scenarios at 2030, 2050 and 2100,
dealt to the prompts afresh at each horizon so no prompt keeps one scenario;
<span class="tag random">random</span> one of the five extra random cells. Every cell comes from one seeded draw
(experiments/cellcheck.toml says how).</p>
<table class="deal"><tr><th>prompt</th>{"".join(f"<th>{h}</th>" for h in GRID_H)}</tr>
{"".join(f"<tr><td>{esc(cid)}</td>" + "".join(f"<td>{esc(deal.get((cid, h), '–'))}</td>" for h in GRID_H) + "</tr>" for cid in exp["conditions"])}</table>
{''.join(sections)}</main></body></html>'''
open(out, "w").write(page)
print(n, "cells ->", out)
