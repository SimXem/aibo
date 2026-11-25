# Cellcheck: is a headline forecast the same asked alone?

The published AIRO call asks every question at every horizon under every
scenario in **one** call: 6,132 probabilities side by side. Cellcheck asks
twenty cells of the headline question one at a time, each in its own call,
five times per model, and compares each cell's isolated answers with the same
cell in the published (unified) call of the same day.

The headline question is `catastrophe:ai`: a global AI-related catastrophe in
which AI is the proximate cause of deaths reaching at least 10% of the
population. No other question (epidemic, cyber, misalignment, the ladders) is
asked.

| File | What it is |
|---|---|
| `../cellcheck.toml` | The experiment: the twenty cells, five repeats, the two models |
| `cells.html` | Every cell with the exact prompt the runner builds, collapsed (open it in a browser) |
| `build_cells_page.py` | Rebuilds `cells.html` (no model is called) |
| `../../code/run_cellwise.py` | The runner: one call per cell, after the model's ECI step |
| `../../code/analyze_cellcheck.py` | The comparison with the published call |

## The cells

A scenario is a (policy, capability) pair. `sq`, `p1`..`p5` assume a policy
and hold capability at the model's own ECI 50th percentile. `eci_p10`..`eci_p90`
keep the policy the model expects and set capability to one of its own ECI
percentiles. `unconditional` is the world as the model expects it.

Every cell is drawn at random from one seed (`random.Random(20261117)`);
nothing is chosen by hand. `../cellcheck.toml` records the exact procedure, and
a test checks the file against it.

**Fifteen cells on a horizon grid.** Five scenarios are drawn from the 14:
eci_p90, p1, unconditional, p2a and eci_p25. Each is asked at 2030, 2050 and
2100, so the same five appear at every horizon. At each horizon the five
prompts are dealt one scenario each, and the deals are redrawn until no
prompt gets the same scenario twice. A prompt therefore never comes with one
fixed scenario:

| Prompt | 2030 | 2050 | 2100 |
|---|---|---|---|
| none (baseline) | unconditional | p2a | p1 |
| independent | p1 | eci_p90 | eci_p25 |
| recent | p2a | eci_p25 | unconditional |
| critical | eci_p25 | p1 | eci_p90 |
| two-step | eci_p90 | unconditional | p2a |

The scenarios: unconditional is expected policy and expected capability; p1
is federal preemption of state AI laws and p2a a US compute cap on frontier
R&D, both with capability at the model's own ECI p50; eci_p25 and eci_p90
keep the expected policy and set capability to the model's own ECI 25th and
90th percentiles.

**Five more cells.** These are drawn with the same generator from the 405
other prompt × horizon × scenario cells:

- none, 2030, p3b
- independent, 6mo, eci_p25
- independent, 2050, eci_p75
- recent, 6mo, p4
- two-step, 2100, eci_p75

Each cell is asked 5 times by **Opus 5.5** and **GPT-6.2 Astra** (the model
set `cellcheck` in `redlines/registry.py`; GPT-6.1 Sol until 2026-11-18).
GPT-6.2 Astra is not added to the dashboard's panel. It is newer than the
pinned pi, which `redlines/pi_loop.py` tells about it from
`data/pi_models.json`. Every repeat starts with the model's ECI step, since every cell prompt
quotes the model's ECI forecast as the joint prompt does:

- per model: 100 cell calls and 25 ECI steps;
- in all: **250 calls**.

The prompts are the published minimal instrument's, with research on as
published (web search and page reading).

## Running it

Every step runs from `dashboards/airo/` with the repository's environment:

```bash
cd dashboards/airo
source ../../.venv/bin/activate
```

1. **Keys.** The keys file is `~/.config/fri-forecaster/env`, or the file
   `$FORECASTER_ENV_FILE` names. It needs `ANTHROPIC_API_KEY`,
   `OPENAI_API_KEY` (with access to GPT-6.2 Astra) and `TAVILY_API_KEY`.
2. **When.** Run on a publication day (Wednesday or Friday) after the
   12:00 UTC published run, and finish on the same UTC day. Then the
   published call it is compared with was asked the same day, and `--resume`
   works (it refuses a run of another day).
3. **Look first** (free):
   ```bash
   python code/run_cellwise.py --experiment cellcheck --dry-run
   ```
4. **Pilot one prompt per model** (10 calls: the baseline prompt's 4 cells
   and its ECI step, for each model; a few dollars). This shows
   that both models answer and what a call really costs. Each call prints its
   tokens, and the run ends with the priced spend.
   ```bash
   python code/run_cellwise.py --experiment cellcheck --condition none --max-repeats 1
   ```
5. **The full run.** Continue the pilot's log; it skips what is done:
   ```bash
   python code/run_cellwise.py --experiment cellcheck --max-calls 250 --workers 10 \
       --resume results/experiments/cellcheck-<run>-cells.jsonl
   ```
   `--max-calls 250` is needed because the runner refuses more paid calls
   than one prompt's default run unless told otherwise. If calls fail, run the
   same command again; it re-asks only what is missing.
6. **Compare.** After that day's published run is on the dashboard, download
   its `redlines-data.zip` (the Download button) into `private/`, which is
   gitignored, and run:
   ```bash
   python code/analyze_cellcheck.py private/redlines-data.zip \
       results/experiments/cellcheck-<run>-cells.jsonl --json private/cellcheck.json
   ```
   It uses the published calls of the cells' own day. `--joint-day YYYY-MM-DD`
   compares with another day instead, and the report flags the mismatch.

The comparison pairs each model's cells with joint rows of the same label.
The download holds only the published panel's models, so **GPT-6.2 Astra has
nothing to compare with unless production's panel seats it that day**; the
report then lists its cells under "no joint answer". If its joint rows use a
dated model id (`openai/responses/gpt-6.2-astra-YYYY-MM-DD`), the report warns
that the ids differ. Change the id in `cellcheck_models` in
`redlines/registry.py` and run again.

## Cost

These are estimates from pi's prices and the logged calls of older models. The
pilot prints the real spend.

| Searching per call | Opus 5.5 | GPT-6.2 Astra | Search (Tavily) | All 250 calls |
|---|---|---|---|---|
| Typical (4 searches, 2 page reads) | ~$75–105 | ~$40 | ~$17 | ~$130–160 |
| Heavy (10 searches, 4 page reads) | ~$190–310 | ~$100 | ~$45 | ~$335–455 |

**Why Opus still costs more.** GPT-6.2 Astra's tokens cost twice Opus's
($8/$40 vs $4/$20 per million in/out; $0.40 cached input). But at the
published reasoning level ("max" for Anthropic, "xhigh" for OpenAI), Opus has
thought several thousand tokens per turn in the logged calls, and those output
tokens are most of its cost. No call of GPT-6.2 Astra is logged yet: its
column is GPT-6.1 Sol's estimate scaled by the price (4x), the least certain
number here.

Prompt caching is on for both models: pi marks the system prompt, the tools
and the latest turn for Anthropic's cache. Neither model is stopped from
calling several tools in one turn.

The cost could be cut further by lowering Opus's reasoning level or by telling
it to search in batches. Either change would alter what is asked, so its cells
would no longer match the published call they are compared with. Neither is
done.

## What it writes

The run writes three files under `results/experiments/`:

- **`cellcheck-<run>-cells.jsonl`: the record, one row per answer as each call
  completes.**
  - An ECI step row (`step: "eci"`) holds the model's five ECI percentiles.
  - A cell row (`step: "cell"`) holds the model, the prompt (`condition`),
    `horizon`, `scenario_id`, the `probability`, the call's rationale and
    sources, `replicate` (1–5), and the call's id.
  - The first row of each call also carries the prompt, the evidence (every
    search and page read) and the token use and price.
- **`cellcheck-<run>-instrument.jsonl` and `cellcheck-<run>.jsonl`: the same
  answers in the published rows' format**, all scenarios and the
  unconditional slice, so other analyses can read them like a joint run.

Every row says `unit: "cell"` and carries a protocol (`percell:…`) that no
dashboard view reads.

The comparison prints, per model:

- **A table of the 20 cells:** the isolated mean (with n and SD), the unified
  answer, the absolute error in percentage points, and the difference in
  log-odds with its z.
- **The MAE** in percentage points and in log-odds, each with a simulated
  p-value.
- **The mean signed difference** (+ means the isolated cell says more).
- **The chi-square test**, X² on 20 degrees of freedom, with the noise
  estimates behind it.
- **A second chi-square** that assumes the unified call is as noisy as an
  isolated one.
- **The ECI gap:** both arms' ECI 50th percentiles.

It then prints both models together (40 cells). `--json` saves all of it.

How the test works: under "no difference", each cell's isolated mean minus
its unified answer is noise. That noise is the isolated repeats' spread plus
the unified call's own noise. The unified noise is estimated from the same
day's five published calls of the same model across all 84 cells of the
question. Cells from one call share that call's random draw, and the
covariance allows for it. The module docstring of `code/analyze_cellcheck.py`
gives the details. On synthetic data with no difference, X² averages 20 on 20
degrees of freedom and rejects 5% of the time at p < 0.05.

## Rebuilding the page

`cells.html` renders the prompts for one date. On the run day, the date, the
6- and 12-month horizons and the ECI target date move with it. To render
another date:

```bash
python experiments/cellcheck/build_cells_page.py --date 2026-11-18
```
