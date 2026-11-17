"""A test fixture for the 2026-10-19 cutover: rows elicited under the
deaths-OR-damages ladder (instrument v1 and before), re-shaped as the two-leg
instrument writes them, so the real run files under results/runs/ can still
stand in for a complete reading of the current instrument.

Each `ladder:<cause>:<rung>` row becomes a deaths row and -- unless the rung is
extinction, which has no dollar leg -- a damages row with the same forecasts;
every row is stamped with the current instrument version.
"""
import copy

from redlines.instrument import CURRENT_INSTRUMENT


def split_legs(rows, version=CURRENT_INSTRUMENT):
    out = []
    for r in rows:
        parts = r["question_id"].split(":")
        legs = ((("deaths",) if parts[2] == "extinction" else ("deaths", "damages"))
                if parts[0] == "ladder" and len(parts) == 3 else (None,))
        for leg in legs:
            c = copy.deepcopy(r)
            if leg:
                c["question_id"] = f"{r['question_id']}:{leg}"
            c["instrument_version"] = version
            out.append(c)
    return out
