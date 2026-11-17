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


ANALYSES = """<section class="plan"><h2>What will be analysed</h2>
<p>After the run, <code>code/analyze_cellcheck.py</code> sets each cell beside <b>the same cell in the published
(unified) call</b>: the same model, prompt, horizon and scenario, from the published run of the same day (read from the
dashboard's download, <code>redlines-data.zip</code>). Everything below is computed per model, then for both models
together (40 cells).</p>
<dl>
<dt>Per cell</dt>
<dd>The mean of the 5 isolated answers, their spread, the unified answer, the <b>absolute error</b> between the two in
percentage points, and the difference in log-odds (isolated minus unified) with its z.</dd>
<dt>Mean absolute error (MAE)</dt>
<dd>The absolute errors averaged over the 20 cells, in percentage points and in log-odds. Its p-value is simulated:
how often a MAE at least this large arises when the two arms differ only by noise.</dd>
<dt>Direction</dt>
<dd>The mean signed difference: whether a cell asked alone tends to come out higher (+) or lower (−) than inside
the unified call.</dd>
<dt>Chi-square test</dt>
<dd>One test of whether all 20 cells agree up to noise (X² on 20 degrees of freedom per model, 40 for both).
The noise is the isolated repeats' spread plus the unified call's own noise. The unified noise is estimated from the same day's
five published calls of the model across all 84 cells of the question, and cells from one unified call share its
random draw. On simulated data with no difference, the test rejects 5% of the time at p &lt; 0.05.</dd>
<dt>Sensitivity check</dt>
<dd>The same test, assuming instead that the unified call is exactly as noisy as an isolated one, to show how much
the verdict depends on the noise estimate.</dd>
<dt>ECI gap</dt>
<dd>Policy and capability cells are conditioned on the model's own ECI forecast. The isolated run takes it in a
separate step, the unified call in its Step 1. The report prints both, since a cell's difference includes theirs.</dd>
</dl>
<p><b>How to read it.</b> A small p means a cell's answer depends on being asked inside the whole call. That covers
everything that differs between the two: the other 6,131 probabilities, how much the model searches for one question
versus all of them, and the separate ECI step. A large p means no difference was detected at this sample size; it
does not show the arms are equal. Five repeats make single cells noisy, so the MAE and the chi-square over all
cells are the main results. Because each prompt is dealt a different scenario at each horizon, no prompt's effect
is tied to one scenario. There is no separate test by horizon, prompt or scenario; the per-cell table shows any
pattern.</p>
<p class="cmd"><code>python code/analyze_cellcheck.py private/redlines-data.zip
results/experiments/cellcheck-&lt;run&gt;-cells.jsonl --json private/cellcheck.json</code></p>
</section>"""

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
.key span{{padding:0 6px;border-radius:3px}}.plan{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:4px 18px 10px;margin-top:24px}}.plan dt{{font-weight:600;margin-top:10px}}.plan dd{{margin:2px 0 0 0;color:var(--fg)}}.cmd code{{white-space:normal;font-size:13px}}.deal{{border-collapse:collapse;margin:8px 0 4px;font-size:14px}}.deal th,.deal td{{border:1px solid var(--line);padding:3px 10px;text-align:left}}.deal th{{color:var(--soft);font-weight:600}}</style></head><body><main>
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
{ANALYSES}
{''.join(sections)}</main></body></html>'''
open(out, "w").write(page)
print(n, "cells ->", out)
