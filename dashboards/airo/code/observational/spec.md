# Conditional-coherence MVP — experiment specification (v3)

Goal: first conditional-forecasting evidence for the ACRF "why we trust
this" page. Test whether LLMs produce conditional probabilities that are
(1) internally coherent, (2) directionally correct in BOTH directions,
(3) responsive to real association and flat on independent pairs, and
(4) improving with model capability. Ezra's bar: better than chance,
with a visible capability gradient.

v2 superseded v1 after red-teaming (horizon-matched ground truth,
balanced direction scoring, runner fixes, pilot gate). v3 supersedes v2
after the v2 PILOT CAUGHT A GROUND-TRUTH ERROR: frontier models correctly
treated hemispheric pairs as conditionally independent given the date,
while our panel phi scored them wrong — panel phi conflates seasonal
covariation (deterministic once the date is known) with anomaly
covariation (the real uncertainty). v3 ground truth is therefore
ANOMALY phi: outcomes residualized per question on a smooth seasonal
model (two harmonics of day-of-year + horizon dummy, linear-probability
fit), then correlated. Under it the metropolitan positives are unchanged
(seasonal removal barely moves them — their co-movement is synoptic),
Reunion/Glorioso "negatives" collapse to ~0 (the models were right), and
Mayotte/Kerguelen pairs retain ~-0.4 with no mechanism we can defend
(14-month panel, winner's-curse selection). By our own rule — never
score models against associations we cannot explain — the negative
class is DEMOTED to an unscored probe.

## Ground truth

27 pairs of ForecastBench DBnomics questions ("will the daily average
temperature at Meteo-France station X be higher on {resolution_date}
than on {forecast_due_date}?"). Anomaly phi computed on cells with
resolution - due <= 35 days across all 33 resolution sets, after
sinusoidal deseasonalization per question; certification by 2000-rep
block bootstrap (block = question set; seasonal fit held fixed across
resamples — CIs are mildly narrow, one more reason point estimates are
screening-grade). Every scored pair carries a mechanism declared before
any model sees it (`mechanism` in pairs_selected.json).

SCORED (21):
- sanity_near_duplicate (1): Nantes/Poitiers, anomaly phi 0.99.
- associated_pos bands (12): both metropolitan France; shared synoptic
  anomalies, strength falls with distance. Anomaly phi +0.40..+0.93 in
  four bands, CI excludes 0 (lowest band ci_lo > 0.05).
- control_independent (8): one aseasonal-tropical (Guyane, Guadeloupe,
  St-Barth), trans-Atlantic (St-Pierre-et-Miquelon x metro), or
  cross-basin side; no shared anomaly driver. |phi| <= 0.10, CI inside
  +/-0.30.

UNSCORED (6):
- hemispheric_probe: metro/N-Atlantic x southern hemisphere. Panel phi
  -0.41..-0.56 (the seasonal see-saw); date-conditional anomaly phi is
  UNDETERMINED on this panel (some pairs ~0, some ~-0.4, mechanism
  unexplained). Model deltas are reported descriptively: a strongly
  negative delta suggests season-blind pattern-matching ("opposite
  hemispheres, so anticorrelated"), a near-zero delta suggests
  date-aware conditioning. The 30-day realized-branch follow-up adds
  real data here. NEVER scored, never on the dashboard as a result.

Dead zone by construction: control point estimates <= 0.10; positives
>= 0.30 with CI excluding zero. Certified-but-inexplicable associations
are excluded from scoring — that rule is what demoted the negatives.

One domain, two scored mechanisms (synoptic distance, cross-basin
independence) plus the probe. The v1 FRED arm died honestly at the
30-day horizon (no CI excluded zero at n = 20); a long-horizon FRED arm
is a natural extension.

A/B roles randomized once (seed 0); each station appears in at most 2
pairs; no phi of any kind is shown to the model.

## Elicitation

One prompt per (pair, model, rep): all four probabilities in a single
context, so cross-prompt sampling noise cannot masquerade as
incoherence. Questions future-dated at run time (due = run date, res =
+30 days) — kills outcome recall and makes every pair realized-branch
scorable ~30 days later. No tools, no grounding, vendor-default
reasoning settings ("models as deployed"; note haiku runs without
thinking, the 5-family thinks adaptively — the gradient includes that).
Prompt text is verbatim in run_bench.py.

## Models, reps, cost

MODELS: claude-haiku-4-5, claude-sonnet-5, claude-opus-5,
claude-fable-5 (swap in the ACRF dashboard's five-model set for
continuity — decide with Ezra). K = 5. 27 x 4 x 5 = 540 calls. Thinking
tokens are billed: budget $20-50. Batch API halves it if wall-clock
does not matter.

## Pilot gate (mandatory)

`python3 run_bench.py pilot` runs 3 pairs (one positive, one negative,
one control) x all models, K = 1, and dumps raw responses to
pilot_raw.txt. A human reads every pilot response for prompt
misunderstanding before the full run. No full run without this.

## Metrics (per model; per-response values, median over reps per pair)

- M1 coherence: eps = |p_b - (p_b_given_a*p_a + p_b_given_not_a*(1-p_a))|.
  Necessary, not sufficient — a model can enforce the identity
  arithmetically within one prompt. Kept as the two-years-ago reference
  point; M2-M4 score against held-out ground truth and are not gameable
  this way.
- M2 direction: sign(p_b_given_a - p_b_given_not_a) on the 13
  positive-class pairs (sanity included); exact binomial vs 0.5. The
  all-positive prior aces this — which is why M3 is jointly required:
  the pass bar is the conjunction.
- M3 independence: median |p_b_given_a - p_b_given_not_a| on controls.
  PRE-REGISTERED PASS: < 0.075 (set pre-run: elicitation noise and
  benign judgment deltas graze 0.05; the all-positive prior fails at
  ~0.4 either way). With no scored negative class, this is
  THE guard against the "everything correlates" prior. Catches invented
  associations (and
  demand-characteristic inflation, which pairing questions in one
  prompt invites).
- M4 rank tracking: implied phi vs anomaly phi, Spearman, over the 21
  SCORED pairs only (the probe has no ground truth). RANK EVIDENCE
  ONLY — implied magnitudes are demand-inflated; permutation p is
  anticonservative (pairs share stations). This scatter, one panel per
  model, is the dashboard graph.
- Probe report: median delta per hemispheric pair per model, printed
  descriptively, excluded from every pass criterion.

## Pre-registered pass criteria

Top model: M2 exact binomial p < 0.05, M3 PASS (< 0.075), M4
rho_scored > 0 with perm p < 0.05. Gradient: rho_scored non-decreasing
on >= 3 of 4 adjacent tier steps. Any failure => report it and keep
conditional forecasts OFF the pilot dashboard.

## Caveats for any writeup

- Observational, not causal. Right-shaped for red-lines (P(damage |
  eval score) is also observational); causal conditionals arrive with
  StarSim in the FBSim paper.
- One data family (Meteo-France temperature), three mechanisms
  (synoptic distance / anti-phase seasons / tropical aseasonality).
  Claim "on this domain," not "in general." The FRED near-null is
  itself worth one sentence: short-horizon econ association is thin.
- Stationarity: phi from 2024-2026 short-horizon cells, tested on a
  future September window. Spatial and hemispheric structure is as
  stationary as weather gets; the seasonal-transition window is noted.
- Effective n < nominal n (cells share sets/horizons); CIs are
  block-bootstrapped but phi point estimates remain screening-grade.

## Realized-branch follow-up: dropped

Decision (Nick, 2026-08-20): no 30-day realized-branch scoring pass —
ForecastBench already elicits and scores these questions on an ongoing
basis (marginals; conditional realized-branch scoring stays possible
from results.jsonl if ever wanted, since forecasts are date-stamped).

## Files

- pairs_selected.json — 27 pairs (texts, stations, regions, phi, CI, mechanism)
- run_bench.py        — pilot + full runner (resumable)
- score_bench.py      — M1-M4, pass bar, dashboard scatter data
- mine_short.py, mine_anomaly.py, mine_anomaly2.py, select_pairs_v4.py —
  provenance (short-horizon panel, bin then sinusoidal deseasonalization,
  bootstrap, mechanism screens); earlier mine/select versions kept for
  the record
