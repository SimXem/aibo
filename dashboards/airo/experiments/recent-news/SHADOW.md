# recent-shadow-noairo

`experiments/airo.toml` includes `recent-shadow-noairo` as a **Friday-only,
unpooled, unpublished** condition. It inherits the same ECI-selected panel,
full question/scenario instrument and harness as ordinary AIRO conditions.
Existing published condition hashes and the five-condition ensemble are unchanged.
The standalone `experiments/recent-shadow-noairo.toml` remains a manual alias.

The full shadow sets `max_turns = 0`: **no forced-turn submission limit**.
The ordinary production process timeout remains (three hours by default), as
for the other models. The eight-turn limit in the cheap probe is not used by
Friday's condition.

## Exact prompt change

The existing Recent instruction is followed by the owner's sentence:

> For convenience, some relevant recent news stories are provided in file:///news/recent.json.

Then comes the existing `ai-banned` instruction, verbatim. No additional
research instructions or tool descriptions are inserted. The existing
`ai-banned` URL block patterns travel with each call. Inspecting the cache is
optional: there is no new research floor or forced initial read.

`file:///news/recent.json` is a fixed virtual path accepted by the existing
`read_page` tool. It maps only to this call's explicitly supplied snapshot,
not arbitrary local files. The model can page through it using `offset` and
`next_offset`, with web search and ordinary page reads available alongside it.
No new tool descriptions are needed. Calls and returned pages are captured in
normal `evidence` records.

The news snapshot is feed-only: a headline index followed by per-story source
reports with feed summaries and URLs. No generated summaries, survey scoring,
full-text caches, or update outputs are included. Blocked source URLs are
removed before selecting story titles. This guard does **not** exclude every
third-party article discussing AIRO; the instruction still matters.

## Prepare an explicit private snapshot

First poll and reduce using `code/recent_news.py` as described in README.md.
Then freeze a chosen window (substitute actual timestamps and private paths):

```sh
python3 code/recent_news.py snapshot --state "$NEWS_STATE" \
  --since "$START" --as-of "$END" --out .local/recent-news/input.json
```

This requires a complete reduction built on/before END. It refuses selected
reports fetched or published after END; it does not reconstruct past state
from today's reduction. The file records the window, reduction time, collection
time and guard. An old collection is not a current-week feed simply because
END is recent. Inspect these fields before an experiment.

At launch the snapshot is validated, copied to a content-addressed private
file and its SHA-256 recorded on every forecast row, along with dates and story
count. Each local page read rechecks the hash. The original historical state is
never modified. Snapshot contents, traces and forecast rows remain private.

## Cheap first test (not a panel run)

```sh
# Prints/saves the exact prompt; no provider calls:
python3 code/probe_recent_news.py --snapshot .local/recent-news/input.json

# Explicitly permits one Haiku 4.5 call, eight-turn limit, no retries:
python3 code/probe_recent_news.py --snapshot .local/recent-news/input.json --execute
```

For the unchanged Recent baseline, pass `--condition recent`. For Sonnet 5.5,
pass `--model sonnet` (the default remains Haiku). Independent probes can run
in parallel with distinct `--out` directories. `--timeout 600` increases the
wall-clock allowance without changing the eight-turn limit or prompt.
`--date YYYY-MM-DD` fixes the prompt date for matched probes; web searches
remain live, so this option does not make the run a historical backtest.

The probe uses one existing AI incident question, the 12mo horizon, and no
conditional scenarios or capability elicitation. It retains the existing
instrument's other text and tool schemas. This is only a tool-use smoke test,
not a valid full-condition forecast or a historical backtest. Cached news and
instrument background may be older than the execution date. It records the
prompt, evidence, usage and a read-count summary under `.local/recent-news/`.
Model and search charges apply with `--execute`; the eight-turn limit is a
runaway guard, not a dollar-denominated spending limit. Credentials come from
the configured private forecasting environment, not a coding-provider login.

## Full condition (separate, more expensive)

```sh
# Inspect the full instrument and guard, without model calls:
python3 code/run_unified.py --experiment recent-shadow-noairo --dry-run

# Paid frontier-panel run: only when deliberately requested.
python3 code/run_unified.py --experiment recent-shadow-noairo \
  --news-snapshot .local/recent-news/input.json \
  --out .local/recent-news/forecasts.jsonl \
  --conditional-out .local/recent-news/instrument.jsonl
```

The full runner retains its ordinary instrument-integrity preflight. Without
explicit output paths its existing unpublished-run destination is
`results/experiments/`; use private paths above and do not commit raw outputs.
The standalone alias is manual and unpooled. Friday's AIRO condition is
scheduled through the normal daily dispatcher, as an unpublished group after
the published conditions, sharing the same refreshed ECI snapshot and panel.
An A/B study should distinguish accessing news from citing it or changing
forecasts; these are live searches, not frozen retrievals.
