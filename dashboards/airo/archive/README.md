# Archive

This directory holds dead scripts from `code/` that have been superseded or were one-off exploratory tools. The three `make_demo_*` scripts here must never be run against the live page — they read the mock template (`jason-demo.html`) and would clobber `jason-demo.live.html`'s hand-written live JSX if their output were re-injected.

- `make_demo_data.py` — Graph-4 v1, freeciv-only; superseded by `make_demo_combined.py`.
- `make_demo_avg.py` — Graph-4 v3, scatter-only; superseded by `make_demo_combined.py`.
- `make_demo_pandemic.py` — Graph-4 v2, pandemic-only; superseded by `make_demo_combined.py`.
- `freeciv_subset_hunt.py` — exploratory one-off; its conclusions are frozen as the `FC_HORIZONS`/`FC_BAND` constants in `make_demo_combined.py`; it handed off via `/tmp/fc_best_subset.json`, which no longer exists.
- `freeciv_subset_gradient.py` — exploratory one-off; its conclusions are frozen as the `FC_HORIZONS`/`FC_BAND` constants in `make_demo_combined.py`.
- `freeciv_discrimination.py` — exploratory one-off; its conclusions are frozen as the `FC_HORIZONS`/`FC_BAND` constants in `make_demo_combined.py`.
- `plot_freeciv_trend.py` — depends on the vanished `/tmp/fc_best_subset.json`.
- `plot_avg_trend.py` — depends on the vanished `/tmp/fc_best_subset.json`.
- `plot_graph4_panels.py` — matplotlib preview superseded by the in-page SVG charts.
- `plot_graph4_calibration_preview.py` — matplotlib preview superseded by the in-page SVG charts.

Archived 2026-10-22, when AIRO dropped litellm (litellm 1.107.0 on PyPI shipped a credential stealer on 2026-10-21). Every forecast now runs through pi (`redlines/pi_loop.py`). These called litellm and none ran in production; their outputs stay where they were in `data/` and `results/`, and rerunning one means installing litellm by hand.

- `litellm-runners/run_eval.py`, `litellm-runners/pandemic_smoke.py` — the Graph 4 model evals on the FreeCiv and pandemic corpora (`code/merge_graph4_run.py` merges their outputs).
- `litellm-runners/run_ladder_joint.py`, `litellm-runners/run_chain_eval.py` — the coherence experiment's runners (`docs/coherence-experiment.md`; `code/analyze_*` read their outputs).
- `litellm-runners/check_counting_comprehension.py` — the counting-rules comprehension diagnostic (`results/validation/counting-comprehension-v1/`).
- `litellm-runners/run_roster.py` — Graph 5's 24-model roster run through OpenRouter (`code/observational/` keeps the bench's mining and scoring).
- `causal/` — Graph 6's generating code, a frozen copy of the Starsim causal bench at `causal-v4-locked` (GPL-3.0; `data/causal/README.md`).
- `compare_harness.py` — compared a run through the litellm loop with the published pi run, cell by cell; with one loop there is nothing to compare.
