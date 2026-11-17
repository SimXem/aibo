# llm-conditional-forecasting

Can LLMs do conditional forecasting? When told "suppose A happened," do
they move P(B) in the right direction, by an amount that tracks how
related A and B actually are in observed data?

MVP benchmark built 2026-08-20 (Nick Merrill / FRI, agreed with Ezra
Karger). Full pre-registered design, ground-truth construction, and the
pilot-caught-ground-truth story: **spec.md**.

## Result

All four metrics improve monotonically with model capability; the top
model meets the pre-registered pass bar.

| Model | M1 coherence (median eps) | M2 direction (13 pos) | M3 controls (median abs delta, bar 0.075) | M4 rank rho |
|---|---|---|---|---|
| claude-haiku-4-5 | 0.009 | 13/13 | 0.100 FAIL | +0.70 |
| claude-sonnet-5  | 0.003 | 13/13 | 0.020 pass | +0.81 |
| claude-opus-5    | 0.001 | 13/13 | 0.028 pass | +0.87 |
| claude-fable-5   | 0.001 | 13/13 | 0.014 pass | +0.88 |

Every tier gets direction right; what separates tiers is discipline on
independent pairs (not inventing associations) and magnitude tracking.

## Layout

- `spec.md` — pre-registered experiment specification (v3)
- `pairs_selected.json` — the 27 question pairs (21 scored + 6-pair
  unscored hemispheric probe), with ground-truth anomaly phi, bootstrap
  CIs, and declared mechanisms
- `run_bench.py` — elicitation runner (`pilot` mode, then full; resumable)
- `score_bench.py` — metrics M1-M4 + pass bar; writes `scatter_by_model.json`
- `results.jsonl` — the 2026-08-20 full run (540 responses)
- `mine_*.py`, `select_pairs*.py` — ground-truth provenance, in
  chronological order (panel phi -> short-horizon -> deseasonalized)
- `pilot_raw.txt`, `full_run.log` — run records

## Reproduce

```
export ANTHROPIC_API_KEY=...
python3 run_bench.py pilot   # read pilot_raw.txt before continuing
python3 run_bench.py
python3 score_bench.py
```

Requires `anthropic` and `numpy`; question/resolution data for
re-mining ground truth comes from a checkout of
`forecastbench-datasets` (paths in `mine_*.py`).
