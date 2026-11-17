# Cyber replay and launch limitations — September 10, 2026

The complete replacement snapshot uses `airo-incidents-prospective-v1`. All four models answered each of the three instruments on the same UTC elicitation date. Forecasts remain model judgments; the checks below establish data integrity, arithmetic and stated scope, not calibration.

## What changed in the question

Count new qualifying incidents beginning on or after September 10, 2026 and by the stated deadline. The 12-month onset interval ends September 10, 2027; the 2030 interval ends December 31, 2030. Each eligible incident contributes its first three years of harm, including harm after that deadline. A cyber campaign begins with its first malicious action against a target. Adding AI, tools or victims does not alone start a new campaign. The [accepted specification](counting-rules-specification-2026-09-10.md) supplies the full rule.

## Cyber results

| Model | 10k deaths/morbidity OR $22B; onsets in 12 months | 100k deaths/morbidity OR $220B; onsets through 2030 | Top two rungs’ share of 12-month expected-loss summary |
|---|---:|---:|---:|
| GPT-6 Astra | 14.9% | 16.1% | 74.8% |
| Opus 5 | 55% | 42% | 74.3% |
| Fable 5.1 | 25% | 38% | 67.1% |
| GPT-5.5 Pro | 7.5% | 9% | 84.2% |
| **Unweighted median** | **20%** | **27.1%** | — |

The unrounded medians are 19.975% and 27.05%. The earlier September 8 medians were 35% and 36%, under the earlier incident definition. The revised run also differs in date and sampling variation, so the difference is not an estimate of the effect of changing counting rules alone. Old probabilities and definitions remain archived.

## What passed, and what did not

- **Integrity:** 12 successful model/instrument runs; 6,580 rows and 25,620 probability cells; no missing or duplicate cells, invalid probabilities, mismatched dates, or prompt-replay failures. All seven frozen elicitation inputs still match their pre-run hashes. The 24 historical raw files were preserved.
- **Comprehension:** all 32 stipulated eligibility classifications passed (eight per model). This tests understanding of the examples, not numerical forecast quality.
- **Cyber replay:** all 10,271 checks pass, including unconditional and main-instrument conditional cyber ordering, parent containment, medians, threshold conversion and an independently reconstructed expected-loss formula. Graph 2 stores probabilities to four decimal places in percentage points; mirror comparisons allow half a displayed unit per model and one unit for the twice-rounded median. Raw logical checks retain their strict tolerance.
- **Broader coherence:** 33 conditional containment violations remain: 18 in the main instrument, ten in dashboard axes, and five in paper axes. Thirty-two are from GPT-5.5 Pro and one from Fable 5.1. The largest is 22% for misalignment versus 18% for the broader AI incident category at the one-billion rung, conditional on Pro’s own 90th-percentile ECI and through 2100. The five paper-axis errors are cyber probabilities exceeding the broader AI probabilities by 0.1 percentage point. No unconditional ordering violations were detected. No probabilities were edited or successful calls rerun to select a preferred result.

## Interpretation for launch

The exact onset and campaign rules are now explicit. The lower monetary thresholds have relevant historical fraud and breach anchors, but the shared rationales do not quantitatively derive the prospective campaign-loss distribution from those sources. See the [primary-source review](cyber-source-review-prospective-2026-09-10.md). The FRI human-study comparison remains contextual because its thresholds, pathways and access assumptions differ.

The two extreme rungs still contribute about 67–84% of each model’s 12-month expected-loss summary. The revised counting rules do not establish that those tail probabilities are reliable. Keep the headline expected-loss panel de-emphasized; use death-OR-damage labels and preserve model disagreement and the conditional-coherence caveat. A deaths-only expectation cannot be recovered from these OR probabilities.

## Reproducible evidence

- [Full cyber replay](cyber-validation-prospective-2026-09-10.json).
- [Three-instrument integrity and coherence report](../results/validation/counting-prospective-2026-09-10.json).
- [History-preservation receipt](../results/validation/counting-promotion-2026-09-10.json).
- [Comprehension checks and frozen-input hashes](../results/validation/counting-comprehension-v1/).

Commands: `python code/validate_launch_run.py --date 2026-09-10 --out results/validation/counting-prospective-2026-09-10.json`; `python code/audit_cyber.py --run 2026-09-10T1844Z`.

Recorded successful forecast-call cost: **$230.88**, plus the separate comprehension diagnostic. The first two failed Fable core attempts predated retained diagnostic traces; their costs are unknown, not zero. These totals are not a complete provider or search-service invoice.
