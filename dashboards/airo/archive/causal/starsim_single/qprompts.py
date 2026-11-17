"""Prompts for the single-region continuous design (v4). Two SEPARATE prompts per
item; the model never sees baseline and intervention together."""

PREAMBLE = """This is a question from ForecastBench-Sim, a forecasting-calibration \
benchmark built by the Forecasting Research Institute. The data below comes from \
a toy SIR simulation (the open-source starsim package): one synthetic population \
of 5,000 agents with fixed, stated parameters, no behavior change, no travel, and \
no interventions unless stated. Your task is probabilistic forecasting of simulator output."""

KEYS = ("p10", "p25", "p50", "p75", "p90")


def prompt(report: str, question: str, intervention: str | None = None) -> str:
    block = f"\n\nPLANNED INTERVENTION: {intervention}" if intervention else ""
    return f"""{PREAMBLE}

{report}{block}

QUESTION: {question}

The report ends at day 20. The simulation is stochastic, so give a distribution: your \
10th, 25th, 50th, 75th and 90th percentiles for the number of people (integers ≥ 0). \
You may reason briefly first. Then end your reply with one JSON object, alone on its \
final line, with exactly these keys:
  "p10", "p25", "p50", "p75", "p90"  (non-decreasing numbers of people)"""
