#!/usr/bin/env python3
"""Cache the live METR ECI chart used by AIRO's Capability tab.

The live Streamlit app is the source for this snapshot.  Its plotted linear
trend (retrieved 2026-09-10) starts from the fitted value 167.3141 on
2026-09-03, has a 16.3-point annual pace and an 80% pace interval of
8.2--32.6.  We retain those displayed inputs here, rather than substituting
the older public Git checkout, which was behind the live app.
"""
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "code"))
from eci_projection_metrgraph import project  # noqa: E402

OUT = os.path.join(ROOT, "data", "eci_trend_2026-09-10.json")
N, SEED = 400000, 1
ANCHOR = datetime(2026, 9, 3)
END = datetime(2030, 12, 31)
PACE_CI80 = (8.2, 32.6)
FIT_AT_ANCHOR = 167.31405850340178
START_SD = 2 / (2 * 1.282)

# New highs among the US models displayed by the live METR chart.  This is
# chart context, not the historical prompt shown to the September 10 panel.
FRONTIER = [
    ("2024-02-29", 126.9, "Claude 3 Opus"),
    ("2024-04-09", 127.25, "GPT-4 Turbo (Apr 2024)"),
    ("2024-05-13", 128.98, "GPT-4o (May 2024)"),
    ("2024-06-20", 130.0, "Claude 3.5 Sonnet (Jun 2024)"),
    ("2024-09-12", 135.84, "o1-mini (high)"),
    ("2024-12-17", 141.9, "o1 (high)"),
    ("2025-03-31", 144.2, "Gemini 2.5 Pro Preview (Mar 2025)"),
    ("2025-04-16", 146.91, "o3 (high)"),
    ("2025-06-10", 147.46, "o3-pro"),
    ("2025-08-07", 150.0, "GPT-5 (low)"),
    ("2025-10-07", 150.3, "GPT-5 Pro"),
    ("2025-11-18", 152.94, "Gemini 3 Pro Preview"),
    ("2025-12-11", 155.3, "GPT-5.2 Pro"),
    ("2026-02-05", 156.4, "GPT-5.3 Codex (high)"),
    ("2026-03-05", 158.89, "GPT-5.4 Pro (xhigh)"),
    ("2026-04-23", 159.23, "GPT-5.5 (xhigh)"),
    ("2026-04-23", 162.03, "GPT-5.5 Pro (xhigh)"),
    ("2026-06-09", 162.9, "Claude Fable 5 (max)"),
    ("2026-09-03", 169.2, "GPT-6 Astra (high)"),
]


def build():
    dpp_lo, dpp_hi = 365.25 / PACE_CI80[1], 365.25 / PACE_CI80[0]
    import numpy as np
    f = {
        "mu_ln": (np.log(dpp_lo) + np.log(dpp_hi)) / 2,
        "sg_ln": (np.log(dpp_hi) - np.log(dpp_lo)) / (2 * 1.282),
        "fitted": FIT_AT_ANCHOR,
        "pos_sd": START_SD,
        "cur": {"date": ANCHOR},
    }
    targets, day = [], ANCHOR
    while day <= END:
        targets.append((day.strftime("%Y-%m-%d"), day))
        day += timedelta(days=1)
    table = project(None, N, SEED, targets, f)
    return {
        "what": "Live METR ECI linear projection, daily p25/p50/p75 of the US frontier ECI",
        "source": {
            "label": "METR graph's live ECI trend, linear default",
            "app": "https://metrgraph.streamlit.app/?tab=eci",
            "retrieved": "2026-09-10",
            "method": "Displayed live-app fit: 16.3 ECI points/year, 80% pace interval 8.2--32.6; seeded replica of its displayed projection.",
            "n_samples": N,
            "seed": SEED,
        },
        "fit": {
            "n_frontier": len(FRONTIER),
            "pts_per_year": 16.3,
            "pts_per_year_ci80": list(PACE_CI80),
            "anchor": {"model": "GPT-6 Astra (high)", "date": "2026-09-03", "score": 169.2},
            "fitted_trend_score_at_anchor": round(FIT_AT_ANCHOR, 2),
            "start_sd": round(START_SD, 3),
        },
        "from": ANCHOR.strftime("%Y-%m-%d"),
        "to": END.strftime("%Y-%m-%d"),
        "frontier": [{"date": d, "score": s, "model": m} for d, s, m in FRONTIER],
        "daily": [{"date": lab, "p25": row["p25"], "p50": row["p50"], "p75": row["p75"]}
                  for lab, row in table.items()],
    }


if __name__ == "__main__":
    json.dump(build(), open(OUT, "w"), indent=1)
    print(f"-> {OUT}")
