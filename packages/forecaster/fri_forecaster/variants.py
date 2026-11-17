"""The prompt variants: one instruction each, added verbatim to a dashboard's prompt.

Jason's five (2026-10-14) and a sixth. A CONDITION asks the panel under one
of them; `none` adds nothing and is the Baseline condition
(fri_forecaster.baseline). They live here because more than one caller asks
under them and the text must not drift between callers: AIRO's experiments
(redlines.experiments names one per condition; code/run_unified.py puts its
text into the joint prompt) and the ForecastBench driver
(forecastbench.airo_prompt). Each caller says where in its prompt the text
goes and which conditions it pools.
"""

VARIANTS = {
    "none": None,
    "independent": (
        "Try to make your own forecasts. Do not take into account external surveys "
        "assessing extinction or catastrophic risk, or other probabilities given by "
        "prominent figures. The goal is to reach your own independent conclusion."),
    "recent": (
        "If you search external information, focus on information that arrived within "
        "the past year, and weight more heavily sources that are more up to date about "
        "recent developments."),
    "critical": (
        "Evaluate existing information critically. If you take into account forecasts by "
        "specific people or surveyed groups, consider their recent and historical "
        "forecasting accuracy, as well as the information available to the forecasters "
        "when they made their forecasts."),
    "two-step": (
        "Proceed in two steps. First, make the best predictions you can about model "
        "capability progress over the relevant time frame, via human generated "
        "improvement or recursive self-improvement. Consider the distribution, not only "
        "the modal outcome. Then, given possible model capabilities, evaluate the risk "
        "posed and put these pieces together."),
    # THE SIXTH (2026-10-19 evening): the AI-forecast ban, the `both` arm of the
    # anchor-guard experiment of 2026-10-16 (results/experiments/anchor-guard-
    # 2026-10-16, where it was a system-prompt addendum; the minimal instrument
    # has no system prompt, so it goes where a variant's text goes). The airo
    # experiment pairs it with agent-box's URL guard against AIRO's own pages,
    # passed to that condition's calls alone.
    "ai-banned": (
        "Forecasts produced by AI systems, including any automated forecasting "
        "dashboard or model ensemble, carry no information beyond their inputs. Do not "
        "consult them or use them as evidence."),
}
DEFAULT_VARIANT = "none"
