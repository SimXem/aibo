# StarSim causal bench — design log

Decision record for `starsim_causal/`. The README describes *what* the current
design is; this file records *why*, what was tried, and what is planned. Newest
at the bottom. Dates are decision dates.

## Aim

Two questions, asked of every model on the ECI-ranked roster (24 models,
`../data/model_scores.csv`):

- **(a) Baseline** — how well does a model forecast an epidemic with *no*
  intervention, given known parameters and an observed trajectory?
- **(b) Intervention** — given the *same* epidemic, how well does it reason
  about the causal effect of an intervention?

The deliverable is a capability gradient: score vs ECI (and vs ForecastBench
overall) for each of (a) and (b), plus how much of the certified causal
effect each model moves.

## Non-negotiables (hold across every version)

1. **No deaths.** Infections only. Mortality adds a second outcome and a
   second causal pathway for no gain. (`run_region(..., p_death=0)`.)
2. **Same items in (a) and (b).** An item is a world × question/horizon. Each
   item is asked twice; the two prompts differ *only* by one appended
   intervention paragraph. Never mine the two conditions separately.
3. **Separate prompts.** A model never sees baseline and intervention in one
   context; each prompt elicits one probability.
4. **Parameters stated.** The world report gives the simulator's parameters
   (population, contacts/day, infectious period, per-region transmission
   probability and R₀, day-0 seeds) and the observed trajectory through day
   20. The task is calibration on simulator output, not epidemiology trivia.
5. **Baseline stays easy.** Difficulty is added on the intervention side
   only, so (a) remains a clean control for (b).
6. **Ground truth conditioned on what was shown.** P* comes from seeds whose
   day-20 counts match the displayed run (±15%), crossed as (R, S) pairs,
   with bootstrap CIs; items are certified, not assumed.

## v1 — 2026-08-20 (frozen in `v1/`, code at tag `v1-run`)

Two independently mined item classes: `easy_baseline` (8 items: yes/no ×
cases/deaths × day 40/60) and `sanity` (4 items: vaccinated region × horizon,
cases only), with p_base and p_int elicited in **one** prompt. Deaths on
(p_death = 0.02).

**Why it was dropped (2026-08-27).** The two classes were mined separately,
so the intervention items were not the baseline items plus a vaccine — 8 vs 4
items with no correspondence. Joint elicitation also let a model anchor its
intervention forecast on its own baseline number in-context. Both violate
non-negotiables 2–3; deaths violate 1. Results kept for the record only.

## v2 — 2026-08-27 (current; `mine_worlds.py`, `worlds.json`)

- **World** = one simulated configuration + its report. Two isolated SIR
  populations (Riverton, Southbay), 5,000 agents each, RandomNet 6
  contacts/day, 10-day infectious period, init_prev 0.5%, no deaths.
  Per-region transmission probability ∈ {0.03, 0.04, 0.05, 0.065}
  (R₀ ≈ 1.8 / 2.4 / 3.0 / 3.9). The displayed run per β is the control seed
  closest to the median day-20 ever-infected count.
- **Item** = world × horizon. 4 worlds × {day 40, day 60} = 8 items, question
  "Will Riverton have more cumulative infections than Southbay at day t?"
  Two Riverton-leading worlds, two Southbay-leading (one a mirror of another
  as a sign-balance control).
- **Intervention** = the leading region vaccinates on day 21 (the day after
  the report ends): 90% coverage, 95% efficacy, leaky (`ss.simple_vx` +
  `ss.campaign_vx`). Chosen to be unambiguous: it flips every item.
- **Certification**: full flip at both horizons, CI half-width ≤ 0.03,
  ≥ 50 matched seeds per region per arm. All 8 items certified at exactly
  P* ∈ {0, 1}, Δ_do = ±1.
- **Elicitation**: OpenRouter, vendor-default sampling, K = 5 reps, per-item
  medians. Output cap min(64k, max(catalog cap, 16k)) after the pilot showed
  reasoning models truncating at 16k.
- **Scores**: `recovered` = 1 − Σ(p̂−P*)²/Σ(½−P*)² per condition (share of the
  recoverable Brier score; 0 = always ½); `effect_recovered` = mean
  (p̂_int − p̂_base)/Δ_do with p̂_base from the model's own baseline prompt.

### v2 result — saturation (run of 2026-08-27, 1,863/1,920 cells, ~$48)

- Baseline: 19/24 models ≥ 0.98 recovered; below the ceiling only Haiku 4.5
  (0.95), DeepSeek V3 (0.93), Kimi K2 (0.91), Llama 4 Scout (0.78).
  Spearman vs ECI ρ = +0.67 (p < .001).
- Intervention `effect_recovered`: ρ = +0.66 vs ECI, +0.67 vs FB overall.
  But the top tier is compressed at the ceiling: gpt-5.6-sol 1.00, gpt-5.5
  0.99, deepseek-v4-flash 0.98, gpt-5.6-luna 0.97, gpt-5 0.96, gpt-5-mini
  0.96, o4-mini 0.96, gemini-3.7-flash 0.96 … fable-5 0.94, opus-5 0.94.
  Failures are all in the bottom half (gpt-5.4-nano 0.14, llama 0.27,
  haiku 0.43, gpt-4.1 0.51, kimi 0.55).
- deepseek-v4-flash has all 8 items but only 23/80 reps: its default
  reasoning runs 10–55k tokens per call and the provider stalls. Left partial.

**Diagnosis.** 90% × 95% leaky protection cuts transmission ~85%, so
R_eff = R₀·(1 − 0.855) ≈ 0.3–0.6 for every β we use. The leader's epidemic
stops on day 21, the follower keeps growing, and the flip is certain by day
40. The causal task reduces to a *sign* question with an overwhelming cause;
the heuristic "vaccine → fewer infections → flip" is sufficient, and every
model above ECI ≈ 147 has it. The gradient we see is a floor effect among
weak models, not a ceiling among strong ones.

## v3 — decided 2026-08-27: a coverage (dose) ladder

### Levers considered

All without deaths. Today the runner exposes efficacy, coverage, day, target
region and the β pair; anything else is a small custom `ss.Intervention`.

| Lever | What it forces the model to do | Verdict |
|---|---|---|
| **Dose** (coverage × efficacy → R_eff) | Marginal doses: does the leader *still* get overtaken? Needs R_eff and susceptible depletion from the stated parameters. Sub-threshold doses don't flip. | **Chosen.** |
| Horizon (question day near the crossing) | Cumulative counts are monotone; locate *when* the follower overtakes. | Runner-up. Tests timing/dynamics rather than effect size; every new horizon needs new baseline prompts. Reserved as a later lever. |
| Timing (`vax_day` after the peak) | Recognize "too late to matter". | Boundary is pinned to the epidemic peak → nonlinear, world-dependent. Not a clean scalar. |
| Target (trailer / both regions) | Counts change, ranking doesn't (Δ_do = 0). | Useful placebo class, but binary, not a ladder. Possible add-on. |
| Mechanism (transient NPI, isolation) | Delay-not-avert rebound; flips at day 40, un-flips by day 90. | Needs new sim code and a new concept in the report. Later. |
| β gap between regions | Wide gap + moderate dose → no flip. | Interacts with dose; it is what makes the boundary world-specific. Kept fixed. |
| Threshold questions ("> 3,000 by day 60?") | Effect *size*, not sign; road to quantile/CRPS elicitation. | Right *next* redesign after dose, not the first. |
| Smaller population, targeted vaccination, per-region dur_inf/contacts | — | Rejected: extinction noise (not reasoning), RandomNet makes targeting moot, R₀ in disguise. |

### The choice

Vary **only vaccine coverage** *c*. Everything else identical to v2: same
four worlds and reports, same question, day-60 horizon, leader vaccinated on
day 21, 95% leaky efficacy.

Why this is the best and cleanest lever:

1. It is the strength of the `do()` itself, and it is one number in one
   sentence of the intervention paragraph; nothing else in the prompt moves.
2. Monotone: R_eff = R₀·(1 − 0.95·c). The certified truth moves from flip
   (c = 90%) to no-flip (c ≈ 10–20%) through a world-specific boundary *c\**;
   difficulty is the distance from *c\**.
3. The v2 heuristic is right on the first rung and wrong on the last, and in
   between requires the computation we want to test.
4. Free dose–response check: within a world, Δp̂ should be monotone in *c*
   (Spearman of Δp̂ vs Δ_do across rungs) — a standard causal-validity test
   that no other lever yields.
5. Reuses v2 entirely: baseline items and results unchanged; the v2
   intervention run *is* the c = 90% rung. `vax_coverage` already exists; zero
   sim code.

### Definitions

- **Rung / level** is defined in *outcome* space, not knob space: the
  **margin** at day 60 = (follower − leader cumulative infections) / population
  under the intervention, across matched seeds. Per world, choose the coverages
  that produce target margins, e.g. +30%, +10%, +3%, −3%, −10% (positive =
  flipped). "Level k" then means the same thing in every world, and finer
  rungs near *c\** can be added later without changing the design.
- **Certification** per rung as in v2: P* ∈ {0, 1} within 0.03 (CI half-width
  ≤ 0.03, ≥ 50 matched seeds/region/arm). We never sit on the boundary, so the
  ceiling stays full and an item is still "gets it or doesn't". If the
  stochastic transition in *c* is too wide to place a ±3% rung, options are
  more seeds (CI) or a larger population (sharper transition); the latter
  changes the reports and is a separate decision.
- **Scoring**: `recovered` per condition unchanged. Because no-flip rungs have
  Δ_do = 0, `effect_recovered` (÷Δ_do) is replaced by a normalized effect
  error, 1 − Σ(Δp̂ − Δ_do)²/Σ(Δ_do_ref)², plus per-world dose–response
  monotonicity. Report per-rung `intervention_recovered` vs ECI as the
  difficulty ladder.
- **Efficacy stays fixed at 95%**: with a leaky vaccine only the product
  c·e matters to first order, and "x% of the population vaccinated" is the
  more legible number.

### Plan

1. `mine_dose.py`: for each of the 4 v2 worlds, run the leader with
   c ∈ {0.1, …, 0.9} × ~300 matched seeds (~11k sims, cached; no API spend).
   Locate *c\** per world, read off rung coverages at the target margins,
   certify, write `worlds_v3.json` (v2 worlds + a `rungs` list per world).
2. Prompts: v2 template unchanged; `intervention_text(leader, coverage)`.
3. Run only the new intervention prompts (baseline reused from v2); K = 3–5.
   Rough size: 4 worlds × ~5 rungs × 24 models × K = 3 ≈ 1,440 calls, ~$35.
4. Score, chart per-rung ladders vs ECI, update this log with the result.

### Rung 2 — `hold` (mined and chosen 2026-08-27)

`mine_dose.py` simulated the leader at coverage 5–85% (5-point grid) on the
v2 matched seeds (11,033 sims, `.sim_cache_dose.json`). Day-60 margin =
(follower − leader)/N; a coverage is certified only if *both* horizons are
certified and agree.

| world (R₀ leader vs follower) | no-flip certified up to | flip certified from | day-60 boundary | day-40 boundary |
|---|---|---|---|---|
| w0 / w3 (2.4 vs 1.8) | 20% (margin −3.9%) | 70% | ≈ 25% | ≈ 55% |
| w1 (3.0 vs 2.4) | 10% (−2.2%) | 35% | ≈ 15% | ≈ 22% |
| w2 (3.9 vs 3.0) | 15% (−1.9%) | 50% | ≈ 28% | ≈ 30% |

Two things the grid shows. (1) Sensitivity to coverage is world-specific:
in w2 both regions approach saturation, so a 20% campaign already swaps the
ranking, whereas w0 needs ~25%. Rungs therefore have to be chosen per world
(outcome space), as planned. (2) The day-40 and day-60 boundaries differ —
between them (w0: 25–65%) the day-60 item flips while the day-40 item does
not. That band is where a future *crossing-time* rung lives; it is excluded
from rung 2 by the both-horizons rule.

**Choice: the largest certified campaign that does not change the answer**
(`--select --target-margin -0.0 --tag hold` → `worlds_hold.json`):
w0 20%, w1 10%, w2 15%, w3 20%. Day-60 P*_int = 0.970 / 0.978 / 0.009 / 0.029
(same side as baseline; CI half-widths ≤ 0.015), day-40 P*_int ≈ 0/1 exactly.
Δ_do ∈ [−0.03, +0.03].

Why a no-flip rung rather than the closest certified *flip* rung (70%): on
any flip rung the v2 heuristic "vaccine → fewer infections → flip" is still
correct, so it cannot separate reasoning from pattern-matching; on `hold` the
heuristic is wrong and only a magnitude computation (R_eff ≈ 0.9·R₀ plus how
much of the leader's lead survives to day 60) gets it right. The converse
failure — ignoring the intervention entirely — scores perfectly on `hold` but
is caught by rung 1 (90%). **Rung scores must be read jointly**: a model
reasons causally only if it flips at 90% *and* holds at 10–20%.

Run: `run.py --tag hold --worlds starsim_causal/worlds_hold.json` (intervention
prompts only, 8 × 24 × K=5 = 960 calls; baseline reused from
`results/baseline.jsonl`); `score.py --tag hold --worlds …`;
`chart.py --tag hold --worlds …` → `results/eci_vs_recovered_hold.png`.
`effect_recovered` generalizes to 1 − |Δp̂ − Δ_do| (identical to Δp̂/Δ_do on
±1 items; on `hold` items 1 = held, 0 = flipped anyway).

### Rung 2 result (run of 2026-08-27; 930/960 cells, $38)

All 23 non-deepseek models complete at K = 5; deepseek-v4-flash 10/40 reps
(same stall as v2). Scores in `results/scores_summary_hold.json`, chart
`results/eci_vs_recovered_hold.png`, joint table `results/ladder.csv` and
joint chart `results/ladder.png` (`ladder_chart.py`).

- **The rung de-saturates the top tier.** `intervention_recovered` on `hold`:
  gpt-5.6-sol 0.998, gemini-3.7-flash 0.997, gemini-3-flash 0.982, gpt-5 0.968,
  gpt-5.6-luna 0.963, opus-5 0.938, sonnet-5 0.934, fable-5 0.934,
  deepseek-v4-flash 0.910, gpt-5.5 0.858. Flipping anyway (heuristic):
  o4-mini −0.77, gemini-2.5-flash −0.30, deepseek-v3 0.08, qwen3.5-flash 0.15,
  o3 0.45, gpt-5-mini 0.63. Alone, ρ = +0.50 vs ECI (`intervention_recovered`),
  +0.45 (`effect_recovered`).
- **Rung 2 alone rewards ignoring the intervention**, exactly as predicted:
  gpt-4.1 0.985, gpt-5.4-nano 0.968, gemini-3.1-flash-lite 0.992, haiku 0.895,
  llama 0.729 — all of which scored ≤ 0.79 on rung 1.
- **Joint reading = min(effect@90%, effect@hold) per model: ρ = +0.76 vs ECI
  (p < .001)**, stronger than either rung alone (+0.66, +0.45). Ranking:
  gpt-5.6-sol 0.98, gemini-3.7-flash 0.96, gpt-5 0.95, deepseek-v4-flash 0.94
  (partial), gemini-3-flash 0.94, opus-5 0.94, gpt-5.6-luna 0.93, fable-5 0.92,
  gpt-5.5 0.90, sonnet-5 0.88, gpt-5-mini 0.84, gpt-5-nano 0.82,
  gemini-3.1-flash-lite 0.79, o3 0.75, qwen3.5-flash 0.72, qwen3-235b 0.70,
  deepseek-v3 0.70, gemini-2.5-flash 0.63, kimi-k2 0.55, gpt-4.1 0.51,
  o4-mini 0.46, haiku 0.43, llama 0.27, gpt-5.4-nano 0.14.
  Two failure modes dissociate cleanly: *ignorers* (gpt-4.1, gpt-5.4-nano,
  haiku, llama, gemini-3.1-flash-lite) and *over-flippers* (o4-mini,
  gemini-2.5-flash, qwen3.5-flash, deepseek-v3, o3, gpt-5-mini).
- Rep variance is high on this rung: at K ≈ 2 the interim table had
  gpt-5.6-luna at 0.16 and o4-mini at −0.25; K = 5 medians moved them to 0.96
  and −0.77. Treat K = 5 as the minimum for sub-threshold rungs.
- Reasoning models think ~2× longer than on rung 1 (throughput 24/min vs 49).

Next rungs, in order of value: a *crossing* rung (coverage in the band where
day 60 flips but day 40 does not, e.g. w0 at 40%), a second flip rung near the
boundary (w0/w3 70%, w1 35%, w2 50%) to test calibration on the flip side, and
finishing deepseek-v4-flash with `--reasoning low`.

## v4 — decided 2026-08-28: single region, continuous forecast (`starsim_single/`)

**Why the two-region binary design was retired.** Its item is a *sign*
("more in Riverton than Southbay?"), so a heuristic gets it free: on a flip
rung "always flip" is correct, on a no-flip rung "always ignore" is correct.
Rung 2 showed this directly — low-ECI ignorers on the ceiling, mid-ECI
over-reactors at the bottom, ρ vs ECI *down* from +0.65 to +0.50. Difficulty
could only be added by hunting boundaries (dose, crossing), and each rung
needed a null-strategy complement to be interpretable. The scoring rule that
combined rungs (min over rungs) had no precedent in the forecasting
literature and was hard to explain. Rejected.

**Design.**
- One region (Riverton), 5,000 agents, stated parameters, report through day
  20 as before. Four worlds = the four v2 betas (R₀ 1.8 / 2.4 / 3.0 / 3.9).
- Target: **new infections between the end of day 20 and day t**
  (t = 40, 60) — cumulative minus the day-20 count the report states, so the
  vaccine's effect is not diluted by infections that already happened. Chosen
  over active infections because it needs only spread dynamics (R₀ +
  depletion), not the recovery clock; peak active infections is the reserved
  harder target.
- Forecast: quantiles p10/p25/p50/p75/p90 (fbsim's convention). Baseline and
  intervention in separate prompts, identical except the intervention
  paragraph (vaccination day 21, 95% efficacy, coverage c).
- Truth: the distribution over matched seeds (±15% at day 20), per arm.
- Score: CRPS (quantile pinball, `fbsim_core.metrics.compute_crps`) averaged
  over the truth samples, as a skill score: 1 − (CRPS − CRPS_oracle) /
  (CRPS_uniform − CRPS_oracle), oracle = truth quantiles, uniform on
  [0, N − c20]. Same "share of recoverable score" reading as before.
  `effect_recovered` = model's median shift ÷ certified median shift.
- No free strategy: ignoring the vaccine reproduces the baseline distribution
  and scores badly under intervention; over-reacting scores badly by
  magnitude. Coverage is a continuous dial with no boundary to certify.

**First run 2026-08-28:** c = 90%, 8 items × 2 conditions × 24 models × K = 3.
Certified effects (median new infections, baseline → vaccinated): w0 1568→51
(d40), 2780→51 (d60); w1 2854→162, 3135→163; w2 2270→245, 2304→246;
w3 850→134, 851→134. Pilot: 96/96 parsed, no retries.

**Scoring reference (settled 2026-08-28 after three tries).** (1) Uniform on
[0, N − c20]: too weak, everything ≈ 0.9. (2) Per-condition climatology:
too strong on the vaccinated arm (all worlds collapse to 50–250 new
infections), everything ≪ 0. (3) Persistence (no-vaccine distribution) for
the intervention: made B look better than A because the references differed.
Final: **one fixed climatology** for every condition and rung — the pooled
target distribution over all worlds × coverages {0, 25, 50, 75, 90}% at that
horizon (`starsim_single/climatology.json`). Knows the simulator and the
question, not the world or the coverage. A and B are then on the same scale
and the baseline score is rung-independent.

**Results (2026-08-28, K = 3, 24 models; deepseek-v4-flash partial).**

| rung | intervention ρ vs ECI | effect ρ | top of B |
|---|---|---|---|
| 90% coverage | +0.41 | +0.50 | sol .99, gpt-5.5 .98, luna .95, deepseek-v4 .94, opus .92 |
| 50% coverage | **+0.70** | +0.33 | sol .84, gpt-5.5 .83, luna .78, opus .78, sonnet .72, fable .71 |

Baseline (same in both): ρ = +0.26; top models 0.72–0.92, weak tail llama
−0.7, deepseek-v3 0.15, gpt-5.4-nano 0.5, haiku 0.6. The wide fixed
climatology compresses the top of the baseline; it still separates the tail.

Reading: at 90% the effect is recognizable ("the epidemic stops") and B is
near the ceiling for anyone who reads the vaccine paragraph; at 50% the
effect must be computed (R_eff halves, epidemic continues at 49–84% of
baseline depending on R₀) and B orders by capability. Failure modes at 50%:
over-correction (gpt-5-nano −0.25, o4-mini −0.23, deepseek-v3 −0.4) and
under-correction (gemini-3.7-flash 0.41 despite 0.87 on baseline).
`effect_recovered` (median shift ÷ certified shift) is ≈ 1.0 for most models
at both rungs and is the less discriminating number; the CRPS skill on the
vaccinated arm is the headline.

No free strategy on this design: ignoring the vaccine scores the baseline
distribution against the vaccinated one (large CRPS); over-reacting scores by
magnitude. The single coverage knob is the difficulty dial; 50% is the operating point (see table).

Files: `starsim_single/{mine_single,qprompts,run,score,chart,climatology,effect_sizes}.py`,
`worlds{,_c50,_c25}.json`, `results/{baseline,intervention[_cXX]}.jsonl`,
`results/eci_vs_recovered[_cXX].png`.

### Open items

- deepseek-v4-flash reps (23/80 in v2): finish with `--reasoning low`, or
  footnote. Applies equally to v3.
- fbsim dependency: `pandemic_world.runner.run_region(p_death=)` was added
  2026-08-27 on `refactor/monorepo` and must be committed there.
