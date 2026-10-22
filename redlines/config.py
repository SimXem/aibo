"""Paths, round pins, thresholds, and other shared constants.

Every value here is PORTED (not re-derived) from the script that owned it
before the package existed, so behavior is byte-identical. See the docstring
on each constant for its prior home.
"""
import os
from pathlib import Path

# redlines/config.py -> redlines/ -> repo root. Same depth as the old
# code/*.py scripts' `Path(__file__).resolve().parent.parent`.
REPO_ROOT = Path(__file__).resolve().parent.parent

# External sibling checkouts this pipeline reads from. Each is overridable via
# an env var of the same name, for boxes (e.g. the exe.dev cron host) where
# the checkout doesn't live at the default path.
FBSIM_ROOT = Path(os.environ.get(
    "FBSIM_ROOT", str(Path.home() / "Projects" / "forecastbench-sim")))
FB_DATASETS_ROOT = Path(os.environ.get(
    "FB_DATASETS_ROOT", str(Path.home() / "Projects" / "forecastbench-datasets")))
XRISK_CANARIES_ROOT = Path(os.environ.get(
    "XRISK_CANARIES_ROOT", str(Path.home() / "Projects" / "xrisk-canaries")))

# Graph 3: the only ForecastBench round with a human (superforecaster) arm.
# From code/make_demo_graph3.py's ROUND.
GRAPH3_ROUND = "2024-07-21"

# Graph 4 combined (code/make_demo_combined.py): which FreeCiv eval horizons
# count as "near-term" for the tail-risk subset, and the base-rate band that
# subset is drawn from.
FC_HORIZONS = {"H2", "H3", "H4"}
FC_BAND = (0.05, 0.09)

# Graph 4 combined: minimum Starsim pandemic samples for a model to be scored
# (from code/make_demo_combined.py's PAN_MIN_N).
PAN_MIN_N = 400

# --- Climatology: two different numbers for "the FreeCiv low-prob base rate" ---
#
# These disagree (0.045 vs 0.0458): an inherited discrepancy, not a bug
# introduced by this port — recorded rather than fixed, because reconciling it
# moves Graph 4's tracked numbers.
#
# CLIM_FREECIV_COMBINED is the fallback `class_base_rate` used by
# code/make_demo_combined.py::freeciv_pairs when a question's own base rate is
# missing. Graph 4's golden output depends on exactly this value.
CLIM_FREECIV_COMBINED = 0.045
#
# CLIM_FREECIV_OBSERVED is the fallback `class_base_rate` used by
# archive/litellm-runners/run_eval.py's per-class climatology scoring — the corpus's actual
# observed yes-rate, measured independently of the 0.045 above.
CLIM_FREECIV_OBSERVED = 0.0458

# --- Question-set constants retired by the Auto-ARC swap (2026-08-18) --------
#
# STABLE_SUBSET is gone. It named the four XPT questions (9./10./3./4.) that
# were confirmed to survive the Auto-ARC question-set rewrite, so the scheduled
# job could build a series that the swap would not throw away. Two of the four
# did not survive: #9 and #3 carry over intact as the general and AI catastrophe
# questions, at the same 10%-of-population threshold, but the Auto-ARC set has no
# extinction question at all, so #10 and #4 have no successor. Human
# disempowerment replaces the concept and starts from nothing.
#
# BATCH_CAUSE is gone too. It mapped an XPT question's category to a ladder
# cause so the runner could file it under one. The Auto-ARC set needs no such
# map: every ladder question already names its own cause, and the three
# cross-cutting questions belong to no cause by design.
#
# UNBATCHED survives, with different contents and the same reason: a question
# belongs in the joint call only if it shares the others' context.
#   p6bio:* -- the four P6-bio comparison rows sit at 2045 on a deaths-only
#     severity, so they share neither the ladder's horizon grid nor its
#     disjunctive threshold. They exist to line up with an existing human panel
#     and are elicited separately, the way XPT #2 was.
UNBATCHED = ()
