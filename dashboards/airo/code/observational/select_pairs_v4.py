"""Selection v4 (final). Ground truth = SIN-DESEASONALIZED anomaly phi
(pair_candidates_anomaly2.jsonl): the association that remains given the
date, which is what a date-aware forecaster should express. Motivated by
the v3 pilot: models correctly conditioned on the date; panel phi
conflated seasonal covariation with anomaly covariation.

Scored classes (anomaly-certified + mechanism-declared):
  sanity, positives (metro, 4 bands), controls (anomaly ~0, cross-basin).
Unscored: hemispheric_probe (metro/N-Atl x southern) — anomaly ground
truth is undetermined on a 14-month panel (some pairs collapse to ~0,
some retain ~-0.4 with no defensible mechanism); model behavior is
REPORTED, never scored."""
import json, os, random, re

S = os.path.dirname(os.path.abspath(__file__))
METRO = {"Abbeville","Ajaccio","Alençon","Bordeaux–Mérignac Airport","Bourges",
"Brest Bretagne Airport","Caen – Carpiquet Airport","Clermont-Ferrand Auvergne Airport",
"Dijon-Bourgogne Airport","Embrun","EuroAirport Basel Mulhouse Freiburg","Gourdon",
"Le Puy – Loudes Airport","Lille Airport","Limoges – Bellegarde Airport",
"Lyon–Saint Exupéry Airport","Marignane","Millau","Mont-de-Marsan","Montélimar",
"Nancy – Ochey Air Base","Nantes Atlantique Airport","Nice","Orly","Perpignan",
"Ploumanac'h","Pointe De La Hague","Poitiers–Biard Airport","Reims – Prunay Aerodrome",
"Rennes–Saint-Jacques Airport","Rouen Airport","Saint-Girons","Strasbourg Airport",
"Tarbes–Lourdes–Pyrénées Airport","Toulouse–Blagnac Airport","Tours","Troyes-Barberey Airport"}
TROPICAL_N = {"Cayenne – Félix Éboué Airport","La Désirade",
"Martinique Aimé Césaire International Airport","Pointe-à-Pitre International Airport",
"Saint Barthélemy","Saint-Laurent"}
SOUTHERN = {"Amsterdam Island","Europa Island","Glorioso Islands","Grande Terre",
"Juan de Nova Island","Pamandzi","Roland Garros Airport","Tromelin Island",
"Île de la Possession"}
N_ATLANTIC = {"Saint-Pierre"}

def station(q):
    m = re.search(r"station at (.+?) will be higher", q)
    return m.group(1) if m else None
def region(s):
    for name, grp in [("METRO",METRO),("TROPICAL_N",TROPICAL_N),
                      ("SOUTHERN",SOUTHERN),("N_ATLANTIC",N_ATLANTIC)]:
        if s in grp: return name
    return None

rows = []
for l in open(f"{S}/pair_candidates_anomaly2.jsonl"):
    r = json.loads(l)
    sa, sb = station(r["q_a"]), station(r["q_b"])
    if not sa or not sb: continue
    ra, rb = region(sa), region(sb)
    if not ra or not rb: continue
    r.update(st_a=sa, st_b=sb, reg_a=ra, reg_b=rb)
    rows.append(r)

# panel phi carried along for the probe report
panel_phi = {}
for l in open(f"{S}/pair_candidates_short.jsonl"):
    r = json.loads(l)
    if r["source"] == "dbnomics": panel_phi[frozenset([r["a"], r["b"]])] = r["phi"]

rng = random.Random(0); used = {}
def take(cands, k, cat, mech, scored):
    out = []
    for r in cands:
        if len(out) >= k: break
        if used.get(r["st_a"], 0) >= 2 or used.get(r["st_b"], 0) >= 2: continue
        used[r["st_a"]] = used.get(r["st_a"], 0) + 1
        used[r["st_b"]] = used.get(r["st_b"], 0) + 1
        r = dict(r); r["category"] = cat; r["mechanism"] = mech; r["scored"] = scored
        r["panel_phi"] = panel_phi.get(frozenset([r["a"], r["b"]]))
        if rng.random() < 0.5:
            for x, y in [("a","b"),("q_a","q_b"),("st_a","st_b"),("reg_a","reg_b")]:
                r[x], r[y] = r[y], r[x]
        out.append(r)
    return out

regs = lambda r: {r["reg_a"], r["reg_b"]}
sel = []
sel += take(sorted([r for r in rows if regs(r)=={"METRO"} and r["phi"]>=0.95 and r["ci_lo"]>=0.85],
            key=lambda r:-r["phi"]), 2, "sanity_near_duplicate",
            "adjacent metropolitan stations; near-identical daily weather", True)
ctl = [r for r in rows if abs(r["phi"])<=0.10 and -0.30<r["ci_lo"] and r["ci_hi"]<0.30
       and (("TROPICAL_N" in regs(r) and regs(r)!={"TROPICAL_N"} and "SOUTHERN" not in regs(r))
            or regs(r)=={"METRO","N_ATLANTIC"} or regs(r)=={"N_ATLANTIC","TROPICAL_N"}
            or regs(r)=={"TROPICAL_N","SOUTHERN"})]
sel += take(sorted(ctl, key=lambda r:(r["ci_hi"]-r["ci_lo"])), 8, "control_independent",
            "one aseasonal-tropical or trans-Atlantic side; no shared anomaly driver", True)
for lo, hi in [(0.85,0.95),(0.65,0.85),(0.45,0.65),(0.30,0.45)]:
    band = [r for r in rows if regs(r)=={"METRO"} and lo<=r["phi"]<hi
            and r["ci_lo"] > (0.05 if lo<=0.45 else 0)]
    sel += take(sorted(band, key=lambda r:-r["n"]), 3, f"associated_pos_{lo}",
                "metropolitan stations; shared synoptic anomalies, strength falls with distance", True)
probe = [r for r in rows if "SOUTHERN" in regs(r) and (regs(r) & {"METRO","N_ATLANTIC"})]
sel += take(sorted(probe, key=lambda r: (panel_phi.get(frozenset([r["a"],r["b"]]), 0))), 6,
            "hemispheric_probe",
            "opposite hemispheres; panel phi is negative (seasonal see-saw) but "
            "date-conditional anomaly phi is undetermined on this panel — REPORTED, NOT SCORED", False)

for i, r in enumerate(sel): r["pair_id"] = f"pair-{i:02d}"
json.dump(sel, open(f"{S}/pairs_selected.json", "w"), indent=1)
from collections import Counter
print(Counter(r["category"] for r in sel), "| total:", len(sel))
for r in sel:
    pp = f" panel={r['panel_phi']:+.2f}" if r.get("panel_phi") is not None else ""
    print(f"{r['pair_id']} {'S' if r['scored'] else '-'} {r['category']:<22} anom={r['phi']:+.2f} CI[{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}]{pp} | {r['st_a']} || {r['st_b']}")
