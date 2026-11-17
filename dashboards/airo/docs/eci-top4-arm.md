# The ECI top-4 arm — run, held, not published

**Status (2026-08-28, later the same day): promoted to the default.** The project
lead's decision: the model panel is defined as the top-k ECI models. `run_unified.py --model-set`
now defaults to `eci_topk` — the panel computed from the newest ECI snapshot by
`redlines.registry.panel()` (`docs/model-set.md`), which on the 2026-08-28 snapshot
is exactly this arm — so the Friday cron runs it from the next run on the box that
carries this code. The dashboard shows the panel from the first run it answers; the
2026-08-28 arm below stays in `results/experiments/eci_top4/`, not the series (it was
elicited under `unified-joint-v1` as an experiment, and promoting the rule is not the
same as back-filling one day's data). The earlier text of this note is kept as the
record of the comparison and the decision.

**Earlier status (2026-08-28, morning): parked pending a team decision.** The elicitation is done and
the comparison is reproducible. Nothing is published; the dashboard still serves the
frontier five and the Friday cron is untouched.

## What this is

An alternative model panel for the single instrument, chosen by **Epoch Capabilities
Index rank** instead of by hand:

| arm | models |
|---|---|
| `frontier5` (published) | Fable 5, GPT-5.5, Opus 4.8, Gemini 3.1 Pro, Grok 4.20 |
| `eci_top4` (this arm) | Fable 5, GPT-5.5 Pro, Opus 5, GPT-5.6 Sol |

Fable 5 is the only model the two arms share, so its five repeats carry over unchanged.

## Where the selection rule came from

An internal FRI analysis (the `forecastbench-ensembling` checkout, not published) — a prospective test on 29 rounds of resolved
ForecastBench data (dataset questions only, i.e. no market price to read off):

- Averaging the **top 3–4** models beats using the single best-ranked model by
  ~0.006 difficulty-adjusted Brier, and closes essentially the whole gap to the model
  you would have picked with hindsight (−0.0250 vs −0.0253). P(beats k=1) = 1.000.
- Ranking by **ECI beats ranking by ForecastBench track record** (−0.0278 vs −0.0256
  at top-3). Half that win is ECI being a marginally better ranker; the larger half is
  coverage — ECI scores brand-new frontier models that have no forecasting track record
  and therefore cannot be picked on past performance at all. At horizons ≥ 90 days,
  FB-rankable models drop to a median of 8 per round while ECI still covers 17.
- **Lab diversity is not worth paying for.** Across 3,842 model pairs, cross-lab pairs
  beat same-lab pairs by 0.00063 Brier once member skill is controlled — about 0.3 ECI
  points. One ECI point is worth ~0.00207 Brier (r = −0.68 across 88 models). So take
  the highest-ECI models and let the labs fall where they fall; forcing one-per-lab on
  the 2026-08-28 index would cost 5 ECI points to buy 0.0006.

Caveat carried over from that work: the rule was validated on questions resolving
within a year. It has not been, and cannot yet be, validated at 2050/2100 — which is
exactly where this arm's forecasts differ.

## What was run

`--joint --repeats 5 --model-set eci_top4`, protocol `unified-joint-v1`, LEAP condition
set — the same instrument the frontier five answered on the same day, so the panel swap
is the only thing that differs. 20 calls: 15 new plus Fable 5's existing 5.

Two rounds, because the first batch hit two failures:

- **GPT-5.6 Sol, 0/5.** It rejects function tools whenever a `reasoning_effort` is in
  play, and litellm supplies a default one for the gpt-5.x family. Fixed in
  the LLM layer this repo then imported from an internal FRI checkout (`xrisk-canaries`,
  not published): an explicit `reasoning_effort="minimal"` retry, mirroring the existing
  temperature fallback. That file was vendored into this repo later the same day as
  `redlines/llm.py`, which is where the retry lives now. An explicit low effort IS accepted
  with tools — verified directly.
- **Opus 5, 2/5.** Transient Anthropic rate-limiting; three workers on Opus-family
  endpoints while a separate `eciself6mo-pilot` run was in flight on the same box. The
  identical call succeeded on retry. Re-ran the missing three at `--workers 2`, 3/3.

## What it changes

Near-term forecasts do not move. The far horizons move up ~4pp.

| horizon | frontier 5 | ECI top-4 | delta | 95% CI (resampling repeats) |
|---|---|---|---|---|
| 6mo | 4.5pp | 4.8pp | +0.30 | [−0.12, +0.66] — noise |
| 12mo | 6.2 | 6.3 | +0.10 | [−0.31, +0.51] — noise |
| 2028 | 10.0 | 10.0 | +0.06 | [−0.43, +0.52] — noise |
| 2030 | 12.6 | 12.6 | +0.00 | [−0.43, +0.45] — noise |
| **2050** | 24.0 | 27.9 | **+3.83** | **[+3.32, +4.37]** |
| **2100** | 34.4 | 38.3 | **+3.81** | **[+3.16, +4.43]** |

Across the 201 unconditional cells the median absolute move is 0.66pp, p90 7.9pp. The
conditional panel moves the same way (median 0.59pp), so **policy effects are unchanged
— it is the levels that shift, not the deltas.**

Largest movers are the misalignment ladder at the far horizons: `misalign:100` at 2050
goes 58.9 → 73.1pp, `misalign:1k` 42.8 → 56.5pp, with nine more cells in the +10 to
+14pp range.

**The shift is composition, not a capability effect.** Per-model means at 2050+2100:

- frontier 5: Opus 4.8 35.9, Fable 5 33.8, Grok 4.20 29.7, GPT-5.5 24.8, Gemini 3.1 Pro 22.1
- ECI top-4: GPT-5.6 Sol 38.3, Opus 5 34.4, Fable 5 33.8, GPT-5.5 Pro 25.7

The swap drops the two lowest long-run anchors and adds the highest one yet. The arm is
also marginally tighter with itself: median between-model spread 4.6pp vs 5.2pp.

## The decision for the team

Promoting this arm raises the dashboard's headline long-run catastrophe numbers by ~4pp
and the misalignment ladder by up to 14pp — a visible move toward "more alarming" on the
panel that carries the paper's central claim, justified by a selection rule validated
only on short-horizon questions. Nothing at 2050 or 2100 resolves, so no accuracy check
is available at the horizons that moved.

Two smaller things, settled with the promotion (see `docs/model-set.md`):

1. **Index vintage.** The panel is *selected* from the newest snapshot
   (`redlines.eci.latest()`, with a WARN past 31 days); the registry's per-model `eci`
   field stays on the pinned 2026-07-07 vintage, so Graph 4 and every tracked artifact
   are byte-identical. Refreshing the pin remains a separate, deliberate change.
2. **Graph 4.** The panel members that postdate the pin are still NOT on `g4_ladder` —
   their ECI is a different index vintage, and mixing vintages on one
   capability-vs-skill trend line would compare two different indices.

## Files

| path | what |
|---|---|
| `redlines/eci.py` | the ECI snapshots: which exist, which is newest, how old, both formats; the staleness WARN |
| `redlines/registry.py` | `panel()` (top-`PANEL_K` runnable models of the newest snapshot), `MODEL_SETS` = `eci_topk` / `frontier5`, `panel_provenance()` |
| `code/run_unified.py` | `--model-set` (default `eci_topk` since 2026-08-28 pm; rows stamp `panel`) |
| `data/epoch_capabilities_index_2026-08-28.csv` | supplementary ECI snapshot, top 17 |
| `results/experiments/eci_top4/` | the run — outside `results/runs/`, which `runlog.load_runlog` globs into the published series |
| `code/compare_eci_top4.py` | the comparison above; `python3 code/compare_eci_top4.py` |
| `redlines/llm.py` | the `reasoning_effort` retry (vendored here 2026-08-28; the run itself used the pre-vendoring internal copy) |

Box logs: `~/logs/eci_top4-2026-08-28T1820Z.log`, `~/logs/eci_top4-fill-2026-08-28T1906Z.log`.

## Reproducing

```bash
# on the box (keys live there)
python -u code/run_unified.py --joint --repeats 5 --model-set eci_topk \
  --workers 2 \
  --out results/experiments/eci_top4/uncond_$STAMP.jsonl \
  --conditional-out results/experiments/eci_top4/instrument_$STAMP.jsonl

# locally, after rsyncing results/experiments/eci_top4/ down
python3 code/compare_eci_top4.py
```

Use `--workers 2`. Three concurrent workers rate-limited the Anthropic endpoints when
anything else was running on the box.
