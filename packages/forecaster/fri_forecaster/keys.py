"""API keys: one file for the installation, read by every project.

$FORECASTER_ENV_FILE, else ~/.config/fri-forecaster/env: KEY=value lines
(`export ` and quotes tolerated), mode 600, outside the repository. Every
dashboard and submission gets its keys here and nowhere else, so two jobs
cannot hold different keys for one provider.

load_keys() puts the model and search keys (KEYS) in the environment; a
variable already set is never overridden. value() reads any one name without
exporting it, for a key only one step needs.

    python -m fri_forecaster.keys     # the file and the names it holds, never a value
"""
import os
import sys
from pathlib import Path

# pi provider id -> the API key it bills to (harness.run requires the model's).
KEY_FOR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GEMINI_API_KEY",
           "xai": "XAI_API_KEY", "openrouter": "OPENROUTER_API_KEY", "deepinfra": "DEEPINFRA_API_KEY"}
KEYS = ("TAVILY_API_KEY",) + tuple(KEY_FOR.values())


# Epoch's `organization`, by substring -> pi provider id (the labs a key can be held for).
LABS = ("anthropic", "openai", "google", "xai")


def provider_of(organization):
    """The pi provider for an index record's lab, or None when there is none."""
    org = (organization or "").lower()
    return next((p for p in LABS if p in org), None)


def held(provider):
    """Does this installation hold the API key `provider` (a pi provider id)
    bills to? Reads the env files first, as a run would."""
    load_keys()
    name = KEY_FOR.get(provider)
    return bool(name and os.environ.get(name))


def path():
    """The installation's keys file."""
    explicit = os.environ.get("FORECASTER_ENV_FILE")
    return Path(explicit).expanduser() if explicit else Path.home() / ".config" / "fri-forecaster" / "env"


def env_paths():
    return [path()]


def parse_env(path):
    out = {}
    try:
        text = Path(path).read_text()
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def load_keys(extra_paths=()):
    for path in list(extra_paths) + env_paths():
        values = parse_env(path)
        for k in KEYS:
            if values.get(k):
                os.environ.setdefault(k, values[k])
    return sorted(k for k in KEYS if os.environ.get(k))


def value(name):
    """One key by name, from the environment, else the keys file; None when it
    is in neither. Not exported: for a key a single step needs."""
    return os.environ.get(name) or parse_env(path()).get(name) or None


def main(argv=None):
    """Print the keys file and the names it holds (never a value). Exit 1 when
    it cannot be read or holds none."""
    names = sorted(k for k, v in parse_env(path()).items() if v)
    print(f"{path()}: {', '.join(names) if names else 'no keys (missing, unreadable or empty)'}")
    return 0 if names else 1


if __name__ == "__main__":
    sys.exit(main())
