# Can the models forecast conditionals? — Graphs 5 and 6

The dashboard's conditional forecasts (the Policy levers and Capability tabs)
ask a model what a policy or a capability level would do to a risk. Nothing on
those tabs resolves, so nothing there can be scored. The two charts under "Why
trust this?" added on 2026-08-28 are the evidence that the models can do the
*kind* of reasoning those tabs rely on — moving a probability by the right
amount when told to suppose something — on questions where the right amount is
known.

Both charts put the same models on the same x-axis (the Epoch Capabilities
Index) — the causal bench's 24-model roster, plus on Graph 5 the eight other
models of Graph 4's ladder — and draw the dashboard's own panel in the accent
colour.
Both were built elsewhere and **vendored in whole** — code, inputs, and every
raw model reply — so the dashboard's copy can be regenerated, audited, or
re-run without the original repositories.

| | Graph 5 — observational | Graph 6 — causal |
|---|---|---|
| Question | Told "suppose A happened", does the model move P(B) in the right direction, by an amount that tracks how associated A and B really are? | Told a vaccination campaign will happen, does the model's forecast move the way the simulator's does? |
| Ground truth | Association measured in two years of ForecastBench resolution data | The simulator's own distribution over seeds |
| Domain | Météo-France station temperatures, 30-day horizon | One StarSim SIR population, 5,000 agents, parameters stated |
| Score | Rank ρ, implied vs measured association, 21 pairs | CRPS skill vs climatology, pooled over three coverage rungs |
| Headline | ρ = +0.78 vs ECI over 32 models; the frontier sits at +0.84–0.88 against a noise ceiling of 0.94 | ρ = +0.68 vs ECI (p = 0.0003, n = 23); no gradient without the intervention (ρ = +0.27) |
| Where | `code/observational/`, `data/observational/`, `results/observational/` | `archive/causal/`, `data/causal/` |
| View | `redlines/views/observational.py` → `results/observational_data.json` | `redlines/views/causal.py` → `results/causal_data.json` |
| Page | `web/demo/45-conditional-benches.jsx` (`ObservationalPanel`, `CausalPanel`) | same |

## One roster, one ECI vintage

`data/causal/models.csv` is the roster: 24 models, all reachable through
OpenRouter, with the ECI Epoch published on 2026-08-27. `redlines/roster.py`
reads it and is the only place the two views get a model's ECI, label, colour
and panel membership from. It is a **third ECI vintage** next to the two
`redlines/eci.py` manages (2026-07-07 pinned for Graph 4; the newest snapshot
for the panel). The roster's values are part of the causal bench's locked
dataset — recomputing them from a later snapshot would move a published
headline — and the newest Epoch snapshot is a leaderboard top-17 that does not
reach the roster's weaker models anyway. The differences are fractions of a
point (Fable 5: 162.49 vs 162) and the charts say which vintage they use.

Labels are the registry's where the model is in `redlines/registry.py`
(so "Fable 5" reads the same on every chart), else the OpenRouter display name
without its vendor prefix. `inPanel` is matched on the OpenRouter id against
the panel's litellm ids; of the current panel, GPT-5.5 Pro is not on the roster
(not on OpenRouter), so three of four panel members are drawn in colour.

## Graph 5 — the observational bench

Vendored 2026-08-28 from `elsehow/llm-conditional-forecasting` (commit in
`code/observational/UPSTREAM-COMMIT`). The pre-registered design is
`code/observational/spec.md` (v3); read it before changing anything scored.

**Instrument.** 27 pairs of ForecastBench DBnomics questions, "will the daily
average temperature at station X be higher on {resolution date} than on
{forecast date}?" — future-dated at run time (due = run date, resolves +30
days), so nothing can be recalled. One prompt per (pair, model, rep) elicits
P(A), P(B), P(B|A), P(B|¬A) together, so cross-prompt sampling noise cannot
masquerade as incoherence. No tools, no system prompt, vendor-default
reasoning. K = 5.

**Ground truth.** Anomaly phi: outcomes residualized per question on a smooth
seasonal model, then correlated, over 33 resolution sets (2024–2026), with a
2,000-rep block bootstrap. 21 scored pairs — one near-duplicate (Nantes ×
Poitiers, φ 0.99), twelve metropolitan positives in four bands (φ +0.40 to
+0.93; shared synoptic anomalies, strength falling with distance), eight
independent controls (|φ| ≤ 0.10; a tropical, trans-Atlantic, or cross-basin
side). Six opposite-hemisphere probe pairs are **never scored**: the pilot
caught our first ground truth conflating seasonal see-saw with anomaly
covariation, and the models were right. Every scored pair carries a mechanism
declared before any model saw it.

**Metrics** (`redlines/views/observational.py`, matching
`code/observational/score_bench.py` to the printed digit):

- M1 coherence — median |P(B) − P(B|A)P(A) − P(B|¬A)(1−P(A))|. Necessary, not
  sufficient: enforceable arithmetically within one prompt.
- M2 direction — sign of P(B|A) − P(B|¬A) on the 13 associated pairs, exact
  binomial. An "everything correlates" prior aces this, which is why:
- M3 independence — median |P(B|A) − P(B|¬A)| on the 8 controls; the
  pre-registered **bar is 0.075**. The guard against invented associations.
- M4 rank tracking — Spearman ρ between implied phi (from the four
  probabilities) and measured phi over the 21 scored pairs. Rank evidence
  only: implied magnitudes are demand-inflated. **This is the chart.**

**Noise ceiling** (`data/observational/noise_ceiling.json`,
`code/observational/noise_ceiling.py`): an oracle answering the point-estimate
phis, scored against 1,000 block-bootstrap re-measurements of the panel,
scores ρ = 0.94 [0.89–0.98]; split-half reliability 0.83 is the pessimistic
cousin. No forecaster can be expected to beat it; the chart shades the band.

**Runs.**

- `results/observational/results_2026-08-20.jsonl` — the upstream run: four
  Claude models (Haiku 4.5, Sonnet 5, Opus 5, Fable 5) through the Anthropic
  SDK, 540/540 responses. Every metric improved monotonically with capability
  and Fable 5 met the pre-registered pass bar (Haiku 4.5 failed M3 at 0.100).
  `tests/test_conditional_benches.py` pins the view to this run's published
  table. The report built on it is `code/observational/report-2026-08-20.html`.
- `results/observational/results_roster.jsonl` + `results_roster_g4.jsonl` —
  the roster run of 2026-08-28: the same instrument on the 24 causal-roster
  models (3,240 calls, ~$45) and, in a second file, the eight other models on
  Graph 4's ladder (`data/observational/roster_extra.csv`; 1,080 calls, ~$11),
  all through OpenRouter (`archive/litellm-runners/run_roster.py`; pilots in
  `results_roster*_pilot.jsonl` / `pilot_raw_roster*.txt`, read before each
  full run as the spec requires). 4,320/4,320 replies, none given up. The
  view draws this run — a model only once it has all 5 replies to every
  pair — and the 2026-08-20 run is the fallback.

  **Result (32 models):** rank ρ runs from +0.23 (Llama-3.3-70B) and +0.36
  (GPT-3.5, which answers 0.5 to everything) to +0.90 (DeepSeek V4 Flash),
  with the frontier bunched at +0.84–0.88; capability ↔ skill ρ = +0.78
  (p < 0.0001). 24 of 32 clear the pre-registered control bar; the failures
  are mostly the weak end (Llama 4 Scout 0.20, Llama-3.3 0.135, GPT-5 Nano,
  GPT-5.4 Nano) plus a few that sit exactly on 0.075 (GPT-4.1, Haiku 4.5, o3).
  The panel: Sol +0.87, Opus 5 +0.87, Fable 5 +0.86, all passing. Fable 5
  scored +0.88 on the 2026-08-20 Anthropic-SDK run; the difference is one
  rank swap among 21 pairs.

The view's `rho` is the gradient — Spearman between ECI and each model's M4 —
with a t-approximation p-value (`redlines.stats.spearman_p`). Models are not
independent samples; read it as descriptive.

## Graph 6 — the causal bench

`data/causal/` is the **locked dataset** of 2026-08-28 from the
ForecastBench-Sim ICLR work (an internal FRI checkout, `iclr-2026`, not
published; its `results/causal/data` at tag `causal-v4-locked`; commits in
`archive/causal/UPSTREAM-COMMIT`). Its
`MANIFEST.sha256` verifies in place — `tests/test_conditional_benches.py`
checks it — and it is never regenerated into: a new run is a new directory.
The generating code is frozen under `archive/causal/` (`starsim_single/` is the
v4 design that produced the dataset; `starsim_causal/` the runner, client and
roster it builds on; `DESIGN.md` the record of v1–v3 and why each was
retired). It depends on `forecastbench-sim` (`pandemic_world`, `fbsim_core`)
and is a record here, not a runnable path.

**Design** (`data/causal/README.md`). One SIR population (starsim 3.3.4),
5,000 agents, ~6 contacts/day, 10-day infectious period, no deaths. Four
worlds = transmission probability {0.030, 0.040, 0.050, 0.065} (R₀ ≈ 1.8 /
2.4 / 3.0 / 3.9). The report states the parameters and the displayed run's
cumulative infections every five days through day 20. Item = world × horizon
(day 40, day 60); target = new infections after day 20, as p10/p25/p50/p75/p90.
Two conditions in **separate prompts** — a model never sees baseline and
intervention together: baseline, and a day-21 vaccination campaign (95%
efficacy) at 25, 50 or 90% coverage. Truth = the distribution over simulator
seeds whose day-20 count is within ±15% of the displayed run. Score = CRPS
skill, `1 − (CRPS − CRPS_oracle) / (CRPS_climatology − CRPS_oracle)`, against
one fixed climatology for every condition and rung: 1 = the simulator's
distribution, 0 = climatology. 24 models via OpenRouter, vendor-default
sampling, K = 3.

**What the view reads.** The pooled per-model number is
`data/causal/results/eci_vs_pooled.csv`, read as locked; the rank correlation
and p-value are recomputed from it (stdlib; `spearman_ties`/`spearman_p`
reproduce scipy's `spearmanr` to 12 places, and the test pins the README's
+0.68 / 0.0003 / 23). Per-rung and baseline detail for the tooltips comes from
`results/scores_summary_c{25,50,90}.json`. DeepSeek V4 Flash is partial (its
default reasoning stalls) and is excluded from the pooled figure, as the
dataset excludes it.

**Reading.** The intervention forecasts carry the gradient (per rung: 50%
ρ = +0.70, 25% +0.53, 90% +0.41); the no-intervention baseline does not
(ρ = +0.27, p = 0.21) — reasoning about the effect of an action is what
separates the tiers, not reading the report. Earlier designs saturated (v2:
19/24 models at the ceiling because a 90% campaign is an overwhelming cause);
the coverage ladder and the continuous target are what de-saturated it.

## The paper

`redlines/paper/causal.py` renders Graph 6's mirror (`results/causal_data.json`)
and `paper/numbers.py` reads the same file for its `causal:*` macros, so the
paper cannot disagree with the page. The hand-frozen
`data/fbsim_causal_pooled.json` it used to read was retired on 2026-08-28 in
favour of the locked dataset itself.

## Caveats, for any writeup

- Observational is not causal, and the causal bench is a toy simulator with
  its parameters stated. Claim "on these domains".
- One data family each. The weather bench's FRED arm died honestly (no CI
  excluded zero at n = 20 for the 30-day horizon).
- Effective n < nominal n on the weather bench (cells share sets and
  horizons); the CIs are block-bootstrapped but point estimates stay
  screening-grade.
- Models are not independent samples; every ρ against ECI is descriptive.
- Three ECI vintages on one site (above).
