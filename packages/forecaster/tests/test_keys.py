"""The installation's one keys file (fri_forecaster.keys)."""
import io
import os
from contextlib import redirect_stdout
from pathlib import Path

from fri_forecaster import keys


def keys_file(tmp_path, monkeypatch, text):
    path = tmp_path / "env"
    path.write_text(text)
    monkeypatch.setenv("FORECASTER_ENV_FILE", str(path))
    return path


def test_there_is_one_keys_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FORECASTER_ENV_FILE")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert keys.env_paths() == [Path(tmp_path) / ".config/fri-forecaster/env"]
    monkeypatch.setenv("FORECASTER_ENV_FILE", "/elsewhere/env")
    assert keys.env_paths() == [Path("/elsewhere/env")]


def test_load_keys_exports_the_model_and_search_keys_only(tmp_path, monkeypatch):
    keys_file(tmp_path, monkeypatch, 'export ANTHROPIC_API_KEY="a-1"\nTAVILY_API_KEY=t-1\nTYPESAFE_API_KEY=n-1\n')
    monkeypatch.setenv("TAVILY_API_KEY", "from-the-environment")
    assert keys.load_keys() == ["ANTHROPIC_API_KEY", "TAVILY_API_KEY"]
    assert os.environ["ANTHROPIC_API_KEY"] == "a-1" and os.environ["TAVILY_API_KEY"] == "from-the-environment"
    assert "TYPESAFE_API_KEY" not in os.environ
    assert keys.held("anthropic") and not keys.held("google")
    monkeypatch.delenv("ANTHROPIC_API_KEY")   # load_keys set it outside monkeypatch


def test_value_reads_one_name_without_exporting_it(tmp_path, monkeypatch):
    keys_file(tmp_path, monkeypatch, "TYPESAFE_API_KEY=n-1\n")
    assert keys.value("TYPESAFE_API_KEY") == "n-1" and "TYPESAFE_API_KEY" not in os.environ
    assert keys.value("ABSENT_API_KEY") is None
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-the-environment")
    assert keys.value("TYPESAFE_API_KEY") == "from-the-environment"


def test_the_command_prints_names_and_never_a_value(tmp_path, monkeypatch):
    path = keys_file(tmp_path, monkeypatch, "OPENAI_API_KEY=secret-value\nEMPTY_API_KEY=\n")
    out = io.StringIO()
    with redirect_stdout(out):
        assert keys.main([]) == 0
    assert out.getvalue() == f"{path}: OPENAI_API_KEY\n"
    monkeypatch.setenv("FORECASTER_ENV_FILE", str(tmp_path / "absent"))
    with redirect_stdout(io.StringIO()):
        assert keys.main([]) == 1
