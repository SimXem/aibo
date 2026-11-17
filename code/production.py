#!/usr/bin/env python3
"""The production launcher's fixed path. The scheduler is packages/ops/production.py;
the installation's `airo` command runs this file in the live release, and a
deploy runs it in the candidate, so it stays here whatever else moves."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / 'packages/ops/production.py'), run_name='__main__')
