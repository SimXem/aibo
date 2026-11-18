# Recursive self-improvement: forecasting survey

The Forecasting Research Institute (FRI) runs this survey on recursive self-improvement (RSI) in AI. In this survey, we ask you to forecast how far AI research and development (AI R&D) gets automated, and whether this accelerates AI progress.

## How to answer

The survey has 18 forecasting questions in 5 sections.

- For a yes-or-no question, give a probability from 0 to 100. If you think the probability is 25%, type 25.
- For a numeric question, give three values. P10: you think there is a 10% chance that the true value is below this number. P50: your median. P90: you think there is a 90% chance that the true value is below this number.
- At the end of each section, write a rationale: the main reasons for your forecasts, and what evidence would most change them.
- You can use any source. We want your all-things-considered forecasts.

## 1. Automation of AI R&D

These questions ask how much AI R&D work AI will do, and how well AI agents will do open-ended research. Definitions:

- AL5 is the top level of the AL0–AL5 AI autonomy scale that Anthropic uses to rate its AI R&D tasks: “*AI operates fully autonomously, with no human in the loop*” ([Anthropic](https://www.anthropic.com/institute/measuring-pace-of-ai-development)).
- A model is publicly available when anyone can use it, for example through a public API or a consumer app, possibly for a fee. We will date each model by the date when it first became publicly available, using Epoch AI’s dates where possible.
- The ECI frontier on a given date is the highest Epoch Capabilities Index (ECI) score of any model that became publicly available on or before that date ([Epoch](https://epoch.ai/benchmarks/eci)).
- The leading AI company on a date is the company whose model sets the ECI frontier on that date.
- A CRUX 2 re-run uses the setup of the original CRUX 2 open-world evaluation ([CRUX 2](https://arxiv.org/abs/2607.27191)) and the NeurIPS 1–6 scale ([NeurIPS](https://neurips.cc/Conferences/2025/ReviewerGuidelines)). In CRUX 2, an AI agent gets the research question of an unpublished AI paper (but not the paper itself), about a week, an API budget, and GPU credits, and must write a paper for a top AI conference. The original authors then grade each paper.

### Q1.1 AL5 share, end of 2027

**What share of AI R&D work at the leading AI company will AI do fully autonomously (AL5) on Dec 31, 2027?**

Answer: P10, P50, and P90, in percent (0–100).

Resolution: This question will resolve to the share (0–100%) of the leading AI company’s AI R&D work that AI does at AL5 on Dec 31, 2027.

- Share: the percentage of the company’s AI R&D work that AI does at AL5. We will fix the weight of each task at its share of the company’s research time in 2026. For example, if AI does at AL5 all the tasks that took 30% of research time in 2026, the share is 30%, even if those tasks now take much less human time.

Please forecast the true share that an independent study (for example, run by METR or Epoch AI) would measure. Since no such independent study existed when this survey opened (Nov 3, 2026), and the leading company may not publish AL5 data, this question is partly hypothetical. If the required data exist when the question resolves, we will use them. If not, we will aim to resolve the question with the best evidence available (which may include, for example, asking a panel of AI experts to estimate the share).

### Q1.2 AL5 share, end of 2030

**What share of AI R&D work at the leading AI company will AI do fully autonomously (AL5) on Dec 31, 2030?**

Answer: P10, P50, and P90, in percent (0–100).

Resolution: The same criteria as Q1.1, but on Dec 31, 2030. The leading AI company is the company that leads on Dec 31, 2030. For the reasons given under Q1.1, this question is partly hypothetical.

### Q1.3 CRUX 2 re-run score, end of 2027

**Imagine a re-run of CRUX 2 that starts on Dec 31, 2027 with the best publicly available AI agent on that date. What will be the average score of the agent’s papers, on the NeurIPS 1–6 scale?**

Answer: P10, P50, and P90, as NeurIPS scores (1–6).

Resolution: This question will resolve to the average overall score of the papers that the AI agent writes in the re-run.

- Setup: the same as [CRUX 2](https://arxiv.org/abs/2607.27191).
- Scale: the NeurIPS overall score, from 1 (“*Strong Reject*”) to 6 (“*Strong Accept*”) ([NeurIPS](https://neurips.cc/Conferences/2025/ReviewerGuidelines)).
- Best publicly available AI agent: the best publicly available AI model on Dec 31, 2027, in the best publicly available agent scaffold.
- Average score: the mean of the overall scores of all papers in the re-run.

Please forecast how expert reviewers would score the papers of the best AI agent at the end of 2027. Since such a re-run may not take place, this question is partly hypothetical. If the CRUX 2 team or another team runs a comparable study near Dec 31, 2027, we will use its results. If not, we will aim to resolve the question with the best evidence available on how well AI agents do open-ended research (which may include, for example, asking a panel of AI experts to estimate the results of such a re-run).

### Q1.4 Both automated AI R&D milestones by 2030

**What is the probability that both of these milestones happen by Dec 31, 2030?**

(a) The AL5 share of AI R&D work at the leading AI company is above 50%.

(b) In a CRUX 2 re-run that starts on or before Dec 31, 2030, the papers of the best publicly available AI agent have an average score of at least 4 (“*Borderline accept*” or higher).

Answer: a probability from 0 to 100.

Resolution: This question will resolve Yes if both (a) and (b) happen on or before Dec 31, 2030.

- (a) uses the definitions of Q1.1. The date of (a) is the first date on which the AL5 share is above 50%.
- (b) uses the setup, scale, and average score of Q1.3. The agent is the best publicly available AI agent on the start date of the re-run. If there is more than one re-run, the first re-run with an average score of at least 4 counts. The date of (b) is the start date of that re-run.

For the reasons given under Q1.1 and Q1.3, this question is partly hypothetical. If the required data exist when the question resolves, we will use them. If not, we will aim to resolve the question with the best evidence available (which may include, for example, asking a panel of AI experts whether both milestones have happened).

## 2. ECI frontier

These questions ask how fast AI capabilities will rise, as measured by the Epoch Capabilities Index (ECI; [Epoch](https://epoch.ai/benchmarks/eci)). Definitions:

- The ECI frontier on a given date is the highest ECI score of any model that became publicly available on or before that date.
- The two automated AI R&D milestones are the two events in Q1.4: (a) the AL5 share of AI R&D work at the leading AI company is above 50%, and (b) in a CRUX 2 re-run, the papers of the best publicly available AI agent have an average score of at least 4.

### Q2.1 ECI frontier, end of 2027

**What will the ECI frontier be on Dec 31, 2027?**

Answer: P10, P50, and P90, in ECI points.

Resolution: This question will resolve to the ECI frontier on Dec 31, 2027.

We will use the ECI scores that Epoch AI publishes ([Epoch](https://epoch.ai/benchmarks/eci)), and Epoch AI’s dates for when each model became publicly available. We will read the data on Mar 31, 2028, so that Epoch AI has time to score models that became publicly available near the end of 2027. If Epoch AI changes the ECI scale, we will convert the scores to the scale in use when this survey opened (Nov 3, 2026). If Epoch AI stops updating the ECI, we will aim to resolve the question with the best evidence available (which may include, for example, asking a panel of AI experts to estimate the ECI frontier).

Please assume that Epoch AI keeps adding new benchmarks that are not yet saturated, so that the ECI can keep rising as capabilities improve. If Epoch AI does not, we will aim to add such benchmarks ourselves and refit the ECI with Epoch AI’s public code.

### Q2.2 ECI frontier, end of 2030

**What will the ECI frontier be on Dec 31, 2030?**

Answer: P10, P50, and P90, in ECI points.

Resolution: The same criteria as Q2.1, but on Dec 31, 2030. We will read the data on Mar 31, 2031.

### Q2.3 ECI gain after both milestones

**If both automated AI R&D milestones (Q1.4) happen by Dec 31, 2030: how many ECI points will the ECI frontier gain in the 12 months after the date when both milestones have happened?**

Answer: P10, P50, and P90, in ECI points.

Resolution: This is a conditional question. It will resolve only if both milestones of Q1.4 happen on or before Dec 31, 2030. If not, the question will not resolve.

- Start date: the date when both milestones have happened, that is, the later of the two dates in Q1.4.
- Gain: the ECI frontier 12 months after the start date, minus the ECI frontier on the start date. Since the ECI frontier cannot fall, the gain is zero or more.

We will use Epoch AI’s data and handle any changes to the ECI as in Q2.1. We will read the data three months after the end of the 12-month period.

## 3. Fast years

These questions ask whether AI progress will accelerate. Definition:

- A fast year is a rise of the ECI frontier by 30 points or more within any 12-month window. A fast year counts as soon as it happens. For example, if the ECI frontier rises by 30 points in 7 months, a fast year has happened at the end of those 7 months.

### Q3.1 Fast year by 2027

**What is the probability of a fast year by Dec 31, 2027?**

Answer: a probability from 0 to 100.

Resolution: This question will resolve Yes if a fast year happens on or before Dec 31, 2027.

The 12-month window can start before this survey opened (Nov 3, 2026), but it must end on or before Dec 31, 2027. We will use Epoch AI’s data and handle changes to the ECI as in Q2.1.

### Q3.2 Fast year by 2030

**What is the probability of a fast year by Dec 31, 2030?**

Answer: a probability from 0 to 100.

Resolution: The same criteria as Q3.1, but by Dec 31, 2030. A fast year by Dec 31, 2027 also counts as Yes for this question.

### Q3.3 ECI gain after the first fast year

**If a fast year happens by Dec 31, 2030: how many ECI points will the ECI frontier gain in the 12 months after the date when the first fast year has happened?**

Answer: P10, P50, and P90, in ECI points.

Resolution: This is a conditional question. It will resolve only if a fast year happens on or before Dec 31, 2030. If not, the question will not resolve.

- Start date: the date when the first fast year happens.
- Gain: the ECI frontier 12 months after the start date, minus the ECI frontier on the start date. Since the ECI frontier cannot fall, the gain is zero or more.

For example, suppose that a model becomes publicly available on Mar 1, 2028 and sets the ECI frontier at 170, and another model becomes publicly available on Oct 1, 2028 and raises it to 205. This rise of 35 points within 7 months is a fast year. If there was no earlier fast year, the start date is Oct 1, 2028, and the gain is the ECI frontier on Oct 1, 2029 minus 205.

We will use Epoch AI’s data and handle changes to the ECI as in Q2.1. We will read the data three months after the end of the 12-month period.

### Q3.4 Cause of the first fast year

**If a fast year happens by Dec 31, 2030: what is the probability that AI automation of AI R&D caused the first fast year?**

Answer: a probability from 0 to 100.

Resolution: This is a conditional question. It will resolve only if a fast year happens on or before Dec 31, 2030. If not, the question will not resolve. The first fast year is as in Q3.3.

AI automation of AI R&D caused the first fast year if it was the direct or proximate cause of the rise in the ECI frontier, or if the first fast year would not have occurred, or would have counterfactually been extremely unlikely to occur, “but for” the substantial involvement of AI in the AI R&D behind the models that raised the ECI frontier during that fast year. Other causes, such as more training compute, can also contribute.

Since no one can observe what would have happened without AI, this question is partly hypothetical. We will aim to resolve it with the best evidence available (which may include, for example, the AI companies’ own assessments, such as Anthropic’s test of whether a doubling of the rate of progress in AI aggregate capabilities is “*substantially attributable to the automation of research and/or engineering*” ([Responsible Scaling Policy v3.4](https://www-cdn.anthropic.com/files/4zrzovbb/website/0bacdc8440ea96e62a8766d99ebe1d4eea6d5f3a.pdf)), or asking a panel of AI experts).

## 4. Internal lead

These questions ask how far the best AI models inside AI companies will be ahead of the best publicly available models. Definitions:

- The internal lead is the number of ECI points by which the best model available internally at any AI company leads the ECI frontier. For each internal model, we will use the ECI score from Epoch AI once that score is publicly available, and we will date the model by the date when it first became available internally.
- A model is available internally on a date when at least some staff inside the company can use it, for example for AI R&D, safety testing, or daily work. The model counts even if the company restricts its use to a small group of staff or to a few tasks, for example because of safety concerns or a government restriction. We will date each model by the date when it first became available internally, as the company reports it (for example, in a system card) or as credible reports show.

### Q4.1 Internal lead, end of 2027

**What will the internal lead over the ECI frontier be on Dec 31, 2027?**

Answer: P10, P50, and P90, in ECI points.

Resolution: This question will resolve to the internal lead on Dec 31, 2027.

We will use Epoch AI’s ECI scores and handle changes to the ECI as in Q2.1. Epoch AI scores models only after they become publicly available; we will resolve the question when the ECI scores of the models that were available internally on Dec 31, 2027 are publicly available. The internal lead is zero or more by definition, because a publicly available model is also available internally.

Please forecast how far the best AI inside the companies is ahead of the ECI frontier. Since some internal models may never become publicly available, and the dates when models first became available internally may not be disclosed, this question is partly hypothetical. If the required data exist when the question resolves, we will use them. If not, we will aim to resolve the question with the best evidence available (which may include, for example, the companies’ own benchmark reports, or asking a panel of AI experts to estimate the internal lead).

### Q4.2 Internal lead, end of 2030

**What will the internal lead over the ECI frontier be on Dec 31, 2030?**

Answer: P10, P50, and P90, in ECI points.

Resolution: The same criteria as Q4.1, but on Dec 31, 2030. For the reasons given under Q4.1, this question is partly hypothetical.

### Q4.3 Internal lead after both milestones

**If both automated AI R&D milestones (Q1.4) happen by Dec 31, 2030: what will the internal lead over the ECI frontier be 12 months after the date when both milestones have happened?**

Answer: P10, P50, and P90, in ECI points.

Resolution: This is a conditional question. It will resolve only if both milestones of Q1.4 happen on or before Dec 31, 2030. If not, the question will not resolve.

- Start date: the date when both milestones have happened, as in Q2.3.
- Internal lead: as in Q4.1, measured 12 months after the start date.

Please forecast how far the best AI inside the companies is ahead of the ECI frontier, one year after AI does most AI R&D on its own. Since the milestones of Q1.4 and the internal lead are partly hypothetical, this question is partly hypothetical too. If the required data exist when the question resolves, we will use them. If not, we will aim to resolve the question with the best evidence available (which may include, for example, asking a panel of AI experts to estimate the internal lead).

## 5. Expert AGI and AI catastrophe

These questions ask how a fast year would change the chances of expert AGI and an AI catastrophe by 2050. We use the same definitions as FRI’s Longitudinal Expert AI Panel ([LEAP](https://leap.forecastingresearch.org/)). Definitions:

- Expert AGI means that more than 50% of LEAP panelists agree that AGI exists ([LEAP Wave 8](https://leap.forecastingresearch.org/reports/wave8)). AGI is a commercially available AI system that (1) can outperform the 90th percentile professional human employee in every primarily non-physical occupation (based on 2025 performance), across all sectors, on at least 90% of the economically useful non-physical tasks that they perform, and (2) has an inference cost no more than 5× the cost of equivalent human labor.
- An AI catastrophe is a catastrophic event caused primarily by AI systems in which more than 10% of the people alive at the start of a five-year period die by the end of that period ([LEAP Wave 9](https://leap.forecastingresearch.org/reports/wave9)). This covers cases where AI is the direct or proximate cause of the deaths, and events that would not have occurred, or would have been extremely unlikely to occur, “but for” the substantial involvement of AI within one year before the event.

### Q5.1 Expert AGI by 2050, with a fast year

**If a fast year happens by Dec 31, 2030: what is the probability of expert AGI by 2050?**

Answer: a probability from 0 to 100.

Resolution: This is a conditional question. It will resolve only if a fast year happens on or before Dec 31, 2030. If not, the question will not resolve. If a fast year happens, the question will resolve Yes if expert AGI exists on or before Dec 31, 2050.

Since the LEAP panel may not exist in 2050, this question is partly hypothetical. If the panel exists when the question resolves, we will use its answer. If not, we will aim to resolve the question with the best evidence available on whether such a panel would agree that AGI exists (which may include, for example, asking another panel of AI experts).

### Q5.2 Expert AGI by 2050, without a fast year

**If no fast year happens by Dec 31, 2030: what is the probability of expert AGI by 2050?**

Answer: a probability from 0 to 100.

Resolution: The same criteria as Q5.1, but the question will resolve only if no fast year happens on or before Dec 31, 2030. If a fast year happens, the question will not resolve.

### Q5.3 AI catastrophe by 2050, with a fast year

**If a fast year happens by Dec 31, 2030: what is the probability of an AI catastrophe by 2050?**

Answer: a probability from 0 to 100.

Resolution: This is a conditional question. It will resolve only if a fast year happens on or before Dec 31, 2030. If not, the question will not resolve. If a fast year happens, the question will resolve Yes if an AI catastrophe happens on or before Dec 31, 2050.

We will use the resolution criteria of [LEAP Wave 9](https://leap.forecastingresearch.org/reports/wave9). In particular, for fatality and population data, we will rely on broadly recognized sources, such as Our World in Data, the Economist, and the United Nations. The five-year period must start on or after Dec 31, 2025 and end on or before Dec 31, 2050. If reasonable people disagree about whether such a catastrophe has happened, a panel of experts will resolve the question.

Please give your best forecast of whether such a catastrophe will happen by 2050. Do not change your forecast because of problems with resolution. For example, do not consider whether anyone will be able to resolve the question after a catastrophe.

### Q5.4 AI catastrophe by 2050, without a fast year

**If no fast year happens by Dec 31, 2030: what is the probability of an AI catastrophe by 2050?**

Answer: a probability from 0 to 100.

Resolution: The same criteria as Q5.3, but the question will resolve only if no fast year happens on or before Dec 31, 2030. If a fast year happens, the question will not resolve.
