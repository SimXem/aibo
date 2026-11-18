# Acceleration: AI catastrophe under self-sustaining acceleration

There are two prompts, asked independently. Neither call sees the other's
prompt or answer.

| | Catastrophe (`../acceleration.toml`) | Elicitation (`../acceleration-elicit.toml`) |
|---|---|---|
| Asks | `catastrophe:ai` at 6 horizons × 13 conditions = 78 probabilities | P(S) and P(F) at 4 dates = 8 probabilities |
| Runner | `code/run_unified.py`, as the published series | `code/run_elicit.py`: `run_cellwise`'s ECI step, alone |
| Scenario set | `data/acceleration_conditions.json` | `data/acceleration_elicit.json` |
| Prompt | `prompt.txt` | `elicitation-prompt.txt` |

Both prompts are rendered for a run date of 2026-11-18.

Both use the same definitions, word for word. Both use the published
`recent` prompt, whose instruction is the last sentence of the agreed
elicitation prompt. Both run through the minimal instrument and the pi loop
with research on. Each asks 2 models (model set `cellcheck`: Opus 5.5 and
GPT-6.1 Sol) 5 times: 10 calls per prompt, 20 in all.

## The conditions

Both prompts describe the events in the same words:

- **S**: software-only self-sustaining acceleration holds without a break for
  at least 6 months, over a period that lies entirely between the run date
  and the date.
- **F**: acceleration with economic feedback holds in the same way, and
  software-only acceleration does not hold at any point within that period or
  before it. Whether it holds afterwards is left open.

The dates are December 31 of 2027, 2028, 2030 and 2040.

| Ids | Condition |
|---|---|
| `unconditional` | The world as the model expects it |
| `sw_2027` … `sw_2040` | S by each date |
| `econ_2027` … `econ_2040` | F by each date |
| `none_2027` … `none_2040` | Neither S nor F by each date |

The elicitation asks for `p_software_only`, P(S) by each date, and
`p_with_economic_feedback`, P(F) by each date. Neither may fall as the date
gets later.

S and F can both hold by the same date: F, and then S after F's period. The
three kinds therefore do not split the outcomes cleanly:

    P(cat) = P(cat|S)·P(S) + P(cat|F)·P(F) + P(cat|neither)·P(neither) − P(cat|S and F)·P(S and F)

Neither prompt asks for the last term.

## Running it

From `dashboards/airo/`, with the repository's environment:

```bash
python code/run_unified.py --experiment acceleration --dry-run          # catastrophe prompt; free
python code/run_elicit.py  --experiment acceleration-elicit --dry-run   # elicitation prompt; free
python code/run_unified.py --experiment acceleration                    # 10 paid calls
python code/run_elicit.py  --experiment acceleration-elicit             # 10 paid calls
```

Each runner refuses the other's experiment.

The rows are unpublished. The catastrophe call writes
`results/experiments/acceleration-<run>.jsonl` (the unconditional rows) and
`…-instrument.jsonl` (every row). The elicitation writes one row per call to
`results/experiments/acceleration-elicit-<run>.jsonl`, with the numbers in
`elicited`.

To change the dates or the minimum duration, edit the constants at the top of
`code/make_acceleration_conditions.py` and run it; it writes both sets.
`--check` says whether they are current. Raise a set's `protocol` if a change
alters what is asked.
