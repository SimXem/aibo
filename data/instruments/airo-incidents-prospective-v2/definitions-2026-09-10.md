# Automated AI Catastrophic Risk Forecasting: Questions

*AIRO revision approved by Nick Merrill on September 10, 2026: incident onset windows begin at each elicitation; cyber campaign boundaries and onset are clarified. All other attribution, severity, accounting and cross-cutting definitions retain the August 31 wording. See docs/counting-rules-specification-2026-09-10.md.*

*Revision of 2026-08-31 (Bridget Williams, tracked changes in the shared doc, applied 2026-09-02 onto the 2026-08-18 text, which carries her 2026-08-19 notes): every dollar leg scaled to a $2.2M value of a statistical life, the damages window fixed at three years after onset, the shut-down heuristic dropped from the but-for test, the epidemic definition rewritten to name AI's role, the misalignment boundary shortened, and the overlap-of-categories clause moved to the shared question details. The doc keeps an "AI-related large-scale catastrophe (past study version)" beside the updated one; this file carries the updated definition -- the past-study wording is what the XPT panel answered. Her 1-billion-deaths row reads "$2.2 trillion" in the doc's Severity options and "$2 quadrillion" in its summary; at $2.2M per death it is $2.2 quadrillion, used here.*

See also: the Auto-ARC question workbook (data/auto-arc/questions-2026-08-31.xlsx)

# Summary

* **General large-scale catastrophe**  
  * Severity:   
    * 10% of population  
  * Dates:  
    * 2030  
    * 2050  
    * 2100  
* **AI-related large-scale catastrophe**  
  * Severity:   
    * 10% of population  
  * Dates:  
    * 2030  
    * 2050  
    * 2100  
* **Human disempowerment**  
  * Dates:  
    * 2030  
    * 2050  
    * 2100  
* **AI-related incidents:**  
  * Incident types:  
    * AI-related incident  
    * AI-related human-caused epidemic  
    * AI-related cyber incident  
    * Misaligned AI incident  
  * Severity:  
    * 100 deaths (or equivalent morbidity) or $220 million  
    * 1,000 deaths (or equivalent morbidity) or $2.2 billion  
    * 10,000 deaths (or equivalent morbidity) or $22 billion  
    * 100,000 deaths (or equivalent morbidity) or $220 billion  
    * 1 million deaths (or equivalent morbidity) or $2.2 trillion  
    * 10 million deaths (or equivalent morbidity) or $22 trillion  
    * 100 million deaths (or equivalent morbidity) or $220 trillion  
    * 1 billion deaths (or equivalent morbidity) or $2.2 quadrillion  
  * Dates:  
    * Within the next 6 months  
    * Within the next 12 months  
    * 2028  
    * 2030  
    * 2050  
    * 2100  
    * *For bio incidents: 2044*

# General large-scale catastrophe

What is the probability that any global catastrophe (deaths reaching at least 10% of the population alive at the start of the measurement window) will occur by each of the following resolution years \[2030; 2050; 2100\]?

**Question details**

* Catastrophe threshold and the measurement window: A catastrophe at the 10% level means that deaths attributable to the catastrophe (excess mortality, i.e., deaths beyond the baseline that would have occurred anyway) reach at least 10% of the population alive at the start of the measurement window.  
* The measurement window is any contiguous period of at most five years during which the attributable deaths accumulate to the threshold. The window must begin on or after December 31, 2025 and end on or before December 31 of the resolution year (2030, 2050, or 2100). A faster event; the five years is a ceiling on the span over which deaths are counted, not a required duration.  
* For a threshold to resolve positively, the deaths must arise from a single catastrophe or a single causally-linked chain of events, not from summing unrelated causes.  
* Data and disagreement: For fatality and population data, we will rely on broadly recognized sources (e.g., Our World in Data, the Economist, the United Nations). Where these disagree in ways that would change resolution, we will resolve by the majority opinion of a panel of experts in demographics and fields relevant to the specific catastrophe (e.g., epidemiology for a pandemic). If reasonable people disagree about whether the event occurred, the question resolves via the same expert panel.

# AI-related large-scale catastrophe

What is the probability that a global AI-related catastrophe (AI being the proximate cause, per the but-for standard, of attributable deaths reaching at least 10% of the population alive at the start of the measurement window) will occur by each of the following resolution years \[2030; 2050; 2100\]?

**Question details**

* The points above also apply to this question.  
* Artificial intelligence: Defined as the development of machines capable of sophisticated (intelligent) information processing (Dafoe 2018, AI Governance: A Research Agenda, p. 5 fn. 2).  
* AI as proximate cause (but-for standard): We consider AI a proximate cause of death under a but-for test: the event would not have occurred, or would have been counterfactually extremely unlikely to occur, but for the substantial involvement of AI.  
  * Examples that count: an AI-powered system directly killing people at the relevant magnitude; AI autonomously triggering a nuclear launch (including deaths from subsequent nuclear winter); AI being substantially responsible for creating a superweapon that later causes deaths at the relevant magnitude; AI acting autonomously in armed conflict and causing deaths at the relevant magnitude.  
  * Examples that do not count: AI assisting in targeting a weapon that humans could and would have launched anyway (the AI did not counterfactually enable the event).  
* There is no fixed time limit between the AI's involvement and the deaths. Creation of a superweapon may precede its use by years and still satisfy the but-for standard; the test is counterfactual materiality, rather than timing.

# Human disempowerment

What is the probability that disempowerment of humanity will occur by each of the following resolution years \[2030; 2050; 2100\]?

**Question details**

* Disempowerment of humanity is defined as a state where AI systems are the primary determinant of human events globally.   
* This could occur via an overt takeover, where an AI system takes control of global systems of power (such as national governments, international organizations, multinational corporations) and humans have no role in executing power. It could also occur if the majority of human events are determined by AI decision, even if humans are nominally in control but humans could not behave differently if they wanted to, for example because they do not understand the decisions well enough to make a decision, or they are coerced into certain actions due to threats or other means.  

# AI-related incidents and domain-specific incidents

Each of these questions takes the following form:

What is the probability that one or more \[***incident**: AI-related incident / human-caused epidemic / cyber incident / misaligned AI incident*\] cumulatively causes \[**severity**: *the death of more than X million people (or equivalent morbidity) or $Y economic damages*\] by \[***date**: each of the following resolution years*\]?

**Question details**

* Perfect-knowledge clause: Assume we have perfect knowledge of the cause of each event, the intent and identity of the actors involved (including whether an AI system was involved and in what role), and the technical attribution. We want your view on the damages resulting from these events, not on the probability that they would be correctly identified or attributed.  
* Incident categories could overlap; for example, a misaligned AI incident could also be counted as an AI-related cyber incident, provided such an incident met the defined thresholds for each category.

## Incident options

* AI-related incident  
* AI-related human-caused epidemic  
* AI-related cyber incident  
* Misaligned AI incident

**Incident definitions**

* AI-related incident  
  * An incident is considered “AI-related” if it would not occur, or not reach the severity threshold, but for the substantial involvement of AI.  
  * An AI-related incident could be an AI-related human-caused epidemic, an AI-related cyber incident, a misaligned AI incident, or a different type of AI-related incident.  
* AI-related human-caused epidemic  
  * This could include: pathogens released deliberately by malicious human actors who have used AI; pathogens deliberately created by humans using AI but released accidentally; or pathogens created and released entirely by AI without human involvement.  
* AI-related cyber incident  
  * A set of malicious cyber operations sharing a common perpetrator (an individual, group, or coordinated set of actors) and a common campaign or method, directed at a target or set of related targets within a bounded, contiguous period.   
  * Treat a campaign as a distinct, bounded operation, assessed by the continuity of its activity, targets and objectives. Sharing an actor or tools does not by itself merge separate operations. Adding victims, changing tools, adding AI, or receiving a new reporting label does not by itself create a new campaign from an ongoing operation.
  * Campaign onset is its first malicious action against a target, such as an intrusion or fraudulent solicitation. Planning and tool development alone do not establish onset. Discovery, first reported loss, later encryption, or first use of AI does not reset an earlier onset within the same campaign.
  * Qualifying AI contributions include (non-exhaustive): discovering or developing exploits or pathogen modifications; generating, adapting, or synthesizing malware or biological agents; conducting or scaling social engineering; autonomously selecting targets, propagating, or dispersing; and planning or orchestrating the operation. Routine, long-standing automation (e.g., conventional vulnerability scanners) does not qualify; the AI contribution must be non-trivial to the event's occurrence or scale.  
* Misaligned AI incident  
  * An incident in which an AI system behaves in a way that neither its developer nor its operating user intended or endorsed. This "neither" reading is deliberate and separates loss of control from misuse:  
    * Excluded (misuse): a user intentionally directs an AI to cause harm and it complies. The user's intent is served even if the developer's is not. If such an event involves a cyber attack, it belongs under the Cyber questions.  
    * Included (loss of control): the AI pursues objectives, takes actions, or produces outputs that diverge from what both the developer and the operating user wanted — e.g., an autonomous agent taking destructive actions no one authorized, specification-gaming with large real-world costs, or deceptive or manipulative behavior neither party sought.  
  * Boundary with ordinary failure: the incident should center on the AI system's own behavior or decision-making being the proximate cause, rather than a conventional software defect or an operator error. This line is not crisp; use your judgment and assume the perfect-knowledge clause lets us determine whether the AI was acting contrary to both parties' intent versus functioning as designed.  
  * The harm may arise from the AI acting directly, or from actions humans took in direct reliance on the AI's misaligned outputs; in either case the AI's behavior must be the proximate driver.

## Severity options

* 100 deaths (or equivalent morbidity) or $220 million  
* 1,000 deaths (or equivalent morbidity) or $2.2 billion  
* 10,000 deaths (or equivalent morbidity) or $22 billion  
* 100,000 deaths (or equivalent morbidity) or $220 billion  
* 1 million deaths (or equivalent morbidity) or $2.2 trillion  
* 10 million deaths (or equivalent morbidity) or $22 trillion  
* 100 million deaths (or equivalent morbidity) or $220 trillion  
* 1 billion deaths (or equivalent morbidity) or $2.2 quadrillion

**Severity definitions**

* The figure of \[X\] deaths refers to global excess mortality that is believed to be attributed to the incident(s).   
  * The deaths do not need to be directly attributed to the incident but if there is an alternative reason for excess mortality to increase in a location (e.g. due to conflict) then the excess mortality for that region will not be counted as deaths as a result of the incident. E.g., famine deaths that would not have occurred absent the incident would count, while deaths due to a conflict that likely would have occurred anyway would not.  
  * For this question to resolve positively, more than X million excess deaths attributable to the incident must occur within a 3-year period, beginning from the onset of the incident.  
  * In the absence of a published estimate, we will defer to the majority opinion of a panel of at least five experts to determine if this criterion has been met.  
* Equivalent morbidity is defined as roughly 10 QALYs per death, e.g. 100 million QALYs is intended to represent morbidity roughly equivalent to 10 million deaths.  
  * A quality-adjusted life year (QALY) is a measure used in health economics that combines both the length and quality of life, where one QALY equals one year lived in perfect health. It's calculated by multiplying the number of years lived by a quality score between 0 (death) and 1 (perfect health), allowing comparison of different health interventions' effectiveness.  
  * An estimate of QALYs lost due to the pathogen that is published in a peer-reviewed journal, or by an international organization such as the World Health Organization or World Bank, would be sufficient to resolve this question.  
  * In the absence of such an estimate, we will defer to the majority opinion of a panel of at least five experts to determine if this criterion has been met.  
* Economic damages: Economic damages refer to global economic costs attributable to the event, beginning from the start of the event and extending to three years after the event onset. These include:  
  * Direct economic losses — e.g., reduced productivity and income (commonly estimated as a reduction in GDP); costs of response, remediation, recovery, and decontamination; destroyed or unrecoverable data and hardware; ransoms paid; medical and public-health response costs; regulatory penalties tied to the event.  
  * Monetized mortality, using a value of a statistical life (VSL) of $2.2 million, regardless of the geographic distribution of fatalities.  
  * Exclude purely notional losses such as declines in market capitalization or share price that do not correspond to real resource costs. Give all estimates in 2026 USD.  
* Resolution sources: Assume access to authoritative assessments, which may include estimates from the WHO, World Bank, IMF, national cybersecurity agencies (e.g., CISA, ENISA), major insurers and reinsurers, incident-response and threat-intelligence firms, and academic epidemiological and economic-modeling groups. Where multiple analyses exist, we will use the consensus or median; absent that, we will defer to the majority opinion of a panel of at least five experts.

## Date options

* 2028  
* 2030  
* 2050  
* 2100  
* *For bio incidents: 2044*

**Date details**

* Count only incidents whose onset falls within the specified counting interval, beginning on the elicitation date. All dates refer to UTC calendar dates, inclusive of the stated start and end dates.
* For six- and twelve-month horizons, the interval ends that many calendar months after the elicitation date. For a fixed-year horizon, it ends on December 31 of the named year. The exact start and end dates are supplied with this forecast. Every later elicitation starts a new counting interval; there is no permanent project-start or calendar-year baseline.
* Exclude incidents that began before the interval, including their later harms. New reporting, additional losses or later AI involvement does not by itself establish a new incident onset.
* For each eligible incident, count attributable mortality, equivalent morbidity and economic damages within its first three years after onset, under the severity definitions above. Harm after the interval's end date can count if it falls within that incident's three-year harm window. The horizon is an onset deadline, not a deadline for all harm to occur.
* These date rules apply to all four incident categories only; the separate large-scale-catastrophe and human-disempowerment questions retain their own date criteria.

## Suggested incident questions for humans 

* For each incident type:  
  * 2028  
    * 1,000 deaths  
    * 1 million deaths  
  * 2030  
    * 1 million deaths  
  * 2050  
    * 1 million deaths  
  * 2100  
    * 1 million deaths  
    * 1 billion deaths  
* This comes to 24 questions. If combined with all large-scale catastrophe and human disempowerment questions it’s a total of 33 questions.