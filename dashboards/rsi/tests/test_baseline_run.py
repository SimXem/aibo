from datetime import datetime, timezone
import json
import sys

import pytest
from fri_forecaster import baseline, harness

from rsi_dashboard import run
from rsi_dashboard.instrument import parse, synthetic


def test_baseline_run_recovers_only_missing_member(tmp_path, monkeypatch):
    source = run.SOURCE.read_text()
    response = synthetic(parse(source))
    members = [{"key": key, "model": "fake/" + key} for key in ("first", "second")]
    monkeypatch.setattr(run, "PROJECT", tmp_path)
    monkeypatch.setattr(run.panel, "panel", lambda **kwargs: (members, {"snapshot": datetime.now(timezone.utc).date().isoformat()}))
    monkeypatch.setattr(run.keys, "load_keys", lambda: ["TAVILY_API_KEY"])
    calls = []

    def scripted(**kwargs):
        calls.append(kwargs["model"])
        assert kwargs["system"] == baseline.SYSTEM
        assert source.rstrip() in kwargs["prompt"]
        assert kwargs["prompt"].endswith(source.rstrip() + "\n\nSubmit your answers using submit_forecast.")
        assert kwargs["min_research"] == 0
        assert kwargs["research_tools"] == ("web_search", "read_page")
        schema = kwargs["tool_parameters"]["submit_forecast"]["properties"]
        assert set(schema["answers"]["required"]) == set(response["answers"])
        assert set(schema["rationales"]["required"]) == set(response["rationales"])
        answer = json.loads(json.dumps(response))
        if kwargs["model"] == "fake/second":
            if calls.count("fake/second") == 1:
                del answer["answers"]["Q1.1"]
            else:
                answer["answers"]["Q5.1"]["probability"] = 70
        return {"answer": answer, "evidence": [], "usage": {}}

    monkeypatch.setattr(harness, "run", scripted)
    monkeypatch.setattr(sys, "argv", ["rsi_dashboard.run"])
    with pytest.raises(ValueError, match="second: invalid submission"):
        run.main()
    out, = (tmp_path / "results").iterdir()
    assert (out / "first.json").exists()
    assert not (out / "ensemble.json").exists()
    monkeypatch.setattr(sys, "argv", ["rsi_dashboard.run", "--resume", str(out)])
    run.main()
    assert sorted(calls) == ["fake/first", "fake/second", "fake/second"]
    ensemble = json.loads((out / "ensemble.json").read_text())
    assert len(ensemble["answers"]) == 18
    assert ensemble["answers"]["Q5.1"]["probability"] == 60

    # The dashboard consumes the completed runner output and verifies its median
    # against the model receipts before presenting it.
    from rsi_dashboard.results import load_run
    snapshot = load_run(out, source, parse(source))
    assert snapshot["answers"]["Q5.1"] == {"probability": 60}
    assert len(snapshot["models"]) == 2
    assert all(len(model["rationales"]) == 5 for model in snapshot["models"])
    ensemble["answers"]["Q5.1"]["probability"] = 61
    (out / "ensemble.json").write_text(json.dumps(ensemble))
    with pytest.raises(ValueError, match="ensemble disagrees"):
        load_run(out, source, parse(source))


def test_paired_conditions_freeze_one_panel_and_never_pool_answers(tmp_path, monkeypatch):
    from fri_forecaster.tools import BLOCK_DOMAINS_ENV, BLOCK_ENV
    from rsi_dashboard.results import load_run
    members = [{"key": "one", "model": "fake/first"}]
    day = datetime.now(timezone.utc).date().isoformat()
    monkeypatch.setattr(run.panel, "panel", lambda **kwargs: (members, {"snapshot": day}))
    monkeypatch.setattr(run.keys, "load_keys", lambda: ["TAVILY_API_KEY"])
    calls = []

    def scripted(**kw):
        calls.append((kw["prompt"], kw["env"]))
        ans = synthetic(parse(run.SOURCE.read_text()))
        ans["answers"]["Q3.2"]["probability"] = 20 if kw["env"][BLOCK_DOMAINS_ENV] else 40
        return {"answer": ans, "usage": {}, "evidence": []}

    monkeypatch.setattr(harness, "run", scripted)
    monkeypatch.setattr(sys, "argv", ["run", "--out", str(tmp_path), "--condition", "both"])
    run.main()
    pair, = tmp_path.iterdir()
    source = run.SOURCE.read_text()
    runs = [load_run(pair / name, source, parse(source)) for name in ("full-web", "fri-blocked")]
    assert [r["answers"]["Q3.2"]["probability"] for r in runs] == [40, 20]
    assert [r["web_access"] for r in runs] == ["full-web", "fri-blocked"]
    assert calls[0][0] == calls[1][0]
    assert [env for _, env in calls] == [{BLOCK_ENV: "", BLOCK_DOMAINS_ENV: ""},
                                         {BLOCK_ENV: "", BLOCK_DOMAINS_ENV: "forecastingresearch.org"}]
    monkeypatch.setattr(sys, "argv", ["run", "--resume", str(pair)])
    run.main()
    assert len(calls) == 2
    from rsi_dashboard.results import load_runs
    assert len(load_runs(tmp_path, source, parse(source), publication=True)) == 2
    (pair / "fri-blocked" / "ensemble.json").unlink()
    with pytest.raises(ValueError, match="incomplete run"):
        load_runs(tmp_path, source, parse(source), publication=True)
