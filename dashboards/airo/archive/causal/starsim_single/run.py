"""Runner for the single-region continuous design: starsim_causal/run.py with the
quantile prompt and a quantile parser. Same flags (--dry-run, --pilot, --tag, ...).

  uv run python results/causal/starsim_single/run.py --dry-run
  uv run python results/causal/starsim_single/run.py --pilot
  uv run python results/causal/starsim_single/run.py --reps 3
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
import importlib.util  # noqa: E402

sys.path.insert(0, str(HERE.parent / "starsim_causal"))   # llm, models, prompts for the base runner
from qprompts import KEYS, prompt  # noqa: E402

_spec = importlib.util.spec_from_file_location("causal_run", HERE.parent / "starsim_causal" / "run.py")
base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(base)


def parse(txt: str, keys) -> dict | None:
    """Last JSON object with all quantile keys as numbers ≥ 0; sorted non-decreasing
    (a model listing them out of order is re-sorted, not rejected)."""
    txt = txt.replace("\\{", "{").replace("\\}", "}")
    for o in reversed(re.findall(r"\{[^{}]*\}", txt)):
        try:
            d = json.loads(o)
            vals = [float(str(d[k]).replace(",", "")) for k in keys]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if all(v >= 0 for v in vals):
            return dict(zip(keys, sorted(vals)))
    return None


base.CLASSES = {
    "baseline": dict(keys=KEYS, pilot_idx=(0, 5), prompt=lambda it: prompt(it["report"], it["question"])),
    "intervention": dict(keys=KEYS, pilot_idx=(0, 5),
                         prompt=lambda it: prompt(it["report"], it["question"], it["intervention"])),
}
base.parse = parse
base.ITEMS_FILE = HERE / "worlds.json"
base.ITEMS_PATH = base.ITEMS_FILE

if __name__ == "__main__":
    if "--out-dir" not in sys.argv:
        sys.argv += ["--out-dir", str(HERE / "results")]
    if "--worlds" not in sys.argv:
        sys.argv += ["--worlds", str(HERE / "worlds.json")]
    base.main()
