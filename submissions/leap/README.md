# LEAP: the panel answers a survey wave

LEAP is FRI's monthly panel on AI questions. Each wave arrives as one JSON
question set and goes back as one JSON file per forecasting system. A question
asks for a number at every combination of its dimensions, scenarios and
resolution dates (an *entry*), as percentiles or as one point forecast.

The system submitted is the standing panel under the Baseline condition: the top
four models by Epoch's index (`fri_forecaster.panel`), each asked the whole
question set once with web search (`fri_forecaster.baseline`), pooled by an
equal-weight mean per value. It is the same system as ForecastBench's `chorus`
condition and goes under the same name (`python -m forecastbench.names current chorus`).

```
leap/
  instrument.py            the question set as one prompt, the answer tools, the cleaning
  run.py                   ask the panel: one call per member -> <out>/<stamp>.jsonl
  build.py                 pool the members, write and check the submission file
  validate_submission.py   the organisers' validator, as sent with every question set
tests/                     a made-up model and question set; no calls
```

## A wave

Run from this directory, or anywhere once installed (`pip install -e .`). The
question set and everything a run writes stay outside the repository.

```sh
python -m leap prompt QUESTIONS.json                          # what a model is asked; free
python -m leap run    QUESTIONS.json --out WAVE/runs          # PAID: four model calls with search
python -m leap run    QUESTIONS.json --out WAVE/runs --resume RUN_ID   # only the members it lacks
python -m leap build  QUESTIONS.json WAVE/runs/RUN_ID.jsonl --model NAME --out WAVE
```

`build` writes `WAVE/<model>.<question_set>.json` and prints the validator's
verdict. That file is the submission; it is sent by hand.

- Keys come from the installation's one keys file (`fri_forecaster.keys`). The
  panel is chosen from AIRO's Epoch snapshots; `LEAP_ECI_DIR` names another
  directory of snapshots and automatic model rows.
- A model answers by entry number (`e1`, `e2`, ...), so the dimension and
  scenario names in the file are the question set's own strings.
- An entry is kept whole or not at all: a value that is missing, not a number,
  outside the unit's range, or percentiles that decrease drop the entry. It is
  never repaired. A member short of values is asked again once.
- Every member must have every entry. A partial ensemble is a different system,
  so `build` refuses one unless told `--allow-partial`.
- A panel member that cannot be run fails the run; no other model stands in.

A finished wave needs nothing kept here: the code is the same for the next one.
