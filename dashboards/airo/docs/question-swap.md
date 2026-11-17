# Question swap — the Auto-ARC question set

Status: **design, not executed.**

Sources (the Auto-ARC question set is by Bridget Williams, FRI):
- The Auto-ARC question workbook, sheet "Auto-ARC questions - long" — 141 rows,
  the authority on composition (tracked as `data/auto-arc/questions-<date>.xlsx`).
- The Auto-ARC definitions and resolution criteria (tracked as
  `data/auto-arc/definitions-<date>.md`).
- Sheet "Questions from prior FRI work" — the human panels that already asked a
  comparable question (XPT, LEAP, P6 bio, the AI-cyber pilot, Active Site).
- **The 2026-08-17 project call.** The team decided three things this document
  depends on: run the draft questions now, never force coherence, and hydrate
  every threshold from one source.

**The team decided on 2026-08-17 to run these now** rather than wait for the
external review of the definitions, on the understanding that if the wording
later moves, the old forecasts are discarded and re-run. So the sequencing
question is settled.


## The set is 35 questions, not 141

The spreadsheet's "Date of question resolution" column is a HORIZON. This
dashboard already models a horizon as a dimension of a question, not as a
separate question. Collapse that column and the set is:

| Family | Questions | Severity | Horizons | Cells |
|---|---:|---|---|---:|
| General catastrophe | 1 | **10% of population** | 2030 / 2050 / 2100 | 3 |
| AI catastrophe | 1 | **10% of population** | 2030 / 2050 / 2100 | 3 |
| Human disempowerment | 1 | none | 2030 / 2050 / 2100 | 3 |
| AI-related incident | 8 | 8 rungs, deaths or $ | 2028 / 2030 / 2050 / 2100 | 32 |
| AI-related human-caused epidemic | 8 | 8 rungs, deaths or $ | 2028 / 2030 / 2050 / 2100 | 32 |
| AI-related cyber incident | 8 | 8 rungs, deaths or $ | 2028 / 2030 / 2050 / 2100 | 32 |
| Misaligned AI incident | 8 | 8 rungs, deaths or $ | 2028 / 2030 / 2050 / 2100 | 32 |
| P6-bio comparison rows | 4 | 10k / 10M / 100M / continuous | 2045 | 4 |
| **Total** | **35** | | | **141** |

33 cells carry `y` in the "To be completed by humans?" column. Those get a human
number in the September round: the 1M rung of each incident type at all four
horizons, plus 1k at 2028 and 1B at 2100, plus all nine cross-cutting cells.

Two horizons were agreed on the call but are **not in the spreadsheet yet**:
*next 6 months* and *next 12 months*, so that an elevated very-near-term risk
is visible. These matter more to this dashboard than any other cell in the set: they are the only questions that
resolve inside the paper's life, so they are the only ones that can be scored.


## The incident grid is already a severity ladder

Four causes, eight rungs, one wording per cause, the threshold as the only
variable. That is exactly the shape `data/severity_ladder_questions.json` holds
today — four causes, seven rungs.

So this is a data change into the two files built for it. It is not a third
question set and not a new panel. The ladder spec says so in its own provenance
block: the fuller FRI catastrophic-risk questions document, once final, should
replace these definitions.


## Graph 2 — the severity ladder

Replace all 28 ladder questions with the Auto-ARC 4 × 8 grid.

### Causes: the palette transfers with no new hue

| New cause | Ladder key | Color | Was |
|---|---|---|---|
| AI-related incident (the container) | `ai` | `#3a4150` slate | `total` "All causes" |
| AI-related human-caused epidemic | `bio` | `#a63d76` magenta | `bio` — unchanged |
| AI-related cyber incident | `cyber` | `#a1801a` gold | `nuclear` |
| Misaligned AI incident | `misalign` | `#33a8bd` cyan | `ai` |

Slate goes to "AI-related incident" because that cause now plays the container
role the slate "All causes" curve plays today. The Auto-ARC definition makes the
containment explicit: an AI-related incident *"could be an AI-related
human-caused epidemic, an AI-related cyber incident, a misaligned AI incident,
or a different type of AI-related incident."*

### Rungs, and the 10%-of-population anchor

```
today:            1k        100k   1M    10M   100M          1B    extinction
Auto-ARC:  100    1k   10k  100k   1M    10M   100M    ·     1B
           $1B   $10B $100B  $1T  $10T  $100T   $1Q    ·    $10Q
                                                       ^
                                         10% of population (~820M today)
```

Six of the seven current rungs survive. The axis gains 100 and 10k at the
bottom, and loses `extinction` — with it, Graph 2's `WORLD_POP` reference.

**The two catastrophe questions are severity-axis anchors, not rungs.** Their
severity is *10% of the population alive at the start of the measurement
window* — about 820M people today. That is a point on the same log-death axis,
sitting between the 100M and 1B rungs. It is not a rung of the four incident
ladders, for two reasons: it floats with population where the rungs are
absolute, and it is deaths-only where the rungs are deaths-or-dollars.

The machinery for this already exists and needs no change. The ladder spec's
`xpt_anchor` block maps a question id to a deaths value, and Graph 2 renders it
as a marker on the curve. It already carries `820000000.0` for XPT #3 and #9.
After the swap it carries the Auto-ARC general and AI catastrophe questions at the
same value, and the anchor stops being a foreign human-baseline marker and
becomes one of our own live forecasts.

**Only one side of the bracket is safe to check.** P(AI catastrophe at 10% of
population) must not exceed P(AI-related incident ≥ 100M deaths or $1Q): that
rung is a strictly easier event on both legs. The ≥1B side is *not* licensed —
820M is below 1B on deaths, but the rung also resolves on $10Q, so neither
contains the other. Check the side the wording licenses and no more, exactly as
`coherence.py` already does for the XPT questions.

### The axis becomes disjunctive: deaths OR dollars

Each rung pairs a death count with a dollar figure at a constant 1:10⁷ ratio —
the stated VSL ($10M until the question set's 2026-08-31 revision; $2.2M since, which scaled every dollar leg: "100 deaths or $220M"). The legs are exactly convertible, so the axis stays
monotone and log-spaced. Label both scales.

This unblocks cyber. `severity_ladder_questions.json` currently says cyber is
*"absent by design"* because, per a 2026-08-03 decision, cyber belongs on a
damages ladder, not a deaths ladder, and needs its own question set. The
Auto-ARC disjunctive threshold is that question set. The note retires.

### Horizons

Three become four; 2028 arrives. The 2028 and 2044/2045 dates exist because
prior FRI studies use those dates. Two more arrive if the near-term horizons
land.


## Graph 1 — the bottom-line rail

> **Superseded twice.** The rail first grew to every rung of every cause
> (eight rows per incident type, matching Graph 2); since 2026-08-27 each
> incident cause is instead **one expected-loss row** — the eight rung
> forecasts folded to a floor on E[loss] in death-equivalents, the same
> arithmetic as the Conditional-on tab (`redlines.conditional.expected_loss`,
> `redlines/views/graph1.py::_loss_series`), plotted on Graph 2's severity
> axis. The rungs themselves stay on Graph 2. The plan below is kept as the
> record of why the incident types are on this rail at all.

The three cross-cutting questions go here: general catastrophe, AI catastrophe,
human disempowerment.

Three rail items is thin for a panel the paper screenshots. Also plot the **1M-deaths
/ $10T rung of each incident type** — the one rung the question set flags for human
forecasting at every horizon, so the only row where a model-versus-human read
exists across the whole time axis.

Implement it **by reference, not by copying**: add a `featured` array of question
ids to the ladder spec, and have Graph 1 read the ladder as well as the starter
file. Copying a question into both files would elicit it twice.

Seven rail items in two groups:

```
CROSS-CUTTING              AI INCIDENT TYPES  (≥1M deaths / $10T)
  Global catastrophe         Any AI-related incident
  AI catastrophe             AI-enabled epidemic
  Human disempowerment       AI-enabled cyber
                             Misaligned AI
```

Hold the P6-bio rows at 2045 out of the unified batch and elicit them
separately, the way question #2 is handled today.


## Single source of truth

The call was explicit about this: the data source that hydrates the dashboard's
language must be the same source that hydrates what the human panels and the
models are asked, so there is a single source of truth and no way for the three
to become disentangled. Once the canonical questions and definitions exist, the
dashboard is hydrated from them, and as they change, so do the prompts.

A request on the call to move the threshold out of small print and into the
graph title ("10 million deaths or $1 trillion in damage") immediately ran into
the objection that the XPT question actually plotted defines catastrophe as 10%
of the population.

**The objection was right, and the live dashboard is wrong today.**

| | Says |
|---|---|
| `web/demo/80-app.jsx:38` | "**Catastrophic** = ≥ 10 million deaths (or ≥ $1T economic damage), headline threshold." |
| `web/demo/70-modal.jsx:22` | "Headline threshold: **≥ 10 million deaths** (or ≥ $1 trillion in real economic damage)." |
| The question actually plotted (XPT #9) | "more than **10% of humans alive** at the start of a 5-year period die" |

That is 10M against roughly 820M — off by a factor of about 80, in the headline
definition, on the page the paper screenshots. It is hand-typed prose
in JSX that was never joined to the question data. **Fix this now, ahead of and
independently of the swap.**

### What the SSOT must hold

One canonical record per question, carrying everything any surface needs:

- `id`, full `text`, and the resolution criteria verbatim
- severity as structured data — `deaths`, `damages_usd`, or `population_share` —
  plus the display label rendered from it, never typed twice
- `horizons`
- human anchors, each tagged with its source panel (XPT 2022, LEAP 2026,
  P6 bio 2025, the September round) rather than assumed to be XPT

### What must hydrate from it, and does not today

- the model prompt (`run_unified.py`) — already does
- the human elicitation instrument — not built yet; must read the same file
- **graph titles and axis labels** — hardcoded prose today
- **the "what counts as catastrophic" modal** — hardcoded prose today
- tooltips, the data bank's threshold column, the timeline page

### The test that keeps it true

A golden test asserting that **no threshold literal appears in any `.jsx`
chunk** — no `10 million`, no `$1T`, no `10%`. Every such string must arrive
through a blob field. That is what makes "no way for them to become
disentangled" a property of the build rather than a promise.


## Coherence is a measurement, not a constraint

The call was equally explicit here, and the shipped code does not match it.
Nothing is forced: incoherence is flagged in the UI, the prompts do not suggest
that answers should cohere, and incoherent results are not thrown out.
Coherence is used as a measure of consistency, so the questions stay
independent, and the dashboard carries internal checks so a reader can see when
the arithmetic does not work — a warning, not an edit.

### The bug

`code/run_unified.py`'s `PROMPT` states the constraints:

```
Your numbers must respect the logical relations between these questions:
  - Probabilities are non-decreasing across horizons.
  - Within a cause, a higher death threshold is a strictly harder event, so
    probability must not increase as the threshold rises.
  - "All causes" contains every specific cause, so at any threshold and horizon
    no specific cause may exceed it.
  - A question about a narrower event ... may not exceed the broader question
    that contains it.
```

So coherence *is* suggested in the prompt. `tests/test_coherence.py` even says so
in a comment: `HORIZON ... (prompt-enforced both ways)`. Every coherence number
the dashboard currently reports is contaminated by that block.

**Removing it costs nothing, and we already measured that.**
`docs/coherence-experiment.md` ran exactly this comparison: arm B was joint
elicitation with *no* instruction about monotonicity; arm C was arm B plus the
rule, differing by 222 characters. Both hit 0.0% violations. The doc's own
conclusion, already written, is: **"Do not state the constraint. Arm C bought
nothing over arm B."** The runner never followed it.

### What to change

1. **Delete the constraint block from `run_unified.py`'s `PROMPT`.** Keep one
   call with every question — that is arm B, and it is what the experiment
   licensed. Joint context does the work; the instruction does not.
2. **Keep the checks minimal and obvious.** Not a growing lattice. The
   inequalities described on the call are the right scope: the risk of an
   AI-enabled extinction event should never be higher than the all-cause risk of
   an extinction event. Basic containment, nothing that needs an argument.
3. **Check after the fact, in Python.** `redlines/coherence.py` already does
   exactly this and needs no redesign — only its two hardcoded relation maps
   need to move into the question JSON.
4. **Warn, never discard.** Already true. Keep it true.
5. **Move the check into "Why Trust This"** — the project lead's proposal on
   the call: the claim is not that coherence is forced, but that the questions
   are framed reasonably and, when they are, there is no evidence of an
   internally incoherent model.
6. **`tests/test_coherence.py` must stop asserting rate ceilings.** It currently
   fails the build if LADDER or CROSS exceeds 2.0%. With the prompt block gone
   those rates will rise, and that is a *result*, not a regression. Report the
   rates; keep at most a loose smoke ceiling that catches a broken run.

Expect the reported violation rate to go up. That is the point — a rate measured
without a prompt telling the model the answer is the only rate worth publishing.


## What the swap costs

- **Nuclear leaves entirely.** No nuclear question survives.
- **Extinction leaves entirely.** Human disempowerment replaces it as the
  worst-case concept — the better question, but with no anchor and no history.
  Its definition was still under external review at the time of writing.
- **There is no "all causes" ladder any more.** "AI-related incident" contains
  the three AI sub-types, not nuclear and not natural pandemics.

**Two of the four "stable subset" questions do not survive.** `config.py` and
`cron_run.sh` both record that 9 / 10 / 3 / 4 were *"confirmed to survive"*
the Auto-ARC rewrite. In fact:

| Question | Survives? |
|---|---|
| 9. Total Catastrophic Risk | yes → General catastrophe, same wording, same 10% threshold |
| 3. AI Catastrophic Risk | yes → AI catastrophe, same wording, same 10% threshold |
| 10. Total Extinction Risk | **no** |
| 4. AI Extinction Risk | **no** |

The cost is near zero right now. The unified run log holds one elicitation date,
2026-08-14. The next scheduled weekly run was **2026-08-21**. Swap before then
and almost no series is discarded.

**Nine of eleven XPT human anchors go.** Only two carry over, because only two
questions keep their wording — and they keep it exactly, including the 10%
threshold:

| New question | XPT anchor (super / expert, %) |
|---|---|
| General catastrophe | 2030 0.85 / 2.7 · 2050 3.85 / 10.0 · 2100 9.09 / 20.85 |
| AI catastrophe | 2030 0.01 / 0.23 · 2050 0.725 / 3.0 · 2100 2.125 / 10.0 |

Everything else waits on September, except the LEAP and P6-bio cells — and
neither dataset is in this repo. Both must be sourced.


## What must change in code

Ordered by whether it blocks the swap.

**Fix now, independently of the swap**

1. **The hardcoded catastrophe threshold** in `80-app.jsx` and `70-modal.jsx`.
   It contradicts the question it labels. See the SSOT section.
2. **Delete the constraint block from `run_unified.py`'s `PROMPT`.** Licensed by
   `docs/coherence-experiment.md` arm B vs arm C.
3. **`tests/test_coherence.py`** stops asserting rate ceilings.

**Un-hardcode, so 7 September is a data drop**

4. **`coherence.py` — `XPT_RELATIONS` and `SUBSET_PAIRS`.** Both hardcoded on
   retired ids. Move into the question JSON as a `relations` block.
5. **`registry.py` — `CATEGORIES`.** Two rail groups replace four.
6. **`config.py` — `BATCH_CAUSE`, `STABLE_SUBSET`, `UNBATCHED`.** `STABLE_SUBSET`
   is legacy and half of it dies; delete it.
7. **Horizons read `spec["questions"][0]["horizons"]`** in `run_unified.py` and
   `graph2.py`. Breaks on the 2045 bio rows. Move to `spec["horizons"]`.
8. **Blob key `xpt` becomes `human`, with a `source` field.** Four surfaces read
   `xpt` and print the literal "XPT 2022".
9. **`graph2.py` — `WORLD_POP`** and `extinction` rung handling.
10. **`graph1.py`** learns to read `featured` ladder ids.
11. **Page copy** — every "XPT 2022 human medians" string.
12. **Batch size.** 35 questions × 4 horizons. Check `max_tokens=32000` holds a
    140-cell submission; the retry guard should not be load-bearing.
13. **Golden tests** regenerate after the swap, not before.

Retire the old forecasts to `archive/`, as the 2026-08-14 cutover did.


## Open questions for the question-set author

1. **2044 or 2045 for the bio horizon?** The markdown says 2044, the spreadsheet
   says 2045. P6 bio resolves before 2045-01-01.
2. **The near-term horizons agreed on the call are not in the sheet yet.** Next
   6 months and next 12 months. Are they coming in the next revision? They are
   the highest-value cells in the set for this dashboard.
3. **The 100,000-death suggestion from the call — which question?** The incident ladder
   already has a 100k rung, so the plain reading is that it applies to the
   catastrophe questions, which today carry only the 10%-of-population
   threshold. Confirm. If so, those questions gain a second severity level and
   stop being single points on the ladder axis.
4. **Is "AI-related incident" formally the union of the other three?** The
   definition implies it. It becomes a check we run and publish.
5. **Can we have the LEAP (2026-06) and P6-bio (2025-07) numbers as data?**
   Both are named as human comparisons; neither is in this repo.
6. **The severity criteria say "more than X million excess deaths"** but the
   rungs go down to 100 deaths. Template artifact.
7. **Two aggregation rules.** Incident questions ask about "one or more …
   cumulatively"; the catastrophe questions require "a single catastrophe or a
   single causally-linked chain of events". Intended?
8. **Two window conventions.** The catastrophe questions use a contiguous window
   of at most five years starting on or after 2025-12-31. The incident questions
   use onset before the end of the year with three-year damage accrual.
   Intended?
9. **Human disempowerment has no severity axis and no containment relation** to
   any other question. Standalone, or meant to be comparable? Its definition is
   already flagged for external review.
10. **A suggestion worth eight questions: add an "any-cause incident" ladder** —
    the same eight rungs, no AI condition. It restores the all-causes container
    the set now lacks, lets every AI sub-type be checked against a true ceiling,
    and gives the paper a direct read on the AI share of catastrophic risk at
    every severity.
