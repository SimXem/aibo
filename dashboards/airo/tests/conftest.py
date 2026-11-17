"""AIRO's tests run from AIRO's directory, as its scripts do, whichever
directory pytest was started in."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _from_airo_root(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
