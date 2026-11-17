# StarSim causal bench — locked dataset (2026-08-28)

Frozen copy of the single-region causal-forecasting benchmark and its 24-model
run. Design rationale and the record of rejected designs (v1–v3) are in
`../DESIGN.md`; generating code is `../starsim_single/`
at git tag `causal-v4-locked`. Do not regenerate into this directory; a new
run is a new directory.

## Headline

Intervention forecasts, pooled over three vaccine-coverage rungs (25 / 50 /
90%): **Spearman ρ = +0.68 vs ECI, p = 0.0003, n = 23** (`results/eci_vs_pooled.csv`,
`charts/eci_vs_pooled.png`). Per rung: 50% ρ = +0.70 (p = 0.0002), 25% +0.53
(p = 0.01), 90% +0.41 (p = 0.05). Baseline (no intervention) ρ = +0.26 (p = 0.21).
Models are not independent samples; treat as descriptive.

## Design

- **World**: one SIR population (starsim 3.3.4), 5,000 agents, ~6 contacts/day,
  10-day infectious period, no deaths, init_prev 0.5%. Four worlds = transmission
  probability {0.030, 0.040, 0.050, 0.065} (R₀ ≈ 1.8 / 2.4 / 3.0 / 3.9). The
  report states these parameters and the displayed run's cumulative infections
  every 5 days through day 20.
- **Item**: world × horizon (day 40, day 60) → 8 items. Target: **new infections
  between the end of day 20 and day t**. Forecast: quantiles p10/p25/p50/p75/p90.
- **Conditions**: baseline (report + question) and intervention (report +
  "vaccination campaign on day 21, 95% efficacy, c% coverage" + question), in
  **separate prompts**. Coverage rungs c ∈ {25, 50, 90}%. Baseline answers are
  shared across rungs.
- **Truth**: the distribution over simulator seeds whose day-20 count is within
  ±15% of the displayed run (131–290 seeds per world), per arm.
- **Score**: CRPS (quantile pinball, `fbsim_core.metrics.compute_crps`) averaged
  over the truth samples, as a skill score
  `1 − (CRPS − CRPS_oracle) / (CRPS_climatology − CRPS_oracle)`; oracle = the
  truth quantiles; climatology = `worlds/climatology.json`, the pooled target
  distribution over all worlds × coverages {0, 25, 50, 75, 90}% at that horizon
  (one fixed reference for every condition and rung). 1 = matches the
  simulator's distribution, 0 = climatology.
- **Models**: 24 ECI-ranked models via OpenRouter (`models.csv`), vendor-default
  sampling, K = 3 reps per (item, model), per-quantile medians over reps.
  deepseek-v4-flash is partial (its default reasoning stalls) and is excluded
  from the pooled figure.

## Files

- `worlds/worlds_c{90,50,25}.json` — reports, questions, intervention text,
  truth distributions (samples included), per rung
- `worlds/climatology.json` — the fixed CRPS reference
- `results/baseline.jsonl` — every baseline response (raw text, parsed quantiles, tokens, cost)
- `results/intervention_c{90,50,25}.jsonl` — every intervention response, per rung
- `results/scores_summary_c{90,50,25}.json` — per-model scores and gradients, per rung
- `results/eci_vs_pooled.csv` — the headline table
- `charts/` — `eci_vs_pooled.png` (headline), `eci_vs_recovered_c{90,50,25}.png` (baseline + intervention per rung)
- `MANIFEST.sha256`
