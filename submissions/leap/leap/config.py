"""Paths. Outside this directory LEAP uses only the engine (packages/forecaster)
and AIRO's Epoch snapshots, from which the panel is chosen. LEAP_ECI_DIR names
another directory of snapshots and automatic model rows."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
try:
    import fri_forecaster  # noqa: F401
except ImportError:
    # One repository: the engine's source is at packages/forecaster, so a bare
    # checkout works without installing it.
    sys.path.insert(0, str(REPO_ROOT / "packages" / "forecaster"))

ECI_DIR = Path(os.environ.get("LEAP_ECI_DIR") or REPO_ROOT / "dashboards" / "airo" / "data")
CONDITION = "baseline"
