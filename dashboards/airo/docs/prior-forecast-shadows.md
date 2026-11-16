# Prior-forecast shadows

`prior-baseline-shadow` runs the minimal Baseline instrument on Wednesday and
Friday. Its sole prompt addition identifies `file:///forecasts/prior-ensemble.json`.
The existing `read_page` tool can read this pinned file in pages. Reading is
optional; the model still submits absolute levels with the normal rationale.
There is no AIRO-reference prohibition or URL guard, and Baseline's turn limit,
research settings, panel and questions are retained.

The input contains all 73 unconditional question medians across the previous
published Baseline panel, original question wording, forecast and resolution
dates, counting windows, and Baseline ECI percentiles. It excludes individual
model responses, rationales, and conditional scenario forecasts. The publication
selected at job start supplies the source run IDs, so raw forecasts produced
later in that job cannot become its prior. Source panel completeness is checked
before workers start. Rows record the snapshot hash and provenance; tool evidence
records whether and which pages each model read. Private source paths are omitted.

`prior-recent-shadow` adds the recent-news file using the news shadow's fresh
poll/reduction mechanism, without its AIRO ban or guard. It replaces the scheduled
`recent-shadow-noairo`, which remains available manually. Both new shadows run
Wednesday/Friday and are excluded from publication and pooling.

The first prior-recent run requires explicit `--seed-prior-baseline`; its seed is
the same published Baseline ensemble used by prior-baseline-shadow. Thereafter
it reads its own last complete ensemble, retained under private
`results/experiments/prior-recent-shadow/`. Only a successful complete panel and
question/horizon grid advances this pointer. Failed, partial, filtered-model and
smoke runs never advance it. Missing or corrupt prior inputs fail closed.

Manual runner examples (from the AIRO directory, using production's configured
provider environment and an explicit published site directory):

```
python code/run_unified.py --experiment prior-baseline-shadow --prior-publication /published/site
python code/prepare_recent_news.py --experiment prior-recent-shadow --condition prior-recent-shadow
python code/run_unified.py --experiment prior-recent-shadow --prior-publication /published/site --news-snapshot /prepared/news.json --seed-prior-baseline
```

Scheduled jobs receive `AIRO_PRIOR_PUBLICATION` from the runtime and need no seed
flag after the first complete manual run. Forecast generation incurs provider
charges; offline tests and dry runs do not exercise provider calls.
