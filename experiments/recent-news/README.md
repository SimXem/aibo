# Recent-news: RSS → deduplicated AI stories

Experimental input pipeline. AIRO's published `recent` condition and ensemble
remain unchanged. The separate Friday `recent-shadow-noairo` condition can
browse this input; see [SHADOW.md](SHADOW.md) and the production handoff in
`deploy/README.md`.

## Machinery retained

- Eight configured RSS/Atom feeds (`feeds.json`): FT AI, NYT AI/Technology/
  Science, Reuters via Google News, Ars AI, MIT Technology Review AI, Verge AI.
- Normalize dates and descriptions; deduplicate canonical article URLs.
  Decode Google News links to publisher URLs where possible (otherwise retain
  the Google link). This unofficial decoding can break.
- Jev's broad **about-AI** gate for articles not carried by an AI-only feed.
  AI-only feeds bypass this gate. This is a candidate pool for AI-safety news,
  **not a validated safety-relevance filter**. No forecast or survey-impact
  judgment is made.
- Deterministic event deduplication: shortlist at most 20 stories within 72
  hours of an item's publication time, ranked by headline/summary word overlap.
  Jev independently judges each candidate; probability ≥ 0.5 merges into the
  best match. No candidate means a new story without a model call.
- Follow-up probabilities link distinct developments as `related` stories;
  they do not merge them unless the same-event judgment also passes.
- Append-only item, fetch and decision logs; reusable decisions and offline
  replay; a markdown audit of failures and close merge calls.

Excluded: full-text/Tavily extraction, forecast loading, ECI/model selection,
update/screen/gate-by-survey-impact, odds ratios, rationales, digest and UI.
Even the old empty per-cause `screen` schema has been removed. Jev sees only
feed headlines/standfirsts, not cached article text.

Implementation: `redlines/recent_news.py`; CLI: `code/recent_news.py`.
Stdlib only; no new dependencies.

## Run from the checkout

Default private state is `.local/recent-news/` (gitignored); override with
`AIRO_NEWS_DIR` or `--state`. Do not commit state, reports, or exported stories.
Only synthetic fixture feeds are checked in. One process should own a state
folder; concurrent writers are not supported.

```sh
# Network, but no model calls:
python3 code/recent_news.py poll

# Paid Jev calls for decisions not already logged; requires TYPESAFE_API_KEY:
python3 code/recent_news.py reduce

# Offline output, with URLs and source/member provenance:
python3 code/recent_news.py list --since 2026-10-09 --out .local/recent-news/news.json
python3 code/recent_news.py report --out .local/recent-news/audit.md

# Combined fetch → reduce → date-filtered JSON (network + paid Jev):
python3 code/recent_news.py run --since 2026-10-09

# Offline reconstruction; writes stories.json only if no items are undecided:
python3 code/recent_news.py reduce --replay
```

Supply credentials via the environment/private runtime configuration, never a
tracked file. Live operation requires operator-approved network access to Jev,
the configured feed hosts and any redirect hosts. This port adds no grants,
scheduled work by itself. The Friday shadow integration adds a daily free
poll and prepares one shared snapshot before the shadow panel runs.

`run` aborts on failed or empty feeds rather than presenting a partial poll as
complete. Fetch results remain in `fetches.jsonl`. `list` is deliberately an
offline view of the **last successful reduction**, not a freshness guarantee.
A failed or incomplete reduction does not replace `stories.json`.

## Date and coverage semantics

`--since` is inclusive, accepts an ISO date/timestamp, and treats a date or
naive timestamp as UTC. An event qualifies when its **earliest member's
publication time** is on/after the cutoff; missing dates use first-fetch time.
Reduce all collected history before applying the cutoff: another report of an
older event does not qualify it as new. Distinct follow-up events can qualify.
Output is oldest-first with stable IDs, members, sources, related stories,
reduction statistics and thresholds.

This is **not historical search or an as-of forecast input**. RSS exposes a
bounded recent window; an earlier `--since` cannot recover expired entries.
The production integration polls daily at 11:45 UTC to build history; daily
polls can still miss entries on fast-moving feeds.
Publication timestamps can be updated by publishers, and a story can contain
reports collected after a prospective evaluation cutoff. A future A/B study
must freeze the observation window and input snapshot to avoid look-ahead.

Other inherited limitations: lexical shortlisting can miss paraphrases;
the 72-hour window can split delayed coverage; canonicalization strips all
query parameters on non-root paths (appropriate for these feeds, not arbitrary
publishers); Jev's `jev-latest` alias can change. Decision logs retain returned
model IDs, probabilities, usage and thresholds. Replay reuses overlapping
logged candidates when a threshold change changes the candidate set; it is
not equivalent to fresh judgments of previously unseen candidates.

## Provenance and verification

Ported from the selected `origin/news` snapshot at
`718e1f051166b010813de9d13b21feb203c23b9e`, principally `redlines/news.py`,
`data/news_feeds.json` and the synthetic news tests. No historical news state,
forecast inputs, credentials or transferred receipts are included.

The handoff notes that its preserved 163-story state replays to only 160
stories with three undecided items. Never replay over that preserved state;
use a private temporary copy. This port rejects incomplete reductions rather
than overwriting the existing output. It intentionally does not load old
full-text caches, so historical Jev-input parity is not promised.

```sh
python3 -m unittest tests.test_recent_news
python3 -m pytest tests/test_recent_news.py
```

Tests exercise synthetic RSS/Atom and Google News resolution, URL deduplication,
AI gating, same-event versus follow-up decisions, threshold/replay behavior,
API retries, date filtering, missing dates, incomplete-replay protection and
offline CLI output. No network or paid API calls are required.
