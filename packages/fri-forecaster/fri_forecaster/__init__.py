"""FRI Forecaster: an agentic forecasting harness (pi + shared research tools).

Factored out of AIRO (forecastingresearch/airo, commit 3be3b93) on 2026-10-05.

    harness.py       one pi call: spec, run, evidence/usage, merged answer
    pi_tools.ts      the pi extension: research tools, submit tools, research floor
    tools.py         web_search / read_page (Tavily), stdlib only
    tool_cli.py      the research tools as a CLI, for pi_tools.ts
    keys.py          API keys from the environment or an env file
    forecastbench.py ForecastBench driver: members (run) and arms (build)
"""
__version__ = "0.1.0"
