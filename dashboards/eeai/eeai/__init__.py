"""EEAI: the Economic Effects of AI dashboard.

FRI's "Economic Effects of AI" expert survey, asked of the standing model panel
(fri_forecaster.panel) under the Baseline condition (fri_forecaster.baseline),
re-asked over time so the forecasts form a series.

This directory is the whole dashboard: the code, data/ (the questions and the
record), web/ (the page's source), tests/, and README.md. Outside it EEAI uses
only the harness (packages/forecaster) and the repository's Epoch
snapshots. AIRO, the other dashboard in this repository, shares the panel and
the loop through the harness and nothing else.

    python3 eeai/make_questions.py        # the survey documents -> eeai/data/questions.json
    python3 -m eeai prompt                # the prompt as it would be sent; calls nothing
    python3 -m eeai run                   # ask the panel (paid: model and search calls)
    python3 -m eeai build                 # eeai/results/runs/*.jsonl -> the site, eeai/site/

README.md says what is asked, what is not, and what is still open.
"""
