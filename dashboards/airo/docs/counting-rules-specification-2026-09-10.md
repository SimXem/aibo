# AIRO launch counting specification

The project lead accepted these three decisions in the September 10, 2026 walkthrough. This records that instruction, not a claim that every coauthor has reviewed the wording. Instrument identifier: `airo-incidents-prospective-v1`. This specification is prepared before replacement probabilities are elicited.

## Shared incident dates

For every incident-ladder question, count only incidents whose onset falls within the specified interval, beginning on the elicitation date. Six/twelve-month intervals end that many calendar months after elicitation; fixed-year intervals end on December 31 of the named year. State the actual dates and UTC convention in each elicitation and retain them in the forecast record. Use the same stated date across a model panel's batch. This is a calendar-date convention, not each provider response's completion timestamp.

Exclude incidents that began before the interval, including their later harms. For each eligible incident, retain the existing first three years of attributable mortality, equivalent morbidity and economic damages after onset. Harm can occur after the interval's onset deadline. Do not describe these as all losses occurring before that deadline.

The date rule applies to all four incident categories. It does not change the separate mortality-catastrophe or human-disempowerment definitions. An entire joint elicitation nevertheless receives a new instrument identifier because every model reads the changed questions together.

## Cyber campaign boundary and onset

A cyber incident remains a bounded campaign: a distinct operation assessed by the continuity of its activity, targets and objectives, under the existing actor/coordinated-actor definition. Sharing an actor or tools does not by itself merge separate operations. Adding victims, changing tools, adding AI, or receiving a new reporting label does not by itself split an ongoing operation into a new campaign.

Onset is the first malicious action against a target in that campaign, such as an intrusion or fraudulent solicitation. Planning and tool development alone do not establish onset. Discovery, the first reported loss, later encryption, or the first use of AI does not reset an earlier onset in the same campaign.

Retain the existing substantial-AI-involvement test, perfect-knowledge clause, deaths-OR-damages thresholds, cumulative scope, accounting conventions and resolution-source fallback. Broader changes to gross versus incremental harm or the attribution test were discussed but not adopted.

## Concrete cases

Each “include” answer below stipulates that all other incident and AI-involvement criteria are met. Dates are examples, not a permanent baseline.

| Facts, with elicitation on September 10, 2026 | Classification |
|---|---|
| Fraud campaign began in August; it adds a powerful AI system September 12 while continuing the same operation. | Exclude, even if the AI greatly increases its harm. |
| That established group launches a distinct hospital ransomware operation September 12. | Include; an established actor can launch a new campaign. |
| Intrusion occurred in August; encryption occurs September 12 in the same campaign. | Exclude; onset is the earlier intrusion. |
| A September 12 report newly reveals the August campaign. | Exclude; discovery does not establish onset. |
| A worm campaign began September 9 and reaches additional victims September 12 through continued propagation. | Exclude; additional victims alone do not create a new campaign. |
| Code was developed in August, but a distinct campaign's first malicious action against a target occurs September 12. | Include; development alone is not onset. |
| A qualifying incident begins December 30, 2030, with harm during its following three years. | Include in the September 10, 2026 “by 2030” forecast; retain only its first three years of harm. |
| The same September 12, 2026 campaign is assessed in a January 2027 elicitation. | Exclude from that new elicitation's windows, although it remains eligible for the archived September 10 forecast. |

## Implementation and publication

- Preserve the old source definitions, raw responses and prompt provenance. Never display old probabilities as answers to the revised rules.
- Version the source and generated question spec, attach the instrument identifier and actual dates to rows, and retain the exact prompt sent. Current views must not fall back to an older instrument simply because a new model/conditional forecast is missing.
- Check the classification cases in a separate model-comprehension diagnostic, then run the full joint instrument once per current model. Keep diagnostic material separate from canonical forecast history. Review completeness, coherence and cyber rationales before promoting new output.
- Keep historical versions accessible and mark the change in any incident timeline. Even within the new version, fixed-year forecasts cover advancing start dates; movement is not solely a change of belief about an identical event.
- Dashboard definitions/labels, manuscript methods/results and any blog/X numerical claims must be reconciled with the replacement snapshot. Expected-loss tail support remains a separate unresolved validation issue; these counting decisions do not establish that the tail forecasts are reliable.

## Implementation status — September 10

The revised source, generated question specifications and joint runner are implemented in this repository. Old definitions are archived under `data/instruments/legacy-2026-08-31/`. New rows retain the common UTC elicitation date, actual onset intervals, instrument version and exact user/system prompt. The source questions and prompt inputs were frozen before inspecting replacement probabilities.

All four current models passed all eight stipulated comprehension cases (32/32); results are in `results/validation/counting-comprehension-v1/`. The project lead authorized a full new forecast per model for the combined, dashboard-axis and paper-axis instruments. All twelve model/instrument runs completed in an isolated working directory on the cron box, dated September 10. The complete snapshot has 6,580 rows and 25,620 probabilities. Integrity checks pass; 33 conditional containment inconsistencies are retained and disclosed. No unconditional ordering violations were detected. Publication and manuscript/launch-copy reconciliation are in progress.

The current-view implementation requires the configured four models, all 35 questions and complete cells on a common elicitation date. It does not fill missing new results with old probabilities. Raw downloads preserve historical instrument versions. `code/validate_launch_run.py` checks all three replacement instruments, prompt replay, dates, completeness, grounding and coherence; `code/audit_cyber.py` independently checks cyber arithmetic and the dashboard mirrors.

Fable encountered two technical submission failures (first an unsupported forced-tool parameter, then no final submission at the loop limit). Its compatibility fix keeps reasoning enabled and the same scientific prompt, requests the final tool in automatic mode and allows two bounded submission-only continuation turns. Diagnostic traces are private, outside the public raw forecast bundle. Failed-run provider costs from before diagnostic capture are unknown and must not be reported as zero. Successful forecasts are not rerun to select preferred probabilities.
