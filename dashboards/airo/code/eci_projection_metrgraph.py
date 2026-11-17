"""Replica of metr_graph's ECI tab at its defaults, run on its own CSV.

Source: https://github.com/peterhurford/metr_graph (visualize_projection.py:
load_eci_frontier() + _render_eci_tab(); live at https://metrgraph.streamlit.app/?tab=eci).
US-best frontier (running max over US models released since 2024-02-29, best
variant per model name), Linear basis: single OLS on the frontier gives pts/yr;
pts/yr sampled lognormal with 80% CI [PPY/2, PPY*2]; start position normal
around the fitted-trend score with 80% CI +/-2; score(t) = start + t / DPP.
Verified 2026-08-28 against the app itself run headlessly (streamlit AppTest,
200k samples): 2027EOY 185.9, 80% CI 173.8-209.7.

    python code/eci_projection_metrgraph.py data/epoch_capabilities_index_2026-08-21.csv 400000 1 [out.json]

Importable too: fit(csv) -> the frontier and the fitted pace; project(csv, n,
seed, targets) -> {label: {date, p5..p95}} for any dates (the analysis of the
self-elicited sets asks for the trend at a run's own target date).
"""
import csv, json, sys
from datetime import datetime
import numpy as np

PCTS = [5, 10, 25, 50, 75, 90, 95]
DEFAULT_TARGETS = [("today", datetime(2026, 8, 28)), ("2026EOY", datetime(2026, 12, 31)), ("2027-Jun", datetime(2027, 6, 30)),
                   ("2027EOY", datetime(2027, 12, 31)), ("2028EOY", datetime(2028, 12, 31)), ("2029EOY", datetime(2029, 12, 31)), ("2030EOY", datetime(2030, 12, 31))]


def fit(CSV):
    """The US-best frontier and the Linear-basis fit, as the app computes them."""
    rows = list(csv.DictReader(open(CSV)))
    valid = []
    for r in rows:
        s, d = r.get('ECI Score', '').strip(), r.get('Release date', '').strip()
        if not s or not d: continue
        try: score, date = float(s), datetime.strptime(d, '%Y-%m-%d')
        except ValueError: continue
        valid.append(dict(name=r.get('Model name', ''), display=(r.get('Display name') or '').strip() or r.get('Model name', ''),
                          date=date, score=score, org=r.get('Organization', ''), country=r.get('Country', '')))
    best = {}
    for m in valid:
        if m['name'] not in best or m['score'] > best[m['name']]['score']: best[m['name']] = m
    ded = sorted(best.values(), key=lambda m: m['date'])
    ded = [m for m in ded if m['date'] >= datetime(2024, 2, 29)]
    ded = [m for m in ded if m['country'] == 'United States of America']
    fr, mx = [], -1e9
    for m in ded:
        if m['score'] > mx: mx = m['score']; fr.append(m)

    base = fr[0]['date']
    days = np.array([(m['date'] - base).days for m in fr], float)
    scores = np.array([m['score'] for m in fr])
    A = np.column_stack([np.ones_like(days), days])
    (intercept_ols, slope), *_ = np.linalg.lstsq(A, scores, rcond=None)
    ppy = round(slope * 365.25, 1)
    ppy_lo, ppy_hi = round(ppy / 2, 1), round(ppy * 2, 1)
    dpp_lo, dpp_hi = 365.25 / ppy_hi, 365.25 / ppy_lo
    mu_ln, sg_ln = (np.log(dpp_lo) + np.log(dpp_hi)) / 2, (np.log(dpp_hi) - np.log(dpp_lo)) / (2 * 1.282)
    fitted = np.mean(scores - slope * days) + slope * days[-1]
    cur = fr[-1]
    pos_lo, pos_hi = round(cur['score'] - 2, 1), round(cur['score'] + 2, 1)
    pos_sd = (pos_hi - pos_lo) / (2 * 1.282)
    return dict(fr=fr, slope=slope, ppy=ppy, ppy_lo=ppy_lo, ppy_hi=ppy_hi, dpp_lo=dpp_lo, dpp_hi=dpp_hi,
                mu_ln=mu_ln, sg_ln=sg_ln, fitted=fitted, cur=cur, pos_sd=pos_sd)


def project(CSV, N=5000, SEED=None, targets=None, f=None):
    """-> {label: {"date", "p5", ..., "p95"}} at the given [(label, datetime)]
    (default DEFAULT_TARGETS). Same draws for the same seed whatever the
    targets, so a row is the same number wherever it is asked for."""
    f = f or fit(CSV)
    rng = np.random.default_rng(SEED)
    dpp = rng.lognormal(f['mu_ln'], f['sg_ln'], N)
    start = rng.normal(f['fitted'], f['pos_sd'], N)
    table = {}
    for lab, t in (targets or DEFAULT_TARGETS):
        el = (t - f['cur']['date']).days
        p = np.percentile(start + el / dpp, PCTS)
        table[lab] = {"date": t.strftime('%Y-%m-%d'), **{f"p{q}": round(float(v), 1) for q, v in zip(PCTS, p)}}
    return table


def main():
    CSV = sys.argv[1]
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    SEED = int(sys.argv[3]) if len(sys.argv) > 3 else None
    OUT = sys.argv[4] if len(sys.argv) > 4 else None
    f = fit(CSV)
    fr, slope, ppy, ppy_lo, ppy_hi, dpp_lo, dpp_hi, fitted, cur, pos_sd = (
        f['fr'], f['slope'], f['ppy'], f['ppy_lo'], f['ppy_hi'], f['dpp_lo'], f['dpp_hi'], f['fitted'], f['cur'], f['pos_sd'])
    table = project(CSV, N, SEED, DEFAULT_TARGETS, f)
    print(f"US frontier ({len(fr)} models, cutoff 2024-02-29):")
    for m in fr: print(f"  {m['date']:%Y-%m-%d}  {m['score']:6.2f}  {m['display']}  [{m['org']}]")
    print(f"\nOLS: slope {slope*365.25:.2f} pts/yr -> PPY {ppy}; +Pts/Yr 80% CI [{ppy_lo}, {ppy_hi}]  (DPP {dpp_lo:.1f}-{dpp_hi:.1f} d/pt, lognormal)")
    print(f"anchor: {cur['display']} {cur['date']:%Y-%m-%d} score {cur['score']}; fitted-on-trend {fitted:.2f}; position N(fitted, sd {pos_sd:.2f}) i.e. 80% CI +/-2\n")
    print(f"{'target':10s} " + " ".join(f"{'p'+str(q):>7s}" for q in PCTS) + f"   (N={N}, seed={SEED})")
    for lab, row in table.items():
        print(f"{lab:10s} " + " ".join(f"{row['p'+str(q)]:7.1f}" for q in PCTS))

    if OUT:
        out = {
            "what": "Projected US-frontier Epoch Capabilities Index (ECI) score by date, percentiles over Monte Carlo trajectories",
            "source": {"repo": "https://github.com/peterhurford/metr_graph", "app": "https://metrgraph.streamlit.app/?tab=eci",
                       "csv": CSV, "csv_refreshed": "2026-08-21", "repo_commit": "b934b67"},
            "method": "metr_graph ECI tab defaults: US-best running-max frontier since 2024-02-29; single OLS -> pts/yr; "
                      "pts/yr lognormal over 80% CI [PPY/2, PPY*2]; start normal around fitted-trend score, 80% CI +/-2; "
                      "score(t) = start + t/DPP. Replica in code/eci_projection_metrgraph.py, verified against the app via AppTest 2026-08-28.",
            "fit": {"n_frontier": len(fr), "pts_per_year": ppy, "pts_per_year_ci80": [ppy_lo, ppy_hi],
                    "anchor": {"model": cur['display'], "date": cur['date'].strftime('%Y-%m-%d'), "score": cur['score']},
                    "fitted_trend_score_at_anchor": round(float(fitted), 2), "start_sd": round(float(pos_sd), 3)},
            "run": {"n_samples": N, "seed": SEED, "computed": "2026-08-28"},
            "frontier": [{"date": m['date'].strftime('%Y-%m-%d'), "score": m['score'], "model": m['display'], "org": m['org']} for m in fr],
            "projection": table,
        }
        json.dump(out, open(OUT, 'w'), indent=1)
        print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
