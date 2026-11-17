#!/usr/bin/env python3
"""Shim: the real implementation moved to redlines/hydrate.py.

Kept so `from hydrate import REPO, inject` (and any script run as
`python3 code/make_demo_graph1.py`, which sys.path-inserts code/) keeps
working unchanged. See redlines/hydrate.py for the actual logic/docstring.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.hydrate import REPO, LIVE, inject  # noqa: E402,F401
