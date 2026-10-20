"""API keys: from the environment, else from the first env file that has them.

Env files (KEY=value lines, `export ` and quotes tolerated), in order:
$FORECASTER_ENV_FILE if set (and only it), else ~/.config/fri-forecaster/env,
then ~/.config/redlines/env (AIRO's cron box). A set variable is never
overridden. Returns the names of the keys configured afterwards."""
import os
from pathlib import Path

# pi provider id -> the API key it bills to (harness.run requires the model's).
KEY_FOR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GEMINI_API_KEY",
           "xai": "XAI_API_KEY", "openrouter": "OPENROUTER_API_KEY", "deepinfra": "DEEPINFRA_API_KEY"}
KEYS = ("TAVILY_API_KEY",) + tuple(KEY_FOR.values())


def env_paths():
    explicit = os.environ.get("FORECASTER_ENV_FILE")
    if explicit:
        return [Path(explicit).expanduser()]
    return [Path.home() / ".config" / "fri-forecaster" / "env", Path.home() / ".config" / "redlines" / "env"]


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
