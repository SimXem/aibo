# Damages without mortality (2026-10-21)

**What changed.** The Severity definitions' economic-damages accounting no
longer counts monetized mortality. The bullet "Monetized mortality, using a
value of a statistical life (VSL) of $2.2 million, regardless of the geographic
distribution of fatalities" is replaced by an exclusion: "Do not count the
monetized value of lives lost or of morbidity (no value of a statistical life);
deaths and illness count only through their real economic costs, such as lost
output and medical costs." Direct losses, response costs, the three-year
window, 2026 USD and the exclusion of notional market-value losses are
unchanged. The new wording is `data/auto-arc/definitions-2026-10-21.md`.

**Who decided, and why.** The project lead, 2026-10-21, after the first run
under the two-leg ladder (`docs/severity-legs-2026-10-19.md`). With lost lives
counted at $2.2M each and every dollar threshold equal to its death threshold
× $2.2M, the damages question contained the deaths question at every rung:

- The damages curve was the deaths curve plus whatever reached the dollar
  figure through economic losses. It could not be read as economic risk.
- At the top rungs the two questions were nearly the same. $220T at the 100M
  rung and $2.2Q at the 1B rung are far beyond what economic losses alone can
  reach within three years against roughly $110T a year of world output, so
  only the deaths could get there. The 2026-10-21 run's by-2030 panel medians
  for "any AI-related incident": 2.37% (deaths) vs 3.47% (damages) at 100M,
  1.42% vs 1.69% at 1B.
- The legs did not match: the deaths leg counts equivalent morbidity (10
  QALYs per death), but damages monetized mortality only, so even the
  containment was not exact.

**What did not change.** The thresholds ($220M … $2.2Q, so the two ladders keep
sharing rung positions; the 1:$2.2M ratio is now only a shared log scale, not
a conversion), the deaths leg, the attribution test, the counting rules, the
grid (73 questions, 438 cells), the cross-cutting questions, the prompt
variants, the scenarios and the loop.

## Identifiers and versions

- Instrument version `airo-incidents-prospective-v3` (`redlines/instrument.py`).
  v2's generated questions and definitions are archived under
  `data/instruments/airo-incidents-prospective-v2/`.
- Protocol tag `unified-joint-combined-v12` (`redlines/conditional.py`
  `PROTOCOL_LINEAGE`, `code/make_combined_conditions.py`).
- The ladder spec drops `notes.vsl_usd`, the `relations.legs` containment and
  the BRACKET case on the damages leg (the AI catastrophe question is still
  bounded by the AI deaths ladder's 100M rung). The coherence audit drops the
  LEG constraint, and the launch validator its `deaths_within_damages`
  warning: neither ladder bounds the other now.

## The cutover

The current-instrument views (Graph 1, Graph 2, the data bank, the Policy
levers tab) show no reading until the first run under v3 lands. The publish
gate withholds the rebuilt page until a complete v3 run exists, so the live site
keeps the last good build until then. The prompt is 103 KB, as before.
