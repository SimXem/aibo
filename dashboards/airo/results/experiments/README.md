# Prompt ablation — does stating the coherence constraints buy anything?

Run 2026-08-18, both arms on Bridget's Auto-ARC set, five frontier models,
201 cells each, same day, same grounding.

    arm A  constraints-stated-2026-08-18.jsonl   unified-batch-v1   --state-constraints
    arm B  ../forecast_runs_unified.jsonl        unified-batch-v2   the published series

Arm A's constraint text is DERIVED from `data/autoarc_ladder.json`'s
`relations` block (code/run_unified.py::constraint_block), not restored from
the retired v1 prompt — that one named "All causes" and actor/delivery-route
questions this set does not contain, so pasting it back would have measured
prompt confusion instead of the constraint.

## Coherence

    constraint   stated (A)      not stated (B)
    HORIZON        0/830            0/830
    LADDER         0/840            0/840
    CROSS          0/720            4/720
    BRACKET        0/15             3/15
    SUBSET         0/15             0/15
    TOTAL          0/2420  0.00%    7/2420  0.29%

Stating the constraints does eliminate the violations. Every one of arm B's
seven is Grok 4.20; the other four models cohere with nothing stated.

## What it costs, and why we do not state it

The constraint does not merely reorder the numbers. It rewrites them.

    Grok 4.20, catastrophe:ai vs the ladder rung that contains it

      horizon   arm        P(AI catastrophe)   P(AI incident >=100M)
      2030      unstated        6.0%                 2.0%   <- violation
      2030      stated          1.2%                 4.5%
      2050      unstated       20.0%                 9.0%   <- violation
      2050      stated          4.5%                11.0%
      2100      unstated       35.0%                18.0%   <- violation
      2100      stated         10.5%                20.0%

Told the relation, Grok resolves it from BOTH sides, and the larger move is
the catastrophe question falling by a factor of 3.3 at 2100. The coherent
number is not the model's number. A dashboard that stated the constraint
would publish 10.5% and imply it had asked Grok what it believed.

Ensemble medians at 2100 move accordingly:

    catastrophe:general   22.0% -> 20.0%
    catastrophe:ai        15.0% -> 10.5%
    disempowerment        30.0% -> 22.0%
    ladder:misalign:1M    30.0% -> 22.0%

## The limitation, stated plainly

These are two separate calls, so run-to-run variance is confounded with the
constraint effect. Across all 1005 shared cells only 8.1% are identical and
the mean absolute shift is 0.038, but the MEDIAN shift is exactly 0.0000 —
so the bulk of that movement is sampling noise with no systematic direction,
not the constraint pulling everything one way.

What survives the confound is the part that is not noise: arm B's seven
violations are a specific, reproducible ordering failure by one model, and
arm A has none. The Grok bracket cells above move in one direction, together,
by far more than the noise floor.

To separate the two properly, repeat both arms several times and compare the
distributions. That is not done.

## Conclusion

Unchanged from docs/coherence-experiment.md: do not state the constraint.
The earlier ladder experiment found arm C (joint + monotonicity rule) beat
arm B (joint, no rule) by nothing at all. This run finds a difference, but
it is bought by changing the forecast, which is the thing being measured.
