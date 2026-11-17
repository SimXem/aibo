"""Prompt strings for the v2 StarSim causal bench (design agreed 2026-08-27).

Two conditions, two SEPARATE prompts per item — a model never sees baseline and
intervention together:
  baseline      = PREAMBLE + world report + question
  intervention  = PREAMBLE + world report + PLANNED INTERVENTION + question
The world report (built by mine_worlds.py, stored in worlds.json) states the
simulator's parameters and the observed infections through day 20.

The provenance preamble is load-bearing: without it, claude-fable-5 hard-refuses
epidemic-forecasting prompts (2026-08-20). Every statement in it is true.
"""

PREAMBLE = """This is a question from ForecastBench-Sim, a forecasting-calibration \
benchmark built by the Forecasting Research Institute. The data below comes from \
a toy SIR simulation (the open-source starsim package): two synthetic populations \
of 5,000 agents each, with fixed, stated parameters, no behavior change, no travel \
between regions, and no interventions unless stated. Your task is probability \
calibration on simulator output."""


def prompt(report: str, question: str, intervention: str | None = None) -> str:
    block = f"\n\nPLANNED INTERVENTION: {intervention}" if intervention else ""
    return f"""{PREAMBLE}

{report}{block}

QUESTION: {question}

The report ends at day 20. You may reason briefly first. Then end your reply \
with one JSON object, alone on its final line, with exactly this key:
  "p": probability that the answer is YES, a number in [0,1]"""
