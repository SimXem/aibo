# Forecasts retired by the Auto-ARC question swap, 2026-08-18

205 rows, one elicitation date (2026-08-14), five models, 41 questions of the
retired XPT + hand-authored-ladder set.

Retired because the questions were, not because the forecasts were wrong. The
team decided on the 2026-08-17 call that if the question wording changed, the
old forecasts would be thrown out. The wording changed for every question
except two.

## Do not pool these with the new series

Two independent reasons, either sufficient:

1. **Different questions.** Only `9. Total Catastrophic Risk` and
   `3. AI Catastrophic Risk` have a successor, as `catastrophe:general` and
   `catastrophe:ai`. Nothing else in this file maps to anything in the current
   set. Nuclear and extinction left the question set entirely.

2. **Different protocol.** Every row here is tagged `unified-batch-v1`, which
   means it was elicited with a prompt that STATED the coherence constraints —
   "your numbers must respect the logical relations between these questions".
   The current runner states none (`unified-batch-v2`). So the coherence rates
   these rows produce are a report of that instruction, not a measurement of
   the models, and averaging them with v2 rows would launder one into the
   other. `tests/test_coherence.py` prints a warning naming any v1 row it finds
   in the live log.

Even the two surviving questions are not comparable across that boundary.

## Reading them

The question text lives in `archive/legacy-questions/`. `redlines/runlog.py`
does not point here and should not — see `../README.md` for the earlier
retirement, which was made for the same reason one protocol change earlier.
