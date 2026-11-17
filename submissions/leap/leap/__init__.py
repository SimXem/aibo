"""LEAP: the panel answers a LEAP survey wave, and the answers go back as one file.

LEAP (FRI's monthly panel on AI questions) sends a question set as JSON and
takes one submission file per forecasting system. A question asks for a
number at every combination of its dimensions, scenarios and resolution dates
(an "entry"), as percentiles or as one point forecast.

    instrument.py            the question set as one prompt, the answer tools, the cleaning
    run.py                   ask the panel: one Baseline call per member (PAID)
    build.py                 pool the members and write the submission file, checked
    validate_submission.py   the organisers' validator, as sent with every question set

    python -m leap prompt QUESTIONS.json                       # the prompt, free
    python -m leap run    QUESTIONS.json --out DIR             # PAID: model and search calls
    python -m leap build  QUESTIONS.json DIR/<run>.jsonl --model NAME --out DIR

Question sets and run files stay outside the repository.
"""
__version__ = "0.1.0"
