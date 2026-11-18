"""Compatibility import for the shared forecasting research tools."""
import sys
from pathlib import Path

try:
    from fri_forecaster import tools
except ModuleNotFoundError as exc:
    if exc.name != "fri_forecaster":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/forecaster"))
    from fri_forecaster import tools

sys.modules[__name__] = tools
