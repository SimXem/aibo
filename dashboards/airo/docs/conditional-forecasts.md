# Conditional forecasts: the LEAP Wave 12 policies

What a named policy does to the forecast. Issue #4 asked for one convincing
pair — status quo against a regulatory scenario, on one bottom-line question
— because that "turns the pitch from 'we track risk' into 'we can price
interventions'". This is that, built on LEAP's own policy set so every
conditional we produce has a human panel answering the same conditional in
the same words.

Status: **the single instrument is the published protocol as of
2026-08-27** (the project lead's decision, after the two runs below). The cron runs
`run_unified.py --joint --repeats 3`; its unconditional slice is the series
every panel reads and its conditionals feed the **Conditional-on tab of
index.html** (the standalone `conditional.html` lasted one day). The
separate-call pilot rows stay in the log as history. The plain weekly batch
is deprecated: the series switched elicitation on 2026-08-27 and the
timeline's snapshots say so (`protocols`).

## What LEAP asks

LEAP Wave 12 ("Safety Policies", internal draft dated 2026-08-26, vendored
under `data/leap/`, internal to FRI and not published; `data/leap_policies.json` is the tracked derivation) asks its panel three things:

1. P(AI-caused catastrophe by 2050) — the Wave 9 outcome, 10% of population
   in a five-year window — **unconditionally and under each of several
   policy conditions**. Also a "sub-catastrophe" at 1M deaths. **2050 only.**
2. P(each policy is implemented by 2030 / by 2050), with an 80%-similar
   clause.
3. Free-text policy tradeoffs.

The conditions are the status quo and five policies, two of which come in
mutually exclusive parts:

| id | LEAP | condition |
|---|---|---|
| `sq` | Status Quo | no new substantial AI policy anywhere through 2050; explicitly *not* the unconditional, which should include policy you expect |
| `p1` | P1 | federal ceiling preemption of state AI laws |
| `p2a` / `p2b` | P2 (a) / (b) | binding cap on the share of compute frontier developers may spend on frontier R&D — US alone / US + China jointly |
| `p3a` / `p3b` | P3 (a) / (b) | binding pre-release authorization for frontier models — US federal body / international body whose members include the US and China |
| `p4` | P4 | federal strict liability for frontier-model harms + capability-scaled insurance + punitive damages without malice |
| `p5` | P5 | bundle: P2b + P3b + P4 |

O1 and O2 are LEAP's *outcomes*, not conditions. O1 is our `catastrophe:ai`
in all but two clauses (LEAP counts deaths where the Auto-ARC set counts attributable
excess mortality; LEAP time-limits the AI's involvement to a year before the
event). O2 pairs loosely with `ladder:ai:1M`.

**The conditioning clause, verbatim, which every condition carries:**

> For each condition below, assume that the relevant governing body
> implements the policy immediately and that it remains in effect through
> December 31, 2050. In making this assumption, try to hold other factors
> constant and treat the policy implementation as exogenous. In other words,
> do not assume that implementation of a more stringent policy implies that
> the world is — in fact — more risky. We want your forecast of how risk
> changes as a result of the policy's implementation, not vice versa.

The exogeneity sentence is the load-bearing part. Without it a model reasons
"a strict-liability statute passing means the world got scary" and the
conditional forecast rises for the wrong reason.

## Design decisions

**Elicitation is unchanged; the condition is prepended.** `code/run_unified.py
--scenario <id>` renders one block at the top of the same batch prompt: the
LEAP instruction above, the condition ("Condition: …" — the policy summary
and, for P2/P3, which part is assumed), the full policy description a LEAP
panelist sees on the survey's Policies tab (background, historical baseline,
resolution criteria), and LEAP's frontier-model definition. Same models, same
tools, same 35 questions and criteria, same horizons, same token budget. With
no condition the slot renders empty and the prompt is byte-for-byte the weekly
run's (`tests/test_conditional.py`). The block states no relation between the
policy and any question and no direction; `CONDITION_BLOCK` is checked for
both.

**The whole set is elicited under every condition; the pilot *reports* one
cell.** The unified protocol's unit is the batch, and eliciting one question
alone would change the elicitation. So every conditional call answers all 201
cells, and the pilot chart reads `catastrophe:ai` at 2030 off it. Everything
else is in the log for later.

**"Immediately", not "by 2030".** Kept verbatim. It is what the LEAP panel
assumes, so the 2050 cell stays comparable; and for a 2030 horizon it is the
cleaner counterfactual — a policy landing in December 2029 cannot move 2030
risk, and "by 2030" would leave each model to pick its own start date.

**Verbatim also means "through 2050".** Our batch asks 2100 too. A 2100 cell
under this clause is a forecast under a policy the prompt does not extend
past 2050. It is computed and flagged (`horizon_note`), never rewritten —
and, since 2026-08-27, not shown: the Conditional-on tab offers 2030 and
2050 only, because a "policy effect" at 2100 under a policy that lapsed in
2050 is incoherent. The 2100 unconditional still feeds the main page.

**Two elicitation protocols, kept apart.** The pilot ran *separate calls*:
one call per model per condition (the full 35-question batch with the
condition block prepended), plus three unconditional calls for the noise —
55 calls, and no call ever sees another condition. The *single instrument*
(`--joint`, protocol `unified-joint-v1`, adopted 2026-08-27) is one
call per model that IS the survey: every question × horizon cell answered
unconditionally *and* under each of the eight conditions in one submission,
keyed per cell (`probabilities: {unconditional, sq, p1, …}` — 1,809 numbers
in ~15k output tokens), the way a LEAP panelist sees one table with
Unconditional beside every condition. `--repeats N` runs the whole instrument
N times per model; the spread is the noise, on the conditionals as well as
the unconditional. Three repeats is 15 calls, against the pilot's 55. The two
protocols' unconditional arms are different elicitations (one given beside
eight policy conditions, one not), so the log carries both under their own
protocol tags, the page switches between them, and nothing pools them. The
joint prompt's framing states no relation between conditions and no
direction (`tests/test_conditional.py::TestJointInstrument`).

**A 95% CI on every row, and "outside" means it excludes 1×.** Under the
single instrument the same call answers the unconditional and every
condition, so a condition's effect is *paired within the call*: per repeat
k, r_k = log(p_cond,k / p_uncond,k), and the between-call wander — which is
large (Grok's unconditional varies 8× across three instruments) — cancels.
Per model the estimate is the mean of r_k (its exponential is the
geometric-mean ratio the page shows) with a Student-t 95% interval over the
repeats (n=3, t=4.30). The ensemble estimate is the median across models of
those per-model means; its interval is a seeded bootstrap percentile
interval (600 draws) that resamples models with replacement and, within
each, its repeats. A bar is drawn only when the ensemble interval excludes
1×; a model's dot is faint when its own interval includes 1×. For the
separate-call pilot, where no call is shared, the fallback is an unpaired
Welch interval on log values. What the pairing changes: the models restate
the same small difference in every repeat, so at 2030 nearly every
condition clears 1× under the instrument — the moves are small (0.86–0.88×
for the single US policies) but they are not resampling. The grey band
around the 1× line is a second, different interval: **the unconditional
forecast's own 95% CI when re-asked** — each model's t-interval (on the logit scale since 2026-08-27 evening: bounded in 0–100%, identical to log below ~10%; losses stay on log) on its
level over its three repeats, as ratios to its centre, median across models
(≈0.6–1.8× at 2030: three draws pin a level poorly, and Grok's alone spans
0.04–22×). It replaces the earlier min–max "noise band", which was roughly a
50% prediction interval for a fourth draw, not a CI. The two intervals
answer different questions — the band, how sure we are of the level; the
whiskers, how sure we are of the move — and a move can be certain while the
level is not, because the move is paired within the call. A bootstrap over
models was tried for the band and rejected: it measures how far the five
models disagree (10× in level), not re-elicitation. The same paired design is what `timeline.html`
needs: it should compare a week's draws to the previous week's, with an
interval, before drawing a move.

**The baseline is the same-session unconditional arm, not the weekly point.**
A conditional run ten days after the weekly run mixes the policy's effect
with ten days of news. The experiment carries its own unconditional arms
(`--unconditional 3`); their mean is the zero line and their spread is the
re-elicitation noise floor, drawn on the chart as a band. A bar inside the
band has not been shown to do anything.

**Per-model deltas, then the ensemble.** Baselines differ tenfold across
models. Each model's change is taken against its own baseline; the ensemble
figure is the median of those. The summary carries three readings of one
change — percentage points, ratio to baseline, log-odds — but **the page
plots one: the ratio, on a log axis.** On a ~1% baseline the pp bar is
invisible; log-odds is symmetric but nobody says it aloud; the ratio is
what a reader can say ("the bundle cuts it to a tenth"), the log axis makes
½× and 2× the same distance from the baseline (so it inherits log-odds'
symmetry — at these probabilities the two are numerically almost the same),
and it is the only one of the three that also applies to an expected loss.
The noise band is the same statistic in the same unit: the median across
models of max/min over repeated unconditional calls, centred on 1×.

**The ladder is shown compressed: one expected-loss row per cause.** The
eight rungs of a cause are P(loss ≥ x_k) at thresholds rising tenfold
(100 deaths or $1B … 1B deaths or $10Q) — points on a survival function, so
E[loss] = ∫ S(x) dx and the sum Σ_k S(x_k)(x_k − x_{k−1}) is a **floor** on
it: every band valued at its lower threshold, nothing above 1B counted beyond
1B. The unit is death-equivalents at the ladder's own rate, 1 death = $2.2M since 2026-08-31 ($10M before)
(the "or" in "100 deaths or $1B"). It is pure arithmetic on the forecasts in
the log (`redlines.conditional.expected_loss`); no new elicitation. Two
things to know before reading it: (1) because thresholds rise 10× per rung,
**the 100M and 1B rungs are ~90–96% of the number** — the row mostly tracks
the top of the ladder, and the page says so with the cell's own share;
(2) a non-monotone ladder (a higher rung more likely than a lower one, which
the prompt does not forbid) is repaired by the running minimum from the
bottom, keeping the floor a floor, and the count is reported (zero in the
pilot's unconditional arms). The rung rows stay in the summary
(`analyze_conditional.py --question ladder:ai:1B`); the page just does not
give each one a chart. Because the unit is the point, an expected-loss chart
plots **levels** on a log lives/$ axis rather than ratios: an extra top row
shows each model's own unconditional value, the line is the ensemble-median
baseline, the dots are absolute, and the bar runs from the line to baseline ×
ensemble-median ratio (both numbers on the right).

**Status quo is a bar, not the zero line.** LEAP says the unconditional
forecast should include policy you expect. The gap between unconditional and
status quo is therefore the model's implied policy dividend.

**Conditional rows never enter the published log.** They go to
`results/conditional_runs.jsonl`, tagged with the condition id, LEAP id, and a
SHA-256 of the exact block the model saw. `load_runlog`, the timeline and
`tests/test_coherence.py` never see them; the runner refuses `--scenario`
against `results/forecast_runs_unified.jsonl`.

**Lead with AI catastrophe.** General catastrophe at 2030 is 1–2% for four of
five models with an AI-attributable slice of 0.15–0.8%; a policy delta there
sits inside the noise. `catastrophe:ai` is LEAP's O1 wording and the only cell
that will ever get a human conditional mark.

## Where LEAP's humans will and will not appear

LEAP asks the conditional outcome at **2050 only**. Every 2030 conditional is
model-only, permanently. When Wave 12 reports, its per-condition medians can
be pulled the way `code/fetch_human_baselines.py` pulls Wave 9 — the same
BigQuery join, with the `scenario_id` filter that script currently uses to
*exclude* conditional rows inverted — and drawn on the 2050 chart as
diamonds.

## Running it

```sh
# the pilot, on the cron box (keys in ~/.config/redlines/env):
python -u code/run_unified.py --scenario all --unconditional 3 \
    --experiment leap-wave12-pilot --out results/conditional_runs.jsonl
# 5 models x (3 unconditional + 8 conditions) = 55 calls, ~40 minutes

# the single instrument: every cell under every condition in one call, 5 repeats
python -u code/run_unified.py --joint --repeats 5 \
    --experiment leap-wave12-joint --out results/conditional_runs.jsonl
# 5 models x 3 = 15 calls; --smoke for one model, --dry-run to read the prompt

python3 code/run_unified.py --dry-run --scenario p2b --out /dev/null   # see the prompt
python3 code/analyze_conditional.py                                   # tables, 2030 + 2050
python3 code/analyze_conditional.py --question loss:ai --measure ratio  # the ladder folded to expected loss
python3 -m redlines build --views conditional                          # -> index.html, Conditional-on tab
python3 code/make_leap_policies.py --check                             # JSON is current
```

The policy text enters the repo through one script, `code/make_leap_policies.py`,
which parses the two vendored survey documents into `data/leap_policies.json`.
Nothing in that file is hand-typed; the eight conditions and their short
labels are the only authored part.

## To confirm with the LEAP team

1. The fielded Wave 12 instrument is the 2026-08-26 draft we hold — same
   policies, same clause.
2. Whether the conditional outcome is elicited at 2030 as well as 2050 (the
   draft says 2050 only; the policy-adoption question carries 2030 / 2050).
3. Whether we can have the Wave 12 per-condition medians as data when it
   reports, for the 2050 diamonds.

## Results — single instrument, 2026-08-27 (run `2026-08-27T1828Z`, 3 repeats)

15 calls (5 models × 3 repeats of the whole instrument), 15 full grids of
1,809 probabilities, one attempt each, every call grounded (5–30 search
hits). Wall clock 18 minutes. `python3 code/analyze_conditional.py --compare`
prints the two protocols side by side; the page's Elicitation toggle does
the same.

**AI catastrophe by 2030, ensemble median ratio (outside noise marked \*):**

| | SQ | P1 | P2a | P2b | P3a | P3b | P4 | P5 |
|---|---|---|---|---|---|---|---|---|
| single instrument | 1.09× | 1.15× | 0.88× | **0.67×\*** | 0.86× | **0.71×\*** | 0.86× | **0.48×\*** |
| separate calls | 0.64×\* | 0.63×\* | 0.34×\* | 0.17×\* | 0.38×\* | 0.49×\* | 0.45×\* | 0.11×\* |

At 2050: P5 0.43×\*, P2b 0.62×\*, P3b 0.64×\*; the rest 0.83–1.17×, inside
noise. Expected loss (`loss:ai`, 2030): only P5 clears noise, 0.51×.

What the instrument changed:

- **Every model orders the conditions the same way, and coherently:**
  SQ ≥ P1 > unconditional > P2a ≈ P3a ≈ P4 > P2b ≈ P3b > P5. The bundle is
  below each of its parts in all five models at both horizons — which the
  separate calls violated within-model (Fable P5 0.51× vs P2b 0.17×). The
  international variants (b) sit below the US-only variants (a) everywhere.
- **Status quo now sits above unconditional in every model (1.05–1.41×),
  and so does preemption (1.05–1.21×).** This is LEAP's framing — the
  unconditional prices in policy the model expects — and it is what a
  panelist answering the same table would produce. The separate calls had
  SQ at 0.64× for reasons that looked like a conditioning reflex.
- **The moves are smaller and most single policies are inside noise.** The
  ensemble band (median across models of where three repeats landed) is
  ≈0.8–1.3×; only the international authorization, the joint compute cap,
  and the bundle clear it at 2030. The separate protocol's 0.1–0.4× moves
  do not survive being asked side by side.
- **The joint unconditional is lower than the separate one in four of five
  models** — Fable 0.12% vs 0.23%, GPT-5.5 0.19% vs 0.37%, Grok 1.4% vs
  2.4%, Opus 0.67% vs 0.73%, Gemini equal; ensemble 0.19% vs 0.37%. Same day,
  an hour apart, a 2× gap the 1.5× repeat noise does not cover: the
  unconditional answered beside eight policy conditions is a different
  number. This is the fact that decides whether the instrument can feed the
  main UI: it can, but as a new protocol from a marked date, not as more
  points on the existing series.
- **Repeat noise is model-specific and large for Grok** (8.75× max/min at
  2030 across three instruments; 2.5× for GPT-5.5; ≤1.5× for the others).
  A per-model band is the right unit; the timeline needs one.

## Results — pilot, separate calls, 2026-08-27 (run `2026-08-27T1711Z`)

55 calls, 55 full grids, one retry (Gemini's known empty submission, on an
unconditional arm). Two calls ran with **no search evidence** — Gemini under
`p2b` and `p5` — and are marked `†` / hollow on the page; they are the visible
outliers below. Tables: `python3 code/analyze_conditional.py`.

**AI catastrophe (`catastrophe:ai`), the pilot cell.** Same-session
unconditional baselines: Fable 0.23%, GPT-5.5 0.37%, Gemini 0.11%, Grok 2.37%,
Opus 0.73% at 2030 (ensemble median 0.37%); 2.3 / 3.0 / 1.6 / 9.7 / 5.7% at
2050 (median 3.0%). Re-elicitation spread across three unconditional calls:
±0.05 pp at 2030, ±0.50 pp at 2050 (≈0.2 in log-odds at both).

| condition | 2030: ensemble Δ (ratio), lowered/raised | 2050: ensemble Δ (ratio), lowered/raised |
|---|---|---|
| status quo | −0.05 pp (0.64×), 3↓ 2↑ — inside the spread | **+0.93 pp (1.41×)**, 1↓ 4↑ |
| P1 preemption | −0.10 pp (0.63×), 4↓ 1↑ | −0.13 pp (0.94×), 3↓ 2↑ — inside the spread |
| P2a compute cap, US | −0.15 pp (0.34×), 4↓ 1↑ | −1.27 pp (0.34×), 4↓ 1↑ |
| P2b compute cap, US+China | −0.19 pp (0.17×), 4↓ 1↑† | −1.73 pp (0.26×), 4↓ 1↑† |
| P3a authorization, US | −0.17 pp (0.38×), 5↓ | −1.47 pp (0.47×), 5↓ |
| P3b authorization, intl | −0.19 pp (0.49×), 5↓ | −1.20 pp (0.49×), 5↓ |
| P4 strict liability | −0.11 pp (0.45×), 4↓ 1↑ | −1.00 pp (0.67×), 4↓ 1↑ |
| **P5 bundle** | **−0.33 pp (0.11×)**, 5↓ | **−2.65 pp (0.14×)**, 5↓ |

† the one model raising it is Gemini's ungrounded call.

What this says, and does not:

- **Every policy lowers the forecast in the ensemble, at both horizons; the
  bundle lowers it most,** and by more than any of its three parts, which is
  the direction a coherent forecaster should give (not enforced; measured).
- **Pre-release authorization is the only single policy every model lowers
  under,** at both horizons and both variants. The compute cap moves the
  ensemble further but one model (Opus at 2030, Gemini† at 2050) does not
  follow.
- **Status quo behaves as LEAP's framing predicts:** no effect at 2030
  (nothing has time to bite), and at 2050 four of five models put risk
  *above* their unconditional forecast — the unconditional already prices
  in some policy. GPT-5.5 puts the gap at 4× (3% → 12%).
- **Preemption (P1) is a null at 2050 and a small lowering at 2030** — the
  latter mostly Gemini, whose 2030 answer collapses to 0.01% under nearly
  every condition regardless of content. Treat that model's 2030 conditionals
  as a "conditioning reflex", not a policy read.
- **Model-level moves are not uniform.** Grok carries the largest absolute
  changes (2.4% → 0.3% under P5 at 2030) because it starts highest; Opus
  answers 0.8% — one of its own unconditional values — for half the
  conditions at 2030, i.e. "no change". Per-model deltas are the honest unit;
  the ensemble line is a median of five, not a consensus.

**General catastrophe (`catastrophe:general`)** shows the same ordering with
smaller relative moves (P5 0.38× at 2030, 0.37× at 2050, ensemble), as
expected for a question these AI policies only partly reach. All 35 questions
are in the log; only these two have been read.

**Expected loss (`loss:ai`, the AI-incident ladder folded), 2030.**
Unconditional floor 3.45M death-equivalents (≈$34.5T) ensemble median, per
model 1.6M–10.3M; the 100M and 1B rungs are 94% of it. Re-elicitation spread
across the three unconditional arms is **×1.82** — far wider than the
probability cells', because the number is a few tiny top-rung probabilities
times a billion. Under the conditions (ensemble median ratio): sq 0.71×,
P1 0.70×, P2a 0.80×, P2b 0.70×†, P3a 0.58× (5↓), P3b 0.41×, P4 0.57×,
**P5 0.38× (5↓)**. Same ordering as the catastrophe cell, smaller moves, and
only P3b and P5 clear the ×1.82 band. Grok raises expected loss 4× under P1
(preemption) — the largest single move on the page.

**One session, one pass per condition.** The spread band is the only
uncertainty shown. A second session on another day is the next thing to run
before any of these numbers is quoted.

## ECI projection for the capability-conditional (recorded 2026-08-28)

The next conditional asks each question given a US-frontier ECI level reached
by end of 2027. The levels come from Peter Wildeford's `metr_graph` ECI tab
(https://metrgraph.streamlit.app/?tab=eci) at its defaults, reproduced in
`code/eci_projection_metrgraph.py` on the app's own CSV as refreshed 2026-08-21
(`data/epoch_capabilities_index_2026-08-21.csv`) and verified against the app
run headlessly (streamlit `AppTest`, 200k samples: 2027EOY 185.9, 80% CI
173.8–209.7). Table and fit are in `data/eci_projection_2026-08-21.json`.

| target | p5 | p10 | p25 | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|---|---|
| today (2026-08-28) | 162.1 | 162.8 | 164.1 | 165.6 | 167.4 | 169.4 | 170.8 |
| 2026 EOY | 164.9 | 165.9 | 167.9 | 170.8 | 174.6 | 179.4 | 183.2 |
| 2027 Jun | 168.3 | 169.9 | 173.2 | 178.3 | 185.4 | 194.5 | 201.5 |
| **2027 EOY** | 171.6 | **173.8** | 178.6 | **185.9** | 196.5 | **209.8** | 220.2 |
| 2028 EOY | 177.9 | 181.5 | 189.2 | 201.2 | 218.5 | 240.4 | 257.5 |
| 2029 EOY | 184.2 | 189.2 | 199.8 | 216.5 | 240.5 | 271.0 | 294.8 |

Method (the app's "Linear" basis): running-max frontier over US models
released since 2024-02-29, best variant per model name (20 points, Claude 3
Opus 126.7 → Claude Fable 5 (high) 162.49 on 2026-06-09); single OLS gives
15.3 pts/yr; pts/yr is sampled lognormal with 80% CI [7.6, 30.6]; the start
is normal around the fitted-trend score at the anchor (162.1) with 80% CI ±2;
score(t) = start + t · pts/yr. 400k samples, seed 1 (the app's 5k unseeded
samples wobble ±0.3).

Three things to keep in mind when conditioning on these:

- **The trend already leads the data.** Nothing since June has beaten Fable 5
  (August releases sit near 156), so the projection's "today" median (165.6)
  is ~3 points above the actual frontier. The fan follows the line, not the
  last point.
- **The upper tail is fat by construction.** Lognormal pts/yr puts the 2027
  p90 at +47 points in 19 months, against +11–12 for one GPT-5 → Fable 5
  sized jump. In ladder terms p10 ≈ one such jump above Fable 5, p50 ≈ two,
  p90 ≈ four.
- **Epoch rescores live.** The 08-21 values for the frontier five are within
  1–2 points of the 07-07 snapshot the dashboard ladder uses (Fable 5
  161 → 162.5, GPT-5.5 159 → 161.7, Opus 4.8 158 → 157.8, Gemini 3.1 Pro
  155 → 154.6, Grok 4.20 154 → 152.1), so the two scales are interchangeable
  at this precision.

## Capability conditional: frontier ECI at end of 2027 (pilot, 2026-08-28)

The second condition set. Same instrument, same tool, same analysis; the
CONDITIONS section carries three capability levels instead of eight
policies, and no policy at all — for this pilot the instrument is the
unconditional plus the three ECI conditions (the project lead's call: just
unconditional and conditional on ECI). The levels are the p10 / p50 / p90 of the
projection above, rounded to the point: **174, 186, 210**. Reported at 2030
to start.

**The runner takes a condition set.** `run_unified.py --joint --scenarios
data/eci_conditions.json` swaps the CONDITIONS section; everything else in
the call is the policy instrument's. A set is a JSON file in
`data/leap_policies.json`'s shape (`conditioning`, `conditions`, `source`)
plus `kind` (the noun the prompt uses), `slug` and `protocol`. The ECI set is
generated by `code/make_eci_conditions.py` from the projection JSON and the
vendored Epoch CSV — the levels, the reference ladder and the step from
today's frontier are looked up, never typed; the instruction, definitions
and labels are authored there. The LEAP text is pinned byte-for-byte
(`tests/test_conditional.py::TestConditionSets`: the conditions-block SHA the
weekly rows are stamped with, and the whole joint prompt at a fixed date), so
the refactor did not touch the published instrument.

**Its own protocol tag and its own files.** Rows are `unified-joint-eci-v1`,
`condition_set: eci`. The whole instrument goes to
`results/conditional_runs_eci.jsonl` and the unconditional slice to
`results/eci_runs/<stamp>.jsonl`; the runner refuses to write a non-LEAP set
into `results/runs/` or `results/conditional_runs.jsonl`. An unconditional
answered beside three capability levels is a third elicitation — never
pooled with the policy instrument's unconditional, nor with the series.

**A fact learned, not an intervention.** LEAP's clause says hold other
factors constant and treat the policy as exogenous. A capability level is
not something anyone does to the world — it does not arrive without the
investment, compute and progress that produce it — so the instruction says
the opposite: *treat it as a fact you have learned about the world; update
your expectations about everything that would ordinarily accompany it
(investment, compute, algorithmic progress, deployment, and how governments
and developers respond) as you would upon learning it.* P(Q | ECI = x), not
P(Q | do(ECI = x)). This is the reading a later mixture over the projection
needs, and it is the one a human panel would naturally give. It is also the
opposite framing from the policy set, which is worth remembering when the
two are shown side by side.

**"Approximately x", not "at least x".** "Frontier ECI reaches at least the
10th percentile" is nearly the unconditional; a point condition (within about
two points) partitions the projection into a slow, a trend and a fast world,
and three point conditionals are what Σ P(Q | x_k) P(x_k) needs.

**The level, not its percentile.** The prompt gives the number, a
definition of ECI and the frontier, and a reference ladder from the CSV
(GPT-4 126 → Claude 3.5 Sonnet 130 → o1 143 → o3 147 → GPT-5 150 →
Gemini 3 Pro 153 → GPT-5.4 Pro 159 → GPT-5.5 Pro 162 → Claude Fable 5 162,
with dates) plus the step from today's frontier (+12 / +24 / +48). The
model can compute the pace itself; whether 210 is "fast" is its judgement,
not our label. "Slow / trend / fast" and the percentiles live in the file's
metadata and on any chart, never in the prompt
(`test_eci_prompt_carries_the_levels_and_not_the_percentiles`).

**The frontier is Epoch's scale of 2026-08-21, US models, best variant.**
That is what the projection is of (metr_graph's "US best"), and the prompt
says so. Epoch rescores the whole index as benchmarks are added; a level
stated on a later scale would be a different condition.

**The whole set is elicited; 2030 is reported.** All 201 cells, all six
horizons, under all four conditions (804 numbers per call, against the
policy instrument's 1,809). The rolling 6-/12-month cells resolve before
the conditioned date; they are conditionals on a later fact, coherent but
odd, and not the pilot's reading.

```sh
python3 code/make_eci_conditions.py --check                              # data/eci_conditions.json is current
python3 code/run_unified.py --joint --scenarios data/eci_conditions.json --dry-run | less
# on the box:
python -u code/run_unified.py --joint --repeats 3 --scenarios data/eci_conditions.json --experiment eci-pilot
#   -> results/eci_runs/<stamp>.jsonl (unconditional slice), results/conditional_runs_eci.jsonl (instrument)
python3 code/analyze_conditional.py --scenarios data/eci_conditions.json --question catastrophe:ai --horizon 2030 --measure ratio
python3 code/analyze_conditional.py --scenarios data/eci_conditions.json --question loss:ai --horizon 2030
```

Not yet done: a chart. The Conditional-on tab reads the policy set only;
the capability set needs either a second condition-set switch on that tab
or its own panel (levels against ECI on the x-axis is the natural one, with
the projection's density under it).

### Results — pilot, 2026-08-28 (run `2026-08-28T1559Z`, 3 repeats, 15 calls, 0 failures, one attempt each)

`python3 code/analyze_conditional.py --scenarios data/eci_conditions.json
--question catastrophe:ai --horizon 2030 --measure ratio`; the full summary
is `results/conditional_summary_eci.json`.

**AI catastrophe by 2030** (ensemble median of per-model paired ratios;
95% bootstrap CI; \* = CI excludes 1×):

| | unconditional | ECI 174 | ECI 186 | ECI 210 |
|---|---|---|---|---|
| ensemble | 0.36% (band 0.31–3.3×) | 1.14× [0.96, 1.71] | **2.62×\*** [1.79, 4.11] | **7.48×\*** [4.23, 16.2] |
| level (median across models) | 0.36% | 0.58% | 1.6% | 3.7% |
| Fable 5 | 0.18% | 0.98× | 1.83×\* | 4.23×\* |
| GPT-5.5 | 0.36% | 1.52× | 4.11×\* | 16.2×\* |
| Gemini 3.1 Pro | 0.22% | 1.13× | 2.62×\* | 10.4×\* |
| Grok 4.20 | 1.00% | 1.14× | 2.40× | 7.48× |
| Opus 4.8 | 0.50% | 1.70×\* | 3.26×\* | 7.33×\* |

Every model orders the three worlds the same way on this cell, and on
every other cell: across all 35 questions and the four expected-loss rows
at 2030, ECI 186 and ECI 210 clear the ensemble interval everywhere
(186: 1.25–3.2×, 210: 1.5–16×, largest at the top rungs and for
misalignment), and ECI 174 clears it nowhere (1.0–1.3×). General
catastrophe: 1.08× / 1.70×\* / 3.37×\*; disempowerment: 1.21× / 2.60×\* /
7.49×\*; `loss:ai`: 1.28× / 2.82×\* / 8.48×\*.

**The models' own median is the projection's slow world.** Asked nothing
about the pace, four of five say in their rationale what they assume
unconditionally: Fable 5 "trend extrapolation puts expected end-2027 ECI
near 176 … so ECI 174 ≈ unconditional"; Grok "assumes ~175–180"; Gemini
"eci174 aligns closely with the unconditional expectation"; Opus scales
"monotonically" from a baseline it does not name. So the models'
unconditional sits at metr_graph's **p10**, not its p50 — they extrapolate
the recent ~12–15 pts/yr from the June 2026 frontier without the fitted
line's lead and without the projection's lognormal pace uncertainty —
and the "trend" condition (186) reads to them as a fast world, 210 as
"takeoff-like", "AGI/ASI by 2027". Two readings follow. (1) As a
conditional forecast the table is fine as it stands: P(Q | ECI = x) at
three x's. (2) As a mixture, Σ P(Q | x_k) w_k with the projection's
weights would land well above every model's unconditional, because the
models put most of their own mass at or below 174. The gap between the
models' implicit ECI expectation and metr_graph's is itself a finding,
and the cheapest next step is to ask for it: one more field per call,
P(frontier ECI ≥ x by end of 2027) for each x, the way LEAP asks
P(policy implemented).

**Same day, two instruments.** The policy instrument's unconditional (the
cron run `2026-08-28T1200Z`, five repeats) and this one's (three repeats),
four hours apart, on AI catastrophe 2030: ensemble medians 0.26% and
0.36%; per model 0.23/0.18 (Fable), 0.26/0.36 (GPT), 0.02/0.22 (Gemini),
0.70/1.00 (Grok), 0.62/0.50 (Opus). Inside each model's own band except
Gemini's, whose policy-instrument level is an outlier low. The
unconditional is an elicitation of the instrument it sits in; the two are
kept under their own protocol tags and never pooled.

**Cheap.** 804 numbers per call against the policy instrument's 1,809; 21
minutes wall clock; no retries.

## Self-elicited capability conditional: the model forecasts ECI itself (pilot, 2026-08-28)

The project lead's design, after the fixed-level pilot: instead of handing the model
three levels from metr_graph, **ask it for its own distribution first, from
the vendored Epoch history, and condition on that.** In one call the model
(1) is shown the frontier-ECI history — every US release that set a new
high from GPT-4 (Mar 2023, 125.8) to Claude Fable 5 (Jun 2026, 162.5), 23
points from the 2026-08-21 CSV — and gives its 25th / 50th / 75th
percentiles for the frontier ECI on **December 31, 2030** (`eci_forecast`,
a required object on the tool, non-decreasing or the call is retried);
(2) answers every cell unconditionally and conditional on the frontier being
approximately its own p25 / p50 / p75 (`eci_p25`, `eci_p50`, `eci_p75`). Same
"fact learned" clause as the fixed set, dated 2030.

Two things it gives that the fixed set cannot. **The model's ECI forecast
beside the trend's**: metr_graph's projection at the same date is p25 210.4
/ p50 231.7 / p75 262.5 (the app's table stops at 2029; this is the same
trajectory evaluated at 2030-12-31, added to `code/eci_projection_metrgraph.py`
and `data/eci_projection_2026-08-21.json`), never shown to the model. And
**whether asking moves the unconditional**: three joint instruments ran the
same day — the policy set (cron, 12:00Z), the fixed ECI set (15:59Z) and this
one — so their unconditional arms can be laid side by side per model.

Mechanics: `data/eci_self_conditions.json` (`code/make_eci_self_conditions.py`;
`elicit` describes the quantity, the conditions carry `field`), protocol
`unified-joint-eciself-v1`, rows in `results/conditional_runs_eciself.jsonl`
+ `results/eciself_runs/`. The conditions are keyed by percentile, so the
level differs per call; the runner stamps each condition row with the number
the model gave (`condition.value`) and every row of the call with
`elicited.eci_forecast`. The LEAP text is still pinned (`TestSelfElicitedSet`).

```sh
python3 code/make_eci_self_conditions.py --check
python3 code/run_unified.py --joint --scenarios data/eci_self_conditions.json --dry-run | less
# on the box, one model to start (2026-08-28):
python -u code/run_unified.py --joint --repeats 3 --models "Fable 5" --scenarios data/eci_self_conditions.json --experiment eciself-pilot
python3 code/analyze_eci_self.py            # forecasts vs trend; conditionals; unconditionals across the three instruments
```

### Results — Fable 5 only, 2026-08-28 (run `2026-08-28T1828Z`, 3 repeats, 0 failures)

`python3 code/analyze_eci_self.py --policy-runs 2026-08-28T1200Z`; summary
in `results/conditional_summary_eciself.json`.

**Fable 5's frontier ECI on 2030-12-31, against the trend:**

| | p25 | p50 | p75 | IQR |
|---|---|---|---|---|
| call 1 | 183 | 197 | 214 | 31 |
| call 2 | 195 | 210 | 228 | 33 |
| call 3 | 190 | 206 | 224 | 34 |
| **Fable 5 (median)** | **190** | **206** | **224** | 34 |
| metr_graph trend, same date | 210.4 | 231.7 | 262.5 | 52 |

Its median sits below the trend's 25th percentile, and its interquartile
range is two-thirds of the trend's. In its own words: "~13–15 pts/yr since
late 2024 … I expect some deceleration", "+28 to +62 pts over 4.3 years".
206 by end of 2030 is ~10 pts/yr from today's 162; metr_graph's linear fit
is 15.3/yr with a lognormal pace spread. Same story the fixed set told
from the other side (there, its unconditional sat at the projection's
p10): **the model expects slower progress than the trend, and it says so
consistently across calls** (medians 197 / 210 / 206).

**Conditional on its own worlds, 2030** (paired ratio to the same call's
unconditional; 95% t-interval over the three repeats; \* excludes 1×):

| | unconditional (3 draws) | own p25 (≈190) | own p50 (≈206) | own p75 (≈224) |
|---|---|---|---|---|
| AI catastrophe | 0.26% (0.50 / 0.08 / 0.20) | **0.53×\*** [0.41, 0.69] | 0.98× [0.81, 1.19] | **1.93×\*** [1.66, 2.25] |
| general catastrophe | 0.80% | **0.77×\*** | 0.98× | **1.47×\*** |
| disempowerment | 0.60% | **0.38×\*** | 0.96× | **2.41×\*** |

**The median world reproduces the unconditional** — 0.96–0.98× on all
three cells, inside every interval. That is the coherence check the fixed
set could not offer (its levels were someone else's), and it passes: the
model's conditional-on-its-own-median is its unconditional, while the
quartile worlds move it about 2× each way, symmetrically in log space.

**Asking for the forecast did not visibly move the unconditional.** Fable
5's unconditional under the three same-day instruments — policy set
(12:00Z, n=5), fixed ECI set (15:59Z, n=3), this one (18:28Z, n=3): AI
catastrophe 0.23% / 0.18% / 0.26%; general 1.00% / 0.70% / 0.80%;
disempowerment 0.50% / 0.37% / 0.60%. All inside its own re-elicitation
band (which on AI catastrophe is 0.1–9.6×: the three draws here were 0.50,
0.08 and 0.20%). Only a large shift would show at n=3; none did.

Parked, not analysed: the first two calls of the aborted five-model run
(`2026-08-28T1825Z`, Grok 4.20 and GPT-5.5, one each) are on the box at
`results/experiments/eciself-aborted-1825Z/`; they carry their own
`eci_forecast` and can join a five-model run later.

## Rolling variant: frontier ECI six months from the run date (2026-08-28)

The project lead's follow-up, after the Fable 5 result: the same instrument, but the model forecasts
the frontier ECI **six months from today** — a date the runner generates —
and conditions on its own p25 / p50 / p75 at that date. Six months is the
batch's own rolling horizon, so the ECI target lands on the same day the
`6mo` cells resolve (`2027-02-28` for a run on 2026-08-28): the model's
capability forecast and its six-month risk forecasts are about one date.

Mechanics: `code/make_eci_self_conditions.py --months 6 --out
data/eci_self6mo_conditions.json` writes the set with a `{target_date}`
placeholder in every text and `elicit.target_months = 6`;
`run_unified.resolve_set` fills the date when the prompt is built (the
rolling horizons' month arithmetic, `add_months`, day clamped) and stamps
it on every row (`elicited.target_date`); the sha stamped on the condition
rows is of the resolved block, so it changes with the run date, as it
should. Protocol `unified-joint-eciself6mo-v1`, files
`results/conditional_runs_eciself6mo.jsonl` + `results/eciself6mo_runs/`.
The trend to compare against is computed at analysis time for the stamped
date — `code/eci_projection_metrgraph.py` is now importable
(`fit`, `project`) and `code/analyze_eci_self.py --scenarios
data/eci_self6mo_conditions.json` calls it; at 2027-02-28 the trend is
p25 169.7 / p50 173.2 / p75 178.1. The projection JSON is byte-identical
after the refactor; the LEAP text is still pinned
(`TestRollingSelfElicitedSet`).

```sh
python3 code/make_eci_self_conditions.py --months 6 --out data/eci_self6mo_conditions.json --check
python3 code/run_unified.py --joint --scenarios data/eci_self6mo_conditions.json --dry-run | grep -A3 "Step 1"
# on the box:
python -u code/run_unified.py --joint --repeats 3 --models "Fable 5" --scenarios data/eci_self6mo_conditions.json --experiment eciself6mo-pilot
python3 code/analyze_eci_self.py --scenarios data/eci_self6mo_conditions.json --policy-runs <same-day policy run>
```

The first launch (18:48Z) was refused by the Anthropic workspace usage
limit ("You have reached your specified workspace API usage limits …
2026-09-01"); the GCP Secret Manager `API_KEY_ANTHROPIC` turned out to be
revoked (401); the limit was raised and the run went at 19:02Z.

### Results — Fable 5 only, 2026-08-28 (run `2026-08-28T1902Z`, target 2027-02-28, 3 repeats, 0 failures)

`python3 code/analyze_eci_self.py --scenarios data/eci_self6mo_conditions.json
--policy-runs 2026-08-28T1200Z`; summary in
`results/conditional_summary_eciself6mo.json`.

**Fable 5's frontier ECI on 2027-02-28, against the trend at that date:**

| | p25 | p50 | p75 | IQR |
|---|---|---|---|---|
| calls 1 / 2 / 3 | 166.5 / 166 / 167 | 170 / 170 / 170 | 174 / 174 / 174 | 8 |
| **Fable 5 (median)** | **166** | **170** | **174** | 8 |
| metr_graph trend, same date | 169.7 | 173.2 | 178.1 | 8.4 |

Three calls, one answer. The pace agrees with the trend: 170 is +7.5 over
the June 2026 frontier in six months (≈15 pts/yr; the fit is 15.3/yr), and
the IQRs match (8 vs 8.4). The 3-point level gap is the fitted line's lead
over the last data point — the trend's "today" is 165.6 against the actual
162.5 — not a disagreement about speed. Set beside the end-of-2030 answer
(206 vs 232, ≈10 pts/yr), the model extrapolates the current pace over the
next six months and expects deceleration after that.

**Conditional on its own worlds, 2030** (paired ratio; \* excludes 1×):

| | uncond | own p25 (≈166) | own p50 (≈170) | own p75 (≈174) |
|---|---|---|---|---|
| AI catastrophe | 0.22% (0.20 / 0.25 / 0.20) | **0.85×\*** | 1.00× | **1.25×\*** |
| general catastrophe | 1.10% | **0.93×\*** | 1.00× | **1.14×\*** |
| disempowerment | 0.60% | **0.78×\*** | 1.00× | **1.35×\*** |

And at the six-month horizon itself (the cells that resolve on the target
date): every ladder rung 0.75–0.83× / 0.98× / 1.30–1.38× (e.g.
`ladder:ai:1M` 0.75×\* / 0.98× / 1.36×\*; `loss:ai` 0.80×\* / 1.00× /
1.34×\*), the saturated 100-death rungs 0.97 / 1.00 / 1.03.

**The multiplier is flat.** At 2030, 34 of 35 cells sit in 0.83–0.87× and
1.20–1.26×; at six months, in 0.75–0.83× and 1.29–1.38×. The rationale says
why: "scale risks up ~15–25% at short horizons and ~5–10% at long horizons
… the p25 world is scaled down symmetrically". A ±4-point capability band
is applied as one relative factor to everything that could be capability
sensitive, larger for the near horizon. The own-median world is 1.00× on
every cell — the coherence check passes again, this time exactly.

**Unconditionals, four instruments, one day** (Fable 5): AI catastrophe
2030 0.23% (policy, n=5) / 0.18% (fixed ECI) / 0.26% (self ECI 2030) /
0.22% (self ECI +6mo); general 1.00 / 0.70 / 0.80 / 1.10%; disempowerment
0.50 / 0.37 / 0.60 / 0.60%. Nothing moves; this run's three unconditional
draws on AI catastrophe were 0.20 / 0.25 / 0.20% (noise floor ×1.25,
against ×6.25 in the end-of-2030 run three hours earlier).

### Results — all five models, 2026-08-28 (run `2026-08-28T1950Z`: the other four × 3, target 2027-02-28, 12/12 calls, 0 failures)

`python -u code/run_unified.py --joint --repeats 3 --models "GPT-5.5,Opus 4.8,Gemini 3.1 Pro,Grok 4.20" --scenarios data/eci_self6mo_conditions.json --experiment eciself6mo-rest`
on the box, 19:50–20:05 UTC, with the prompt byte-identical to the pilot's
(`--dry-run` sha `fe60c97e…` on both machines). Pooled with the pilot:
2,100 rows, 5 models × 3 repeats; `results/conditional_summary_eciself6mo.json`
now covers all five.

**Frontier ECI on 2027-02-28, per model (median of its three calls):**

| | p25 | p50 | p75 | IQR |
|---|---|---|---|---|
| Fable 5 | 166 | 170 | 174 | 8 |
| GPT-5.5 | 164 | 168 | 175 | 10 |
| Gemini 3.1 Pro | 165 | 168 | 172 | 7 |
| Grok 4.20 | 167 | 172 | 179 | 12 |
| Opus 4.8 | 167 | 171 | 176 | 9 |
| **ensemble (median across models)** | **166** | **170** | **175** | 8 |
| metr_graph trend, same date | 169.7 | 173.2 | 178.1 | 8.4 |

Five models, five medians within five points of each other (168–173), all
1–5 under the trend's 173.2 — the same picture as the pilot: the fitted
line's 3-point lead over the last data point, not a slower pace. Every p75
but Grok's (179) sits at or under the trend's 178.1; the IQRs bracket the
trend's 8.4 (7–12). Calls agree within a model: Fable 5 gave the same three
numbers three times, Grok 172/172/173, Opus 169/171/172, GPT-5.5
168/168/171; Gemini's first call was higher (174) and its next two 168.

**Conditional on each model's own worlds, 2030** (paired ratio to its own
unconditional; \* excludes 1×; † answered without search evidence):

| AI catastrophe | uncond | own p25 | own p50 | own p75 |
|---|---|---|---|---|
| Fable 5 | 0.22% | 0.85×\* | 1.00× | 1.25×\* |
| GPT-5.5 | 0.35% | 0.69×\* | 1.00× | 1.61× |
| Gemini 3.1 Pro | 0.01% | 0.86×† | 1.00×† | 1.26×† |
| Grok 4.20 | 1.73% | 0.49×\* | 0.98× | 1.95× |
| Opus 4.8 | 0.67% | 0.55×\* | 1.00× | 1.94×\* |
| **ensemble** | 0.35% | **0.69×\*** | 1.00× | **1.61×\*** |

General catastrophe: 0.93\* / 0.89 / 0.86† / 0.66 / 0.70\* (ensemble
**0.86×\***) — 1.00 everywhere — 1.14\* / 1.15 / 1.26† / 1.60 / 1.50\*
(**1.26×\***). Disempowerment: 0.78\* / 0.66\* / 0.86† / 0.45\* / 0.53\*
(**0.66×\***) — 1.00 (Grok 0.98) — 1.35\* / 1.73 / 1.26† / 1.91\* / 2.05\*
(**1.73×\***).

Three things hold across all five. (1) The own-median world reproduces the
unconditional: 0.98–1.00× on every headline cell for every model — the
coherence check the design was built around passes for the whole panel.
(2) The quartile worlds are a near-symmetric multiplier around it, with the
size a model trait: Fable 5 is the tightest (0.85× / 1.25×), Grok and Opus
the widest (≈0.5× / ≈1.9–2×), GPT-5.5 and Gemini between. (3) Gemini
applies one factor to everything — 0.86 / 1.00 / 1.26 on all three cells,
to the hundredth — as Fable 5 did in the pilot, and it searched nothing.

**Unconditionals across instruments** (AI catastrophe 2030, mean over
repeats; policy instrument n=10 per model): Fable 5 0.19 / 0.18 / 0.22%
(policy / fixed ECI / self +6mo), GPT-5.5 0.21 / 0.36 / 0.35, Gemini 0.05 /
0.22 / 0.01, Grok 1.31 / 1.00 / 1.73, Opus 0.68 / 0.50 / 0.67. The ensemble
median reads 0.21 → 0.35% only because GPT-5.5, the median model, moved
from 0.21 to 0.35 — a shift inside its own repeat spread; within a model
the three instruments agree to within noise except Gemini (0.05 → 0.01, on
a base of a few hundredths of a percent) and Grok (1.31 → 1.73).

## The Capability tab (index.html, 2026-08-28)

`?tab=capability`. Two graphs, from `redlines/views/capability.py`
(`python3 -m redlines build --views capability`, mirror
`results/capability_data.json`). (1) The frontier ECI: the history the
models were shown (every US release that set a new high, GPT-4 → Fable 5),
metr_graph's p25–p75 band and p50 line (the seeded replica, never shown to
the model) from the anchor — the last frontier point, where the projection
starts: its fitted value there, 162.1, sits on Fable 5's 162.5, so the cone
grows out of the history (`data/eci_trend_2026-08-21.json` runs from that
day) — clipped to a few months past the target, and each model's own p25 /
p50 / p75 at its target date. The chart draws ONE mark per variant, a box
plot of the ensemble (box = the median across models of p25 and of p75,
line = the median of the medians), not a whisker per model side by side —
five stacked whiskers read as five different dates (decided 2026-08-28).
There is no table of numbers under the chart (same day); the
per-model and trend numbers are in `results/capability_data.json`
(`variants[].forecast`) and in the results sections above. Legend: "frontier
ECI", "model's forecast of frontier ECI, 25–75th percentile", "METR trend
(Peter Wildeford)" linking to the app. One variant for now, six months out; the end-of-2030
instrument's results stay above and in `results/`, off the tab until asked
for (`VARIANTS` in the view is the switch). (2) The
questions conditional on progress: the Policy-levers chart, unchanged —
`CondDeltaChart` / `CondDeltaTable` / `CondText` took a `ctx` so one
component draws both tabs — with the model's own 25th / 50th / 75th
percentile worlds as the rows (`ECI ≈ 166 / 170 / 174`) and the same
unconditional line, band and CIs. With more than one variant a toggle on
the ECI chart selects which instrument feeds the rows; `?cap=`, `?q=`,
`?h=` deep-link. The rows are the latest elicitation day's, pooled,
as on the policy tab; the model legend lists only the models that ran.
`code/publish_dashboard.sh` builds it with the rest.

## One instrument for both: policy and capability conditions (2026-08-28, built, not yet run)

The project lead asked (2026-08-28) for a single survey instrument that
encompasses both the capability and policy conditions, without policy ×
capability cells: policy questions assume the median ECI trajectory,
capability questions assume whatever the unconditional policy is.

Yes. `data/combined_conditions.json` (`code/make_combined_conditions.py`, from
`data/leap_policies.json` + `data/eci_self6mo_conditions.json`) is a **grouped
condition set**: one call per model answers every cell **twelve** times —
unconditionally, under each of the eight LEAP policies, and under each of the
model's own three capability percentiles — 210 × 12 = 2,520 probabilities
(1,890 on the policy instrument, 840 on the capability one). The runner renders
a grouped set as one CONDITIONS section with the ECI definitions and Step 1
(the model's own p25/p50/p75 for the frontier ECI six months out) first, then
the key list and the unconditional line, then a **POLICY CONDITIONS** section
and a **CAPABILITY CONDITIONS** section, each with its own component's
instruction, definitions and horizon line verbatim, plus one sentence of ours
saying what that section holds the *other* quantity at:

- **Policy conditions** sit on the model's own **median capability trajectory**:
  "the frontier ECI on {target_date} is approximately your 50th-percentile value
  from eci_forecast … the same level as condition eci_p50." LEAP's clause already
  says "hold other factors constant"; this says what constant means for
  capability. The like-for-like baseline for a policy delta is therefore
  `eci_p50` rather than the unconditional — and on 2026-08-28 every model's
  own-median world reproduced its unconditional to 0.98–1.00×, so the two agree
  to within noise and the tabs keep reading against the unconditional.
- **Capability conditions** assume **no policy condition**: "As in the
  unconditional forecast, assume whatever AI policies you expect to be
  implemented — not any of the conditions in the POLICY CONDITIONS section."
  The capability instruction is still the fact-learned one (update everything
  that would accompany that level, governments' response included), so the
  expected policy response to a capability level is part of the world, not held
  fixed. That is the reading of "whatever the unconditional policy is" that
  keeps the capability set as designed; the alternative — freeze policy at the
  unconditional expectation — would contradict that instruction and is not what
  the file says. **The project lead is to confirm this reading.**
- The head of the prompt and the key list both say every condition stands
  alone; no cell combines a policy with a capability level.

What is composed and what is authored is written into the file (`notes.authored`)
and checked: the eight LEAP items render **byte-identically** to the policy
instrument's (`tests/test_conditional.py::TestCombinedSet`), the policy
instrument's own block and prompt SHAs are unmoved, and the component files
are pinned by content so `--check` fails the day either is regenerated.

Protocol `unified-joint-combined-v1` (v2 since 2026-09-02: same questions and
conditions, elicited through the agentic harness — `docs/methodology.md`,
"Grounding"; the tabs show the newest tag present and fall back to v1 until a
v2 run lands), slug `combined`. It is a **different
instrument** from both components — an unconditional answered beside eleven
conditions and an ECI forecast is not the one answered beside eight policies —
so its unconditional slice is its own series: the runner writes it to
`results/combined_runs/<stamp>.jsonl` (until the evening of 2026-08-28, when the set became the published one and the slice moved to `results/runs/`) and the whole instrument to
`results/conditional_runs_combined.jsonl`, never into `results/runs/` or
`results/conditional_runs.jsonl`. Rows stamp `condition.group` (`policy` /
`capability`) and the group's own source.

```sh
python3 code/make_combined_conditions.py --check                                   # JSON is current
python3 code/run_unified.py --joint --scenarios data/combined_conditions.json --dry-run   # read the prompt
# on the box: the pilot, the panel x 3, ~2,520 probabilities per call
python -u code/run_unified.py --joint --repeats 3 --workers 2 \
    --scenarios data/combined_conditions.json --experiment combined-pilot
python3 code/analyze_conditional.py --scenarios data/combined_conditions.json      # all eleven, per model + ensemble
```

### Results — pilot, 2026-08-28 (runs `2026-08-28T2158Z` + fill `2026-08-28T2314Z`; the ECI panel × 3, 13 calls)

The panel (Fable 5, GPT-5.5 Pro, Opus 5, GPT-5.6 Sol — `--model-set eci_topk`,
its first outing), three repeats, `--workers 2`, 2,520 probabilities a call on
the v2 grid. 11 of 12 calls in ~72 minutes; GPT-5.5 Pro's second was lost to
litellm's 600 s connection timeout (an exception, which the grid-retry never
sees — `REDLINES_LLM_TIMEOUT` exists since), and was re-run alone at 1,800 s
(one attempt, 25 min). Two empty-grid retries (Opus 5 #2, Pro #3) recovered.
`python3 code/compare_combined.py` reproduces every number below against the
same-day single-purpose instruments: the ECI top-4 arm (the SAME four models,
policies only, ×5), the frontier five's policy instrument (v1 ×5, v2 ×4–5) and
the six-month capability instrument (frontier five, ×3).

**The unconditional did not move where it is AI-specific.** Ensemble medians,
combined vs the top-4 arm: AI catastrophe 0.33 % vs 0.33 % at 2030, 3.58 % vs
3.53 % at 2050; expected loss (AI) 4.59 M vs 4.68 M / 49.0 M vs 50.8 M;
misalignment 2.40 M vs 2.42 M / 32.9 M vs 33.2 M. The two cells that did move
are the non-AI-specific ones at 2030: general catastrophe 0.73 % vs 1.24 % and
disempowerment 0.47 % vs 1.12 %, driven by GPT-5.5 Pro (0.52× / 0.29×) and
GPT-5.6 Sol (0.46× / 0.38×) coming down; Opus 5 ~1×, Fable 5 0.67× / 0.77×. The
2030 noise floor is ×2.2, so this is at the edge of what three repeats can
call — worth a look on the next run, not a conclusion.

**Policy ratios agree with the policy-only instrument** to a few hundredths on
every condition, same ordering. AI catastrophe 2030: status quo 1.09× vs 1.16×,
P3b 0.67× vs 0.66×, P5 0.46× vs 0.45×; 2050: 1.15× vs 1.23×, 0.62× vs 0.59×,
0.40× vs 0.38×. The one systematic difference is the status-quo premium,
0.07–0.08 smaller in the combined call at every cell. **Read against
`eci_p50` instead of the unconditional the numbers are the same**, because
`eci_p50` is 1.00× the unconditional for every model again (Pro 0.97×) — the
own-median world reproduces the unconditional here too, so the "policy on the
median trajectory" framing costs nothing.

**Capability factors, Fable 5 like-for-like** (the one model on both panels),
combined vs the six-month instrument: 0.89× / 1.13× vs 0.85× / 1.25× at 2030,
0.92× / 1.07× vs 0.92× / 1.12× at 2050 — the same shape, a touch narrower. The
panel ensemble is 0.79× / 1.29× (2030) and 0.80× / 1.26× (2050) against the
frontier five's 0.69× / 1.61× and 0.71× / 1.48×: narrower because Grok 4.20 and
Opus 4.8, the ≈0.5× / ≈2× models, are not on the panel, not because of the
instrument.

**ECI forecasts for 2027-02-28** (p25/p50/p75, median over calls): Fable 5
166 / 169 / 173 (166.5 / 170 / 174 in the standalone instrument), GPT-5.5 Pro
166 / 170 / 176, Opus 5 166 / 169.5 / 174, GPT-5.6 Sol 164.5 / 168 / 172 —
every median 3–5 under the trend's 173.2, as on the standalone run.

So: asking both at once changes none of the three published readings beyond
the re-run noise, at a third more output per call than the policy instrument.

**The tabs read it (2026-08-28 evening).** Both tabs take the instrument with
the newest elicitation day: `redlines/views/conditional.py::SOURCES` lists the
combined log's policy group ahead of the LEAP log, `capability.py::VARIANTS`
the combined log's capability group ahead of the standalone six-month set;
`redlines.conditional.group_view` / `group_rows` present one group of a
grouped set as the plain set it was composed from, so nothing downstream
changed. The page shows the group's own instruction and, under it, the one
assumption sentence of ours ("Also assumed (ours, in the single instrument)"),
and the policy tab's run line says it was elicited in one call with the
capability conditions. Newest day wins, so the Friday cron — still on the
policy instrument — will take the policy tab back the next time it runs,
while the capability tab stays on the combined pilot until a newer capability
elicitation exists. Left: the project lead's confirmation of the capability-side reading
(above), whether the 2030 general/disempowerment dip repeats, and whether the
cron moves to `--scenarios data/combined_conditions.json` — which also
means deciding that its unconditional slice is the published series, since
the runner keeps a non-published set out of `results/runs/`.

## The axes instruments: risk against an x-axis quantity (2026-09-03, built for the 2026-09-04 run)

The FRI economist's spec (2026-09-02): the dashboard shows catastrophic risk **conditional
on a quantity the reader can put on an x-axis** — the frontier ECI, the
combined OpenAI + Anthropic revenue run-rate (LEAP Wave 11) and the year of
"Expert AGI" (LEAP Wave 8) — with the panel's own forecast of each quantity
and the LEAP superforecasters' answer overlaid. The paper adds three more
LEAP quantities: US real-GDP growth and labor-force participation (Wave 6)
and the longest METR 80% time horizon (Wave 8). The LEAP Wave 3
"open vs proprietary" benchmark question was dropped the same day: it is a
four-benchmark mean, not ECI, and mapping one onto the other would be an
invented conversion.

**Two sets, two more calls per model.** `data/axes_conditions.json` (slug
`axes`, protocol `unified-joint-axes-v1`: revenue, AGI year, ECI; 16
conditions) and `data/paper_axes_conditions.json` (`paperaxes`; GDP, LFPR,
METR; 15 conditions), both from `code/make_axis_conditions.py`. Each is its
own instrument in the runner's sense: rows go to
`results/conditional_runs_<slug>.jsonl`, the unconditional slice to
`results/<slug>_runs/`, never to `results/runs/`. The cron runs them after
the combined instrument and before the publish.

**Three horizons only.** The sets carry `horizons: ["2030", "2050", "2100"]`
and the runner narrows the batch to them (`run_unified.set_horizons`): 35
questions × 3 = 105 cells × 17 keys = 1,785 probabilities (1,680 for the
paper set), the same order as the published call. A level fixed at end of
2030 says nothing a six-month cell should be read under, and the whole grid
would not fit one submission.

**Fixed levels, from a reference distribution — not round numbers** (decided
2026-09-02, from first principles). A level means
something only relative to what people expect, so:

| axis | reference | levels |
|---|---|---|
| revenue, end 2030 ($B, 2026 USD) | superforecasters' median p10 / p50 / p90 (n=53), extended one log step each way | 75 · **150 · 300 · 500** · 830 |
| Expert AGI, first year | superforecasters' median p5 / p25 / p50 / p75 / p95 (n=55) | **2030 · 2036 · 2045 · 2060 · 2090** |
| frontier ECI, run date + 6 months | the trend fit (`data/eci_trend_2026-08-21.json`, 15.3 pts/yr from 162.06 on 2026-06-09) at 0× / 0.5× / 1× / 1.5× / 2× / 3× the pace to the reference target 2027-03-04 | 162 · 168 · **173** · 179 · 185 · 196 |
| US real-GDP growth 2025→2030 (%/yr) | supers' p10 / p50 / p90 (n=54), linear step | −0.5 · **1.0 · 2.5 · 4.3** · 6.1 |
| US LFPR, Jan 2030 (%) | supers' p10 / p50 / p90 (n=54), linear step | 54.0 · **58.0 · 62.0 · 65.1** · 68.2 |
| longest METR 80% horizon, 2026-12-31 (h) | supers' p25 / p50 / p75 (n=54), log step | 1.3 · **2.1 · 3.5 · 5.5** · 8.6 |

Bold = a LEAP superforecaster percentile (median across panelists of that
percentile). The ECI date is six months out because that is what the
Capability tab conditions on and what the self-forecast can be scored
against when the six months elapse (decided 2026-09-02); at that date 165–200
would have put most of the grid in a tail, so the levels are pace multiples
instead. The prompt shows the number and a tolerance; where it came from is
in each condition's `chart` field and is never rendered. Levels are fixed
across runs so the scatter is comparable week to week; they are re-derived
(and the tag bumped) only when the reference moves.

**The model forecasts each axis first, in LEAP's percentiles.** `elicits`
(plural; the runner's `set_elicits`) — revenue p10/p50/p90, AGI
p_before_2100 + year p5/p25/p50/p75/p95, ECI p10..p90 (A4: the whiskers),
GDP and LFPR p10/p50/p90, METR p25/p50/p75 — each rendered inside its own
section after LEAP's definitions, each stamped on the rows under
`elicited.<key>`. The percentiles are LEAP's so the overlay is a
like-for-like comparison with the superforecasters, not a translation.

**LEAP's words, from the warehouse.** `code/pull_leap_axes.py` vendors each
question's text, background, resolution criteria, unit and the panel
distributions (superforecaster / expert / public; `scenario_id is null`,
current and non-excluded responses) into `data/leap/axes-2026-09-02.json` (internal, not published; `data/leap_reference.json` carries the aggregates the page shows),
pinned by content in the sets' `source.leap.sha256`. The generator strips
the export's bold/italic markers and no-break spaces and nothing else.

**LEAP's forecast of the ECI (2026-09-03).** The same file carries Wave 5's
"U.S. versus China Polarity" question (`eci_us`, `eci_cn`: the
top-performing American and Chinese system's ECI at end-2026, end-2030 and
end-2040, each panelist's p25/p50/p75), which the FRI economist pointed at after the
axes work had concluded no human panel had forecast the ECI. The
superforecasters' medians for the top US system: 161 / 169 / 176 at
end-2026, 185 / 205 / 240 at end-2030, 225 / 310 / 400 at end-2040 (n=55).
`redlines.views.capability.leap_eci` reads it; the frontier chart draws the
end-2026 box beside the models', and the ECI axis carries it as the LEAP
superforecasters' x (their diamond sits at 169, two months before the
axis's own six-months-out date, which the legend names). The levels of the
ECI axis are still the METR trend's -- setting them from LEAP, as the
revenue and AGI levels are, would change the instrument.

**Conditioning clause.** The fact-learned one, per axis: "assume that
[quantity] takes the stated value … update your expectations about
everything that would ordinarily accompany it". Each section says the other
axes are unconditioned ("assume whatever you expect, as in your
unconditional forecast"); no axis is ever crossed with another.

**Combined set, A4.** The published set's Step 1 now asks five ECI
percentiles (p10..p90) instead of three; its conditions are still the
middle three. Same tag (`unified-joint-combined-v2` had not run yet).

**Harness v3 (2026-09-02 evening).** After the day's full run under v2, the
loop changed: the grid arrives in pieces (`submit_cells`), Tavily searches at
advanced depth, and rows flag cited-but-unread sources. (Reasoning stays at
"max": for the Claude 5 family litellm sends that as adaptive thinking at
Anthropic's top effort -- the 16k "alias" reading was wrong, see
docs/methodology.md.) Tags:
`unified-joint-combined-v3`, `unified-joint-axes-v2`,
`unified-joint-paperaxes-v2` (docs/methodology.md, "v3"). The views follow
the lineage, so the 2026-09-02 rows stay visible until the first v3 run.

**The scatter (C11/C12, built 2026-09-02 evening).** `redlines/views/axes.py`
→ `web/demo/78-axes.jsx`, on the Capability tab under the ECI panels: per
question and horizon, a dot per model at each level with a line through
them, the panel median, each model's unconditional as a hollow dot placed at
its own median forecast of the quantity, and under the axis the LEAP
superforecasters' whiskers (p10–p90 or p5–p95) beside the models' own. Axis,
question and horizon toggles; `?tab=capability&axis=revenue&q=…&h=…`
deep-links. Verified in headless Chrome on the Fable 5 smoke rows.

**Smokes, 2026-09-02.** Fable 5 on the dashboard set: 595 rows, 7 turns, 12
searches + 2 reads, $7.85; own forecasts revenue p50 $500B (supers $300B),
AGI year p50 2049 (supers 2045), ECI p50 172 (trend 173). GPT-5.6 Sol on the
paper set: 560 rows, 7 turns, 22 searches + 22 reads, $1.35; GDP p50 2.1%
(supers 2.5), LFPR 61.2 (62.0), METR 5.0 h (3.5). Every conditional moved
monotonically with its level. One caveat for the comparison: both models
found and read LEAP's public wave reports (leap.forecastingresearch.org)
during research, so the "own forecast" is informed by the superforecasters'
published answers rather than independent of them.
