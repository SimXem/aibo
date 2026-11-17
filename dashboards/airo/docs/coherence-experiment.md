# Joint elicitation and coherence (issue #8)

**Question.** Graph 2 audits a resolution-free constraint: within a cause, P must
not rise as the death threshold rises. About 10% of adjacent rung pairs break it.
Does asking every rung of a cause in ONE call fix that — and if it does, does it
fix the forecasts or merely hide the disagreement?

**Answer.** Joint elicitation removes the violations completely, in two
independent domains. On questions that resolve, it also makes the forecasts
slightly *more* accurate, so it is not buying tidiness at the cost of quality.
Stating the constraint explicitly adds nothing; the shared context does the work.

Run 2026-08-14. Scripts: `archive/litellm-runners/run_ladder_joint.py`, `code/analyze_ladder_joint.py`,
`archive/litellm-runners/run_chain_eval.py`, `code/analyze_chain_eval.py`. Data under
`results/experiments/`.

---

## 1. The violations were noise, not belief

The ladder ran twice under the same protocol before any treatment:

| Run | Coherent ladders | Violating pairs |
|---|---|---|
| 2026-08-05 | 31/57 (54.4%) | 34/333 (10.2%) |
| 2026-08-10 | 32/60 (53.3%) | 34/357 (9.5%) |
| pooled | 63/117 (53.8%) | 68/690 (9.9%) |

The rate is stable. **Which pairs break is not** — only 4 of 34 violating pairs
repeat between the two runs. A model that held an incoherent belief would break
the same pair twice. These do not: they sample each rung in its own call, the
ladder is nearly flat at the top, and independent samples cross over.

Note the unit. Measured per pair the problem reads 10%; measured per **ladder**
(one model, one cause, one horizon) it is 46%, because a ladder has 6 pairs and
one bad rung only breaks two of them. Pairs inside a ladder are not independent,
so the ladder is the honest unit and carries every test below.

## 2. The ladder experiment

Three arms. Control is the two runs above, reused — they agree with each other,
and the budget was better spent on treatment.

- **B** — joint: all 7 rungs of one cause in one call, no instruction about
  monotonicity.
- **C** — joint plus the rule: same, with "P must not increase as the threshold
  rises" added. B and C differ by exactly 222 characters and nothing else.

Rung text is copied verbatim from `data/severity_ladder_questions.json`, so the
elicited quantity is identical to the control.

```
CONTROL — one call per rung
  pooled             coherent ladders  63/117 (53.8%)   violating pairs 68/690 (9.9%)

JOINT — one call per cause
  arm b              coherent ladders  60/60 (100.0%)   violating pairs  0/360 (0.0%)
  arm c              coherent ladders  57/57 (100.0%)   violating pairs  0/342 (0.0%)

  arm b  +46.2 points, Fisher p = 8.6e-13
  arm c  +46.2 points, Fisher p = 2.3e-12
  NOISE FLOOR: the two control runs differ by 1.1 points, p = 1
```

**Zero violations, not fewer.** Arm C gained nothing over arm B because B had
nothing left to gain, so the shared context is doing the work and the explicit
rule is redundant. That matters for reuse: you do not need to *know* the
constraint in advance, only to put the questions in one call.

Joint is also cheaper — 20 calls against 140.

### Is the coherence earned or mechanical?

A model that divides by 3 at each rung is coherent and uninformative. Two tells,
calibrated against a synthetic arm built by applying a constant divisor to real
control data:

| | ties | slope CV |
|---|---|---|
| control | 36/690 | 0.78 |
| arm b | 1/360 | 0.48 |
| arm c | 0/342 | 0.54 |
| *synthetic constant divisor* | *0/357* | *0.00* |

One tie in 360 steps, and the per-step log drop still varies. Not a divisor.

Pinned rungs (≥99%, issue #7): 20 cells control, 21 arm B, 19 arm C. Joint
context neither worsens nor fixes the low-rung wording problem.

### The levels move, but less than they appear to

The summary median shift (1.00 point, against a 0.90-point noise floor) hides
nothing much, because **per-cell noise between the two untreated control runs is
large**: median 0.9 points, 90th percentile 5.5, and a maximum of 20.0 points
(bio ≥1k 2050 moved 20 → 40 with no treatment at all). Only 4 of 84 cells moved
more than that worst noise move under arm B.

An earlier reading of these data claimed the bottom of the ladder falls hard.
It does not survive a sign test (bottom rung: 7 down, 4 up, p = 0.55). What does
survive is a *general* downward shift — arm B moves 52 cells down and 25 up
(p = 0.003), where the two control runs move 33 down and 40 up (p = 0.48).

That drift is consistent with two different stories. Fixing a crossing means
moving one of the two numbers, and if models fix crossings downward the drift is
the signature of a real fix. Thinner search predicts the same drift (see
Limitations). These data cannot separate them.

## 3. Does it help accuracy? The resolvable test

Coherence is cheap to fake — sorting the existing numbers gives 100% and improves
nothing. Catastrophic-risk questions resolve in 2030–2100, so the ladder cannot
settle it. The FreeCiv corpus has the same nested structure and **does** resolve:
every mined target appears at 7 horizons, and "discovered by turn 90" implies
"discovered by turn 130" exactly as "≥1M deaths" implies "≥100k deaths".

The tracked 1–9% tail artifact cannot be used — its band filter truncates every
chain to length 1 or 2. Re-mining 80 games with `--rate-lo 0 --rate-hi 1`
(deterministic, no keys) yields 440 complete 7-horizon chains.

Both arms call the harness's own `build_batch_prompt` and
`parse_batch_probabilities`; that builder already handles one question and many,
so the arms differ in batch composition and nothing else. Every question is
forecast by the same model under both arms, so the comparison is paired.

```
COHERENCE
  sep    coherent chains  25/60  ( 41.7%)   violating pairs  42/360 (11.7%)
  joint  coherent chains  60/60  (100.0%)   violating pairs   0/360 ( 0.0%)

ACCURACY (paired, n=420 cells)
  arm         Brier   mean P
  sep        0.2863    0.617
  joint      0.2565    0.600
  delta     -0.0297   -0.017    (JOINT better)

  BY CHAIN (model x chain = one observation, n=60)
  joint better on 34, worse on 19
  median per-chain Brier delta -0.0073   p = 0.0101
```

All five models improve:

```
  model             Brier sep  Brier joint    delta   coh sep  coh joint
  Fable 5              0.2965       0.2938  -0.0027      4/12      12/12
  GPT-5.5              0.2612       0.2492  -0.0121      5/12      12/12
  Gemini 3.1 Pro       0.2465       0.2382  -0.0082     10/12      12/12
  Grok 4.20            0.2917       0.2692  -0.0225      2/12      12/12
  Opus 4.8             0.3355       0.2323  -0.1032      4/12      12/12
```

Read the chain-level line, not the per-cell one: 7 cells of one chain are not 7
independent facts, and the per-cell test inflates n about sevenfold.

Where does the gain come from? Splitting on whether the separate arm was
incoherent points the right way but cannot localize the mechanism:

```
  SEP was INCOHERENT     n=35  median -0.0154  joint better 23/35  p=0.067
  SEP already coherent   n=25  median +0.0000  joint better 11/25  p=0.071
```

**The corpus already agreed.** `results/eval_full.json` contains 64 nested chains,
and the harness already batches by game — so those chains were forecast jointly.
Frontier models there are at 0 violations (gpt-4o 0/64, gpt-5 0/64, opus-4-8
0/64, fable-5 0/64); the 6.0% overall rate is carried by gpt-3.5-turbo at 40.6%.

## 4. Limitations

1. **Grounding is confounded with batching in the ladder arms.** One search pass
   now covers 7 rungs: about 5 evidence items per call, against roughly 7 per
   rung before. The coherence result is unaffected — internal consistency does
   not depend on evidence volume — but the level shift may be partly thinner
   search rather than shared context. Untested.
2. **Rungs were presented in ascending severity.** The slope CV argues against
   mechanical list-filling but does not rule it out. `run_ladder_joint.py
   --order shuffled` settles it for 20 calls; not yet run.
3. **One joint run per arm**, against two control runs.
4. **The FreeCiv chains were stratified on flip point**, so the sample is
   deliberately unrepresentative (mean outcome 0.548 against a mean class base
   rate 0.591). Absolute Brier and BSS there say nothing about calibration; only
   the paired contrast is interpretable. 12 chains, 4 games, one run.
5. **The accuracy effect is small** — a median of 0.0073 Brier per chain — and
   the mean is carried largely by Opus 4.8.

## 5. Two failure modes batching introduces

**Batching concentrates failure.** Gemini 3.1 Pro searched seven times on
(arm C, AI), then submitted an empty forecast. Under the old protocol a refusal
costs 1 rung; here it cost 7, and arm C lost 21 cells. `run_ladder_joint.py` now
stores `raw_forecasts` when the grid comes back empty, so a refusal is
distinguishable from a schema mismatch. Any rollout needs a retry on an empty or
partial grid.

**Silent truncation on reasoning models.** `fbsim_core.evaluation.models`'s
`MODELS_WITH_EXTENDED_REASONING` stops at `o4-mini`, so any newer reasoning model
draws the non-reasoning token budget, spends it thinking, and is cut off before it
emits the `<<<PROBABILITIES>>>` block. The call returns 200, the parser returns
nothing, and `error` is `None`. GPT-5.5 lost 45 cells this way, and repairing it
moved the chain-level accuracy test from p = 0.14 to p = 0.010.
`run_chain_eval.py` patches the set at import. **`results/eval_full.json` is not
affected** — 100% coverage for all 11 models — but any new batched path is.

## 6. What this licenses

- **Batch nested or logically related questions into one call.** Coherence goes
  to zero violations in two independent domains, and accuracy does not suffer.
- **Do not state the constraint.** Arm C bought nothing over arm B.
- **Retry on an empty or partial grid**, because batching concentrates failure.
- **Fix the reasoning-token allowlist** before any batched rollout.
- **Treat adoption as a re-baseline, not a free fix.** The ladder numbers shift
  downward across the board when you batch.

## 6b. Batching wider again: one call per MODEL

Per-cause batching was the wrong stopping point — it is the unit the experiment
happened to test, not one anything argued for. It leaves the **cross-cause**
relation unbatched: `ai` and `total` are still separate calls, so a specific
cause can exceed "all causes".

Arm `b-all` asks every cause in one call (84 cells) instead of one cause per call
(21 cells):

```
                        within-ladder          cross-cause
  control (separate)    63/117 (53.8%)         14/312 (4.5%)
  arm b   (per cause)   60/60  (100%)           2/315 (0.6%)
  arm b-all (per model) 60/60  (100%)           0/315 (0.0%)
```

Both survivors under arm b were AI extinction above all-cause extinction — a
logical impossibility on the number the paper quotes. Batching wider removes them.

It also relieves issue #7 as a side effect: cells pinned at ≥99% drop from 20
(control) and 21 (arm b) to **13**. A model that sees `nuclear ≥1k` beside
`total ≥1k` stops treating every low rung as near-certain.

Two costs. The slope CV falls to 0.37 — still far from the 0.00 of a constant
divisor, but the flattest we have measured, so it is worth tracking as a standing
metric rather than a one-off check. And the level shift grows: 1.50 points /
0.21 log10 against a 0.90 / 0.08 noise floor.

## 7. Adopted: the unified batch

Everything above is now the production protocol. `code/run_unified.py` asks one
model, one call, every question — 40 questions × 3 horizons = 120 cells, five
calls per run.

Composition is data-driven so the Auto-ARC question swap stays a data change: ladder
rungs come from the ladder spec, XPT questions attach to a cause through
`config.BATCH_CAUSE` (keyed on the question's own category). One question is held
out, `config.UNBATCHED`: #2 is a natural pandemic and nests under no rung of the
bio ladder, so it is forecast in its own call and plotted as before.

The four count questions are asked as P(≥1 qualifying event) — the conversion
`run_forecasts.py` and `redlines/xpt.py` already used — which is what puts them
in the lattice rather than beside it. All questions are asked on 2030/2050/2100;
each row records its original `xpt_horizons` so the human comparison still lines
up where XPT actually asked. The cost is real: P(≥1) discards the count, and
re-eliciting is the only way back to it.

### Result

`code/audit_coherence.py --compare` checks every constraint the question set
implies, on both logs:

```
                                          legacy    unified
  HORIZON  P non-decreasing over time       0.0%       0.0%
  LADDER   P non-increasing over severity   9.5%       0.0%
  CROSS    cause <= all causes              4.5%       0.0%
  BRACKET  XPT question vs its ladder rung 23.3%       1.7%
  SUBSET   narrower question <= broader     3.1%       0.0%
  TOTAL                                     5.9%       0.2%
```

The two survivors are both Fable 5 on #6 Nuclear Extinction (0.015 vs 0.02;
0.06 vs 0.07) and sit within rounding of a wording judgment — this file's
`XPT_RELATIONS` calls #6 broader than the ladder rung because "incidents
involving nuclear weapons" covers accidents without use.

**The retry earned its place on the first production run.** Gemini 3.1 Pro
returned 0 of 40 questions twice before succeeding on the third attempt. Without
it, one model's entire contribution to every panel would have been lost.

### The numbers moved

```
  question                              horizon   legacy  unified   change
  9. Total Catastrophic Risk               2030    1.20%    0.70%    -0.50
  9. Total Catastrophic Risk               2100   13.00%   15.00%    +2.00
  10. Total Extinction Risk                2100    2.50%    5.50%    +3.00
  3. AI Catastrophic Risk                  2100    7.00%    9.00%    +2.00
  4. AI Extinction Risk                    2050    1.20%    0.60%    -0.60
  5. Nuclear Catastrophic Risk             2100    5.50%    4.50%    -1.00
```

The term structure steepened: near-horizon numbers came down, 2100 numbers went
up. Total extinction by 2100 more than doubled.

Treat individual moves with care. This is one run, and §2 measured per-cell
run-to-run noise under the old protocol at up to 20 points with no treatment at
all. What is solid is the coherence, which is a property of the protocol; the
levels are one draw.

The paper draft quotes 0.8–4% by 2030 and 7–15% by 2050 as placeholders. The
unified set puts total catastrophic risk at 0.70% by 2030 and 6.00% by 2050 —
below both quoted ranges.

### What was retired

Every pre-2026-08-14 forecast is retired, not deleted:
`archive/legacy-forecasts/` holds the 419-row log and the one scheduled run, with
a README explaining why they cannot be spliced onto the new series. The Timeline
page consequently starts over at **one snapshot** and stays degenerate until the
weekly job accrues more.

`code/cron_run.sh` now runs the whole set instead of `STABLE_SUBSET`. The subset
existed because a full run cost 205 calls; the unified batch costs 5, which is
cheaper than the old four-question subset and complete.

## 8. What this does not fix

**Coherence is not accuracy.** A perfectly coherent set of forecasts can be
uniformly wrong. §3 is the only evidence here that batching helps accuracy, it
comes from a different domain, and the effect is small.

**The wording gaps are still real.** `XPT_RELATIONS` in
`code/audit_coherence.py` encodes a judgment about which question contains which,
read off the question text. Those judgments are auditable but they are judgments,
and the BRACKET row of the audit is only as good as they are.

**Issue #7 is relieved, not solved.** Pinned rungs fell from 20 cells to 13. The
low-rung wording still reads as near-certain to several models.

**Batching concentrates failure**, and now maximally: one empty submission costs
all 40 questions. The retry (default 2) is the whole mitigation, and it fired on
the first production run. A model that fails all three attempts contributes
nothing to any panel that week.

**The time series restarts.** Timeline has one snapshot and will look degenerate
until several weekly runs accrue. That is the price of retiring a protocol whose
panels contradicted each other 23% of the time.
