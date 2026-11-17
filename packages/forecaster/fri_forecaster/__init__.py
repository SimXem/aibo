"""FRI Forecaster: an agentic forecasting harness (pi + shared research tools).

Factored out of AIRO (forecastingresearch/airo, commit 3be3b93) on 2026-10-05.

    harness.py       one pi call: spec, run, evidence/usage, merged answer
    pi_tools.ts      the pi extension: research tools, submit tools, research floor
    tools.py         web_search / read_page (Tavily), stdlib only
    tool_cli.py      the research tools as a CLI, for pi_tools.ts
    keys.py          API keys from the environment or an env file
    alert.py         alerts: callers say what happened, the installation says where it goes
    variants.py      the prompt variants (AIRO's conditions): one instruction each
    panel.py, eci.py the panel: the top models by Epoch's index
    baseline.py      the Baseline condition: how a dashboard asks the panel

Its users are the projects under dashboards/ and submissions/.
"""
__version__ = "0.1.0"
