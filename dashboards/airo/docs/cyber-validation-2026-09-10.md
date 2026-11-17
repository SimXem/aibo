# AIRO cyber validation — September 10, 2026

**Assessment: arithmetic verified; publication interpretation needs correction; magnitude validation remains qualified.** The 35.5% cyber forecast for 2030 is for **100,000 deaths (or equivalent morbidity) OR $220 billion in economic damages**, accumulated across qualifying incidents. It is not a 35.5% forecast of 100,000 deaths. All four incident ladders have the economic-damage alternative. The existing labels materially misstate the question.

**Later September 10 update:** this is the audit of the September 8 snapshot. Its label fixes have since been deployed, and the project lead accepted the [prospective counting specification](counting-rules-specification-2026-09-10.md) for a new instrument. The evidence-retention statement below was corrected after inspecting the full model calls: retrieval results were present on each call's first row, not missing. The numerical audit findings are unchanged.

## Scope and reproducibility

Inspected the local checkout at base commit `812fd841e4ff31ba23674f530d6c95632c7ffe74`, the latest local run `2026-09-08T1717Z`, all four current models, all eight cyber rungs and six horizons, and all 13 additional policy/capability arms. This is not verification of the deployed website or a newer remote run. No forecasts were re-elicited or changed.

- [Replayable audit](../code/audit_cyber.py): `python3 code/audit_cyber.py > docs/cyber-validation-2026-09-10.json`
- [Machine-readable evidence](cyber-validation-2026-09-10.json): input hashes, full probability table, individual expected losses, complete saved model rationales and cited URLs, and every failed check. The command deliberately exits 1 because it detects the conditional inconsistencies described below; it still writes the complete report.
- [Raw unconditional run](../results/runs/2026-09-08T1717Z.jsonl), [combined instrument](../results/conditional_runs_combined.jsonl), [question specification](../data/autoarc_ladder.json), [source definitions](../data/auto-arc/definitions-2026-08-31.md).

## What was actually elicited

The same deaths-or-damages severity options apply to AI incidents, bio, cyber, and misalignment. The conversion is **$2.2 million per death-equivalent**, not the obsolete $10 million rate. Death-equivalents also include morbidity at approximately ten QALYs per death. Economic damages include direct losses and monetized mortality, exclude merely notional market-cap losses, and use 2026 dollars. The criteria count harm over three years after incident onset; a displayed horizon is an onset deadline, not necessarily the date by which all harm has accumulated.

The questions explicitly permit one or more incidents to accumulate toward a threshold. A cyber incident is a campaign/method by a common perpetrator or coordinated actors within a bounded period; the question can aggregate multiple such incidents. Categories overlap, and “Any AI-related incident” also includes pathways beyond the three named subcategories. Domain probabilities therefore are not additive components of a total.

The source defines AI-relatedness counterfactually: without substantial AI involvement the incident would not occur or would not reach the threshold. Cyber-specific criteria additionally exclude routine longstanding automation and require a non-trivial AI contribution. A report describing AI involvement is evidence to assess, not automatic proof that the counterfactual test is satisfied.

The runner sends question text, criteria, severity definitions, perfect-knowledge/overlap rules and dated rolling horizons (`code/run_unified.py`, `build_prompt` / `build_prompt_joint`). There is no explicit lower onset boundary in the shared date criteria. “Within 12 months” suggests a prospective window, while two rationales describe low thresholds as already met. Clarify whether past incidents or ongoing campaigns qualify before interpreting that reasoning as either correct or erroneous.

## Reproduced headline probabilities

Percentages below are raw model answers and their unweighted median. “12 months” ends September 8, 2027 in this run. Each threshold includes the morbidity alternative.

| Cyber event | Astra | Fable 5.1 | Opus 5 | GPT-5.5 Pro | Median |
|---|---:|---:|---:|---:|---:|
| 10,000 deaths OR $22B, within 12 months | 28% | 24% | 50% | 42% | **35%** |
| 100,000 deaths OR $220B, within 12 months | 4% | 4% | 11% | 6% | **5%** |
| 10,000 deaths OR $22B, by 2030 | 85% | 66% | 82% | 90% | **83.5%** |
| 100,000 deaths OR $220B, by 2030 | 35% | 27% | 36% | 42% | **35.5%** |

All 192 unconditional cyber cells are present and bounded, increase or stay constant with time, decrease or stay constant with severity, and stay below their AI-incident container. All displayed cyber model points and medians match the raw run. The combined instrument's unconditional slice matches the published run. No percentage scaling, median, or threshold-conversion error explains the high headline.

The 13 additional arms contain **12 small containment violations**, all Opus 5 at the lowest rung in 2050/2100: cyber exceeds the AI container by 0.01–0.02 percentage points. These do not affect the unconditional medians above. The evidence JSON identifies each cell. Retain them as audit findings rather than silently correcting elicited answers.

Historical local medians are also variable: the $22B/10k 12-month cell is 46% on Sept 2, 28.5% on Sept 4, and 35% on Sept 8; the $220B/100k 2030 cell is 37.5%, 23%, and 35.5%. Panel membership changes on Sept 8 and the same models also move. This is not a controlled estimate of news effects or repeatability.

## What the rationales support

Each model has **one shared rationale for the whole instrument**, copied across its question rows. None supplies a cyber-specific distribution derivation or a quantitative justification of every tail rung. **Correction:** retrieval results are retained once per model call, on its first row: Astra 15, Fable 5.1 21, Opus 5 28, and GPT-5.5 Pro 60 tool results. The original audit incorrectly inspected only a cyber question row and reported empty evidence. The full retained searches and page reads are available for inspection; the script and evidence JSON now count the whole call. I checked selected consequential anchors against primary sources, not every factual claim in those retrieval traces or the four full rationales. The absence of a quantitative tail derivation in the shared rationale is a narrower finding than absence of retained evidence.

| Model | Cyber reasoning actually saved | Assessment |
|---|---|---|
| Astra | Distinguishes cumulative financial harm from death labels; mentions cybercrime base rates, defensive adaptation and sparse autonomous-malware evidence. Explicitly interprets horizons prospectively with three-year harm accounting. | Correctly recognizes the economic leg; little numerical bridge from observed losses to severe tail probabilities. |
| Fable 5.1 | Anchors low rungs in reported AI-related fraud and AI-enabled breaches; places middle rungs using broad accumulation or very large incidents. Says lower thresholds are already effectively met. | Economic interpretation is explicit; needs a prospective-start/counterfactual-attribution check. |
| Opus 5 | Uses fraud/breach statistics for low rungs, FRI worm forecasts and LEAP for middle rungs, and broad catastrophe forecasts for tails. | Most explicit external anchors; cross-question extrapolation and the very severe cyber tail are not quantitatively justified. |
| GPT-5.5 Pro | Contrasts large financial cyber losses with rare lethal bio/misalignment events; raises tails with capability growth and expert disagreement. | Recognizes financial losses, but offers the least specific numerical cyber justification. |

Two useful anchors check out in narrower forms. FBI IC3 records about **$893M in adjusted complaint losses with reported AI-related information in 2025**; these are neither a complete global estimate nor a counterfactual attribution study. [FBI 2025 IC3 report, p. 39](https://www.ic3.gov/AnnualReport/Reports/2025_IC3Report.pdf). IBM reports that one quarter of malicious breaches in its study were AI-enabled, averaging $6M. That supports financially material incidents but does not, by itself, identify global annual losses or the fraction satisfying AIRO's but-for criterion. [IBM release](https://newsroom.ibm.com/2026-07-29-ibm-study-one-in-four-malicious-breaches-are-ai-enabled%2C-costing-companies-6-million-on-average?lnk=hpln1id).

Opus's $30B global-loss assertion was not independently verified to a primary source. It should not be repeated as an established fact from this audit. GPT-5.5 Pro cites Lloyd's: its $3.5T figure is a hypothetical systemic payment-network scenario's modeled loss over five years, not observed annual AI-caused losses. It can illustrate a damage mechanism but cannot directly validate AIRO's probabilities or three-year accounting. [Lloyd's scenario](https://www.lloyds.com/insights/media-centre/press-releases/lloyds-systemic-risk-scenario-reveals-global-economy-exposed-to-3.5trn-from-major-cyber-attack).

## Human-forecast comparison: correct the condition before citing it

The published pilot gives baseline 2026 probabilities of a ≥$10B data-damaging worm of **8% experts / 5% supers**. Under **Capability 1** (AI enables 25% of moderately skilled hackers to develop elite exploits), with open-weight availability and no cyber safeguards, these become **41% / 15%**. Capability 2 is the Cybench threshold; the report distinguishes attaining it from establishing Capability 1. Grid baseline ≥$10B medians are **1% / 1%**. [FRI report, Tables 1 and associated results](https://forecastingresearch.org/research/ai-cyber-risks-capabilities).

Thus the question-set author's “40% / capability 2” comparison needs updating to the published version. Neither the unconditional nor the conditional human question matches AIRO: different monetary threshold, incident scope, aggregation, AI-attribution requirement, calendar window, and elicitation date. AIRO's scope is broader in some dimensions and narrower in others, so there is no justified probability ordering. The comparison is context, not a calibration test or a reason to replace 35% with a human number.

## Expected loss is the larger unresolved magnitude issue

The calculation is a lower-step approximation to a survival integral, implemented in `redlines/conditional.py::expected_loss`. Independently computing interval probability masses times their lower thresholds reproduces all 24 cyber model/horizon results. No current unconditional cyber ladder needs monotonicity repair.

If D is mortality/morbidity in death-equivalents and E is economic damages under the definition, the OR thresholds describe **L = max(D, E / $2.2M)**. The statistic is a floor on the expectation of this combined severity measure under the forecast distribution. It is **not expected deaths**. Multiplying it by $2.2M expresses the same measure in dollar-equivalents, not necessarily economic damages alone. The “floor” claim describes the numerical approximation, not a guarantee that true risk exceeds the estimate.

| Onset horizon | Median model loss floor, death-equivalents | Same measure in dollar-equivalents |
|---|---:|---:|
| Within 12 months | 124,826.75 | $274.62B |
| By 2030 | 2,190,030.7 | $4.818T |

**The top two rungs supply 72–84% of each model's 12-month loss floor.** Those rungs represent 100M deaths/$220T and 1B deaths/$2.2 quadrillion. For Opus, a 0.02% 12-month probability at the top rung alone contributes 180,000 death-equivalents via the final interval. The saved general rationale does not explain a concrete cyber mechanism at this severity on that timescale.

This is why validating the $22B event is insufficient to validate the expected-loss headline. The point estimates can be numerically coherent while the quantity that dominates the headline remains weakly supported. A deaths-only expectation cannot be recovered from these OR probabilities without additional elicitation or assumptions.

## Concrete handoff and launch recommendation

1. **D2: correct the existing labels before publication.** `web/demo/30-live-graph2.jsx` labels the axis “deaths caused by a single event” and the hover as only `hov.rung + " deaths"`; use the supplied full `r.label`/`hov.label`, show the monetary thresholds visibly, explain cumulative incidents and the onset/harm windows. A hover alone does not correct a misleading visible axis. Physical-death historical markers also need clear separation from the mixed severity measure.
2. **D2/P3: explain or de-emphasize expected loss.** Describe combined severity, the lower-step approximation and tail sensitivity. Correct the separate formatting defect in `redlines/views/graph1.py::_loss_question`: `:.0f` prints the $2.2M rate as `$2M`. The numerical calculation uses $2.2M correctly. Do not relabel the existing statistic as expected deaths.
3. **P2/P3: use the corrected human-study comparison above**, including the actual capability and access assumptions. Do not infer that observed Cybench progress places us in the 41% expert scenario.
4. **Team method decision: resolve counting ambiguities.** Specify the start date/onset eligibility for cumulative losses, how ongoing campaigns count, and how reported AI-assisted fraud maps to the counterfactual standard. Version any resulting instrument change rather than silently reinterpreting prior runs.
5. **Follow-up magnitude review:** request an explicit, sourced explanation of the $22B/12-month and $220B/2030 cells and of the two extreme rungs driving expected loss. A targeted diagnostic should separate mortality from damages, identify qualifying mechanisms, and distinguish restricted capability from broadly available capability. Keep such diagnostic answers separate from the canonical series unless the team adopts a rerun protocol.

My recommendation is to retain the raw probabilities as model forecasts with accurate definitions and clear uncertainty, while avoiding an expected-deaths headline. The current evidence does **not** establish that the cyber estimates are orders of magnitude wrong; it also does **not** clear their tail magnitudes as well-supported. If tail review cannot be completed before launch, de-emphasizing the derived expected-loss summary is the most direct way to address the unsupported part without inventing replacement forecasts. This is a recommendation, not a team decision or a shipped change.

## Verification outcome

The standalone audit evaluated 10,271 numerical checks, recording only the 12 conditional containment violations above. The unconditional cell, aggregation, conversion and loss-reconstruction checks passed. Existing generator, conditional, coherence, Graph 1 and Graph 2 golden tests: **84 run, 12 skipped, no failures** (`python3 -m unittest tests.test_autoarc_generator tests.test_conditional tests.test_coherence tests.test_build_golden.TestGraph1Golden tests.test_build_golden.TestGraph2Golden -q`). Existing resource warnings were emitted. The skips mean this is not an all-dependencies or live-site test. Dashboard source and forecast data were not modified by this audit.
