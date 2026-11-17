# Legacy forecasts — retired 2026-08-14

These are every forecast the dashboard used before the unified batch protocol.
They are **retired, not deleted**: no panel reads them, and the time series
starts over from `results/forecast_runs_unified.jsonl`.

```
forecast_runs.jsonl    419 rows — the append-only log, 2026-08-05 to 2026-08-10
runs/2026-08-11T2221Z.jsonl   one scheduled run from the cron box
```

## Why they were retired

Every row here was elicited one question per call. That protocol produces
forecasts that contradict each other, and the contradictions are not small:

```
                                          legacy    unified
  P non-increasing over severity            9.5%       0.0%
  no cause above "all causes"               4.5%       0.0%
  XPT question vs its ladder rung          23.3%       1.7%
  narrower question <= broader              3.1%       0.0%
  overall                                   5.9%       0.2%
```

The 23.3% row is the reason a merge was impossible rather than merely untidy.
Graph 1 and Graph 2 asked the same model the same question in different calls and
got different answers, so no amount of downstream reconciliation could make the
panels agree — one of the two numbers had to be wrong, and nothing in the data
said which.

Splicing these rows onto the unified series would also put a protocol change
inside a time series whose whole purpose is to show forecasts moving. A jump
caused by how we asked would read as news.

See `docs/coherence-experiment.md` for the experiment that established this, and
`code/audit_coherence.py --compare` to reproduce the table above (it still points
at this file for the legacy column).

## What they are still good for

- The experiment's control arm. `code/analyze_ladder_joint.py` reads the two
  ladder runs here as the separate-call baseline.
- Provenance. These are real, paid-for elicitations with their evidence trails
  intact; they are the record of what the models said under the old protocol.

Do not append to them. Do not merge them into the live log.
