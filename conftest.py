"""Every test runs without the installation's API keys: no test can spend, and
none passes only because a key happens to be on the machine. A test about keys
sets its own."""
import os

import pytest


@pytest.fixture(autouse=True)
def _no_installation_keys(monkeypatch):
    monkeypatch.setenv("FORECASTER_ENV_FILE", os.devnull)
    for name in [n for n in os.environ if n.endswith("_API_KEY")]:
        monkeypatch.delenv(name)
