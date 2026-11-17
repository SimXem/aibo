# Per-cell: the published instrument asked one cell at a time

The published AIRO call answers every question at every horizon under every
scenario in **one** call: 6,132 probabilities side by side. Each answer is
therefore given beside thousands of others. The per-cell experiment asks the
headline question one cell at a time, each in its own call. It then splits
the difference from the published call into three parts.

A cell is one question at one horizon under one scenario. The default run
asks the headline question, `catastrophe:ai`: a global AI-related catastrophe
in which AI is the proximate cause of deaths reaching at least 10% of the
population. It asks it at all six horizons (6 months, 12 months, 2028, 2030,
2050, 2100) under all 14 scenarios (unconditional, the eight LEAP policies,
and the five ECI capability levels). That is **84 cell calls** per model per
prompt.

The experiment has five conditions, the published series' five prompts under
the same names: `none` (baseline), `independent`, `recent`, `critical`,
`two-step`. Each model × prompt run is one **replicate** of the comparison.

| File | What it is |
|---|---|
| `../percell.toml` | The experiment: the five prompts as cell conditions |
| `../../code/run_cellwise.py` | The runner: one call per cell, after the model's ECI step |
| `../../code/analyze_percell.py` | The comparison with the published call of the same day |

## What a cell call sees

A cell call gets the published minimal prompt with everything that belongs to
other cells taken out, and nothing reworded:

- the question's text and resolution criteria, at its one horizon;
- the one scenario, as the published prompt renders it;
- the prompt's added instruction, if it has one;
- research on, as published: the model may search the web and read pages.

Every condition's cells are conditioned on the model's own forecast of the
frontier ECI. In the published call, the model makes that forecast in Step 1
of the same call. Here it is a separate **ECI step**, one per model per
prompt per repeat, whose five numbers every cell prompt then quotes. It is
the only earlier answer a cell call is shown.

The module docstring of `code/run_cellwise.py` gives the full detail.

## Running it

Every step runs from `dashboards/airo/` with the repository's environment:

```bash
cd dashboards/airo
source ../../.venv/bin/activate
```

1. **Keys.** The keys file is `~/.config/fri-forecaster/env`, or the file
   `$FORECASTER_ENV_FILE` names. It needs `TAVILY_API_KEY` and the key of
   each model's lab (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, ...).
2. **When.** Run on a publication day (Wednesday or Friday) after the
   12:00 UTC published run, and finish on the same UTC day. Then the
   published call it is compared with was asked the same day, and `--resume`
   works (it refuses a run of another day).
3. **Look first** (free, no model is called): the plan, the ECI step's prompt
   and the first cell prompts.
   ```bash
   python code/run_cellwise.py --experiment percell --condition none --dry-run
   ```
4. **Run** (paid). Choose the scope:
   ```bash
   # one prompt, one model: 85 calls
   python code/run_cellwise.py --experiment percell --condition none --models "Opus 5.5"

   # one prompt across the panel: 85 calls per model
   python code/run_cellwise.py --experiment percell --condition none

   # all five prompts for one model: 425 calls
   python code/run_cellwise.py --experiment percell --models "Opus 5.5" --max-calls 425
   ```
   The models are the dashboard's panel: the top four runnable models by ECI.
   In this checkout that is GPT-6 Astra, Opus 5.5, Fable 5.1 and Sonnet 5.5.
   `--models` picks some of them.

   The runner refuses to start more paid calls than one prompt's run across
   the selected models unless `--max-calls` says otherwise. If calls fail, add
   `--resume results/experiments/percell-<run>-cells.jsonl` to the same
   command; it re-asks only what is missing.
5. **Compare.** After that day's published run is on the dashboard, download
   its `redlines-data.zip` (the Download button) into `private/`, which is
   gitignored, and run:
   ```bash
   python code/analyze_percell.py private/redlines-data.zip \
       results/experiments/percell-<run>-cells.jsonl --json private/percell.json
   ```
   A joint instrument file from production
   (`state/results/conditional_runs_combined/<run>.jsonl`) reads as well as
   the zip.

Other selections: `--cells`, `--severities`, `--causes`, `--horizons` and
`--scenarios` choose other cells, each with names or patterns and `'*'` for
all. `python code/run_cellwise.py --help` lists them. The comparison below
needs every replicate to ask the same grid of cells.

## Cost

These are estimates from pi's prices, assuming about 4 searches and 2 page
reads per call, with 5% for retries. The run prints each call's tokens and
the priced spend at the end.

| Scope | Calls | Cost |
|---|---|---|
| One prompt, Opus 5.5 | 85 | ~$55–80 |
| One prompt, the four-model panel | 340 | ~$260–340 |
| Five prompts, Opus 5.5 | 425 | ~$285–385 |
| Five prompts, the four-model panel | 1,700 | ~$1,300–1,700 |

Per call, roughly: Fable 5.1 $1.40–2.00, Opus 5.5 $0.55–0.80, Sonnet 5.5
$0.30–0.40 and GPT-6 Astra $0.35, plus about $0.07 of search each. If the
models search heavily, multiply by about 2.5.

## What the comparison measures

On the log-odds scale, for each model × prompt and each cell:

    published answer = answer alone + common shift + cell shift + noise

- **Answer alone:** the cell asked by itself.
- **Common shift:** how far being asked inside the whole call moves every
  cell. It is the mean of (published − alone) over the 84 cells.
- **Cell shift:** how far a particular cell moves beyond that. It is reported
  by horizon, by scenario group, by scenario and cell by cell.

Each estimate is a mean over replicates, with standard errors from the spread
between replicates. The report also tests whether all horizons share one
shift (and all scenarios), and lists every cell with its p and q
(Benjamini-Hochberg).

**The common shift needs many replicates.** All answers of one published call
share that call's random draw, about 0.4 log-odds. That draw is part of the
common shift, so it averages out only across many model × prompt pairs. The
cell shifts compare answers of the same call, where the draw cancels, so they
are measured well with fewer replicates.

**How many replicates the tests need.** The joint test over the six horizons
needs at least 6 replicates, and the one over the 14 scenarios needs at least
14. One model under five prompts gives 5; the four-model panel under five
prompts gives 20.

The module docstring of `code/analyze_percell.py` gives the details.

## What it writes

The run writes three files under `results/experiments/`:

- **`percell-<run>-cells.jsonl`: the record, one row per answer as each call
  completes.**
  - An ECI step row (`step: "eci"`) holds the model's five ECI percentiles.
  - A cell row (`step: "cell"`) holds the model, the prompt (`condition`),
    `horizon`, `scenario_id`, the `probability`, the call's rationale and
    sources, and the call's id.
  - The first row of each call also carries the prompt, the evidence (every
    search and page read) and the token use and price.
- **`percell-<run>-instrument.jsonl` and `percell-<run>.jsonl`: the same
  answers in the published rows' format**, all scenarios and the
  unconditional slice.

Every row says `unit: "cell"` and carries a protocol (`percell:…`) that no
dashboard view reads.

## Related

- `../cellcheck.toml` and `../cellcheck/`: twenty fixed cells asked 5 times
  each by Opus 5.5 and GPT-6.1 Sol, compared cell by cell with a chi-square
  test.
- `../context.toml` and `code/analyze_context.py`: asks whether the other
  horizons in a call move the headline forecast. It sets the cell asked alone
  beside all six horizons asked in one call.
