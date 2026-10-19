"""Question-version boundaries and dated incident onset windows.

The joint call changes as a whole even though only the incident definitions
changed. Old responses are retained, never inferred to answer the new rules.

Versions, newest first (each one's generated question set is archived under
data/instruments/<version>/ when the next replaces it):

  airo-incidents-prospective-v2  2026-10-19: every severity rung is asked as
                                 TWO questions, one resolving on deaths (or
                                 equivalent morbidity) and one on economic
                                 damages, instead of one deaths-OR-damages
                                 question (docs/severity-legs-2026-10-19.md).
                                 Thresholds, attribution, accounting and the
                                 counting rules are v1's.
  airo-incidents-prospective-v1  2026-09-10: the prospective counting rules
                                 (docs/counting-rules-specification-2026-09-10.md).
  legacy-2026-08-31              the August 31 definitions, before rows
                                 carried a version.
"""
from datetime import date

CURRENT_INSTRUMENT = "airo-incidents-prospective-v2"


def instrument_rows(rows, version=CURRENT_INSTRUMENT):
    return [r for r in rows if r.get("instrument_version") == version]


def counting_windows(question, horizons, run_date, spec):
    """Inclusive UTC calendar-date onset windows for one incident question."""
    from .questions import resolves_on

    if question.get("category") != "incident":
        return None
    if isinstance(run_date, str):
        run_date = date.fromisoformat(run_date[:10])
    return {
        h: {"start": run_date.isoformat(),
            "end": resolves_on(h, run_date, spec),
            "timezone": "UTC", "harm_years": 3}
        for h in horizons if h in question["horizons"]
    }
