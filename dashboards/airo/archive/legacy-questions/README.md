# Retired question sets — XPT starter set and the hand-authored severity ladder

Retired 2026-08-18 by the Auto-ARC swap. Kept, not deleted: the forecasts in
`archive/legacy-forecasts/` are keyed on these question ids, and without the
question text those rows are unreadable numbers.

## What was here

`starter_questions.json` — 13 XPT bottom-line questions (2022 tournament),
carrying the super/expert medians the dashboard drew as human baselines.

`severity_ladder_questions.json` — 28 questions this project wrote (4 causes x
7 rungs) because XPT had no complete severity ladder for any cause. Its own
provenance block named its successor: the fuller FRI catastrophic-risk
questions document, once final, should replace these definitions. It did.

`xpt.py`, `xpt_build_exceedance.py`, `test_xpt.py` — the machinery that turned
XPT's event-COUNT questions (#15-#18, "how many times will a state actor...")
into a P(>=1 event) comparable with a model probability, including the censoring
rules for a forecaster whose whole elicited ladder sat below the threshold. The
Auto-ARC set has no quantity questions, so nothing calls it.

## What carried over, and what did not

Only two questions kept their wording, and therefore their human baseline:

| Retired | Becomes | Anchor |
|---|---|---|
| 9. Total Catastrophic Risk | `catastrophe:general` | XPT medians, same 10%-of-population threshold |
| 3. AI Catastrophic Risk | `catastrophe:ai` | same |

The other eleven have no successor. Nuclear left the question set entirely.
So did extinction — Auto-ARC has no extinction question, and human
disempowerment replaces the concept with no anchor and no history. That
retires `config.STABLE_SUBSET`, which had named 9/10/3/4 as the four
"confirmed to survive" the Auto-ARC rewrite: half of them did not.

The two surviving anchors are not read from here. They are transcribed into
`code/make_autoarc_questions.py::attach_human_anchors` with their provenance,
so the live set has one source and this directory stays inert.

## If you need to read a legacy forecast

`redlines/runlog.py` does not point here and should not. Load the JSON directly:

```python
import json
qs = {q["id"]: q for q in json.load(open("archive/legacy-questions/starter_questions.json"))["questions"]}
```

`archive/legacy-forecasts/README.md` covers the forecasts themselves.
