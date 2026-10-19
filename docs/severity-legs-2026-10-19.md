# The severity legs: deaths and damages asked apart (2026-10-19)

**What changed.** Every rung of the incident ladder used to be one question
resolving on *deaths OR damages* — "1,000 deaths (or equivalent morbidity) or
$2.2 billion". Since 2026-10-19 each rung is two questions: one resolving on the
deaths (or equivalent morbidity), one on the economic damages. Four causes ×
nine rungs on the deaths ladder (the extinction rung has no dollar leg) and ×
eight on the damages ladder: 68 ladder questions where there were 36, 73 in the
set where there were 41, 438 question × horizon cells where there were 246.

**Who asked, and why.** Ezra Karger, in the 2026-10-19 one-on-one: "did you
separate out dollars and damages at some point? … of all the things we're doing,
that feels pretty useful given that graph can then be split." Nick Merrill
agreed the same day. The severity chart (Graph 2) is now two charts, a deaths
ladder and a damages ladder.

**What did not change.** The thresholds (the workbook's severity options, split
at their "or", so no number is retyped), the attribution test, the accounting
conventions, the 2026-09-10 counting rules, the horizons, the conditions, the
prompt variants, the sixth call and the loop. The cross-cutting questions are
untouched.

## Identifiers and versions

- Question ids are `ladder:<cause>:<rung>:<leg>` with `leg` ∈ {`deaths`,
  `damages`}; e.g. `ladder:cyber:1k:deaths`, `ladder:cyber:1k:damages`. The
  rung key is shared by both legs (the index of a severity level), so the two
  ladders line up rung for rung. The extinction rung is `ladder:<cause>:extinction:deaths`.
- Instrument version `airo-incidents-prospective-v2` (`redlines/instrument.py`).
  The v1 generated questions are archived under
  `data/instruments/airo-incidents-prospective-v1/`; rows carry the version, so
  no view answers a split question with a deaths-OR-damages probability.
- Protocol tag `unified-joint-combined-v11` (`redlines/conditional.py`
  `PROTOCOL_LINEAGE`, `code/make_combined_conditions.py`).
- The spec (`data/autoarc_ladder.json`) carries `legs` (key, label, unit), each
  rung's two thresholds and per-leg labels under `rungs[].legs`, and each
  question's `leg`.

## A containment the definitions state

The Severity definitions count *monetized mortality, at the stated value of a
statistical life ($2.2M)*, toward economic damages. Each rung's dollar
threshold is its death threshold × that VSL. So an incident that reaches a
rung's death threshold has, by definition, reached its dollar threshold: **the
damages question contains the deaths question at every rung**, and the
deaths-OR-damages question the set asked until now was, logically, the damages
question. The ladder spec records this as `relations.legs`; the coherence audit
checks it as the `LEG` constraint (folded into the SUBSET row on the page),
measured and never imposed. The BRACKET relation (the AI catastrophe question
inside the AI ladder's 100M rung) now names a leg and holds on both.

## What the dashboard does with the two ladders

- **Graph 2**: two charts, one per leg, each with its own axis
  (`redlines.questions.SEVERITY_AXIS`, `DAMAGES_AXIS`), rung ticks and
  historical marks. A mark appears on the ladder(s) it has a figure for: the
  tolls on the deaths ladder, NotPetya ($10B) and COVID-19's output loss
  ($12.5T–$22T) on the damages ladder. Nothing is converted between the two
  any more; the old `max(deaths, damages / VSL)` placement rule is gone.
- **Expected loss rows** (Graph 1, the Timeline's "Statistical lives lost", the
  Policy-levers tab) fold the **deaths ladder only** and are a floor on expected
  deaths (`redlines.conditional.LOSS_LEG`). Until now they read in
  "death-equivalents" at the ladder's VSL; that rate (`USD_PER_DEATH`) and the
  dollar sub-labels on those axes are removed. The damages ladder is not folded.
  Expected-damages rows per cause are a natural follow-up and would reuse the
  same fold over the damages questions.
- **Human baselines**: the workbook's comparison column flags a rung, so both of
  its questions inherit the flag. The LEAP "50 deaths or $100b" number is
  carried on both `ladder:ai:10k` questions (`data/human_baselines.json`,
  re-keyed rather than re-pulled); it is an exact match for neither.

## The prompt

Each incident cause's resolution criteria are printed once under its group
heading rather than under all 17 of its questions. With the per-question form
the joint prompt reached 158 KB; pi takes the prompt as one argument, which
Linux caps at 128 KiB. The shared form is 105 KB. The archived instruments
render under the same template, so their pinned prompt hashes moved with it
(`tests/test_conditional.py`).

## The cutover

The current-instrument views (Graph 1, Graph 2, the data bank, the Policy
levers tab) show no reading until the first run under v11 lands; the Timeline
keeps the cross-cutting questions' earlier readings as legacy points, as at the
2026-09-10 change. The publish gate withholds the rebuilt page until a complete
run exists, so the live site keeps the last good build until then. The paper's
numbers (`paper/numbers.tex`) are a snapshot of the v1 instrument and are
regenerated by hand once v11 has run.

## Open items

- Expected-damages rows per cause (see above).
- Whether the human-baseline comparison should sit on one leg rather than both.
- Cost: the call roughly doubles in delivered probabilities (3,444 → 6,132 per
  call); the cadence conversation Ezra proposed for three weeks out should take
  this into account.
