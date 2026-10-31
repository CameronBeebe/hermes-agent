"""Saved assessment inspection never re-reads files or exports by default."""
import json

import pytest


def test_offline_replay_recomputes_label_without_network(tmp_path, monkeypatch, capsys):
    from scripts.read_assessment import main
    from agent import read_assessment_typesafe as adapter
    from tests.agent.test_read_assessment import response
    record = {"assessment_id": "saved", "tool_call_id": "call-1", "session_id": "session-1",
              "rubric_version": "read-v1", "provider": "typesafe", "requested_model": "jev-latest",
              "state": {"evidence": {}}, "label": "wrong", **response()}
    path = tmp_path / "saved.json"
    path.write_text(json.dumps(record))
    def forbidden(**kwargs):
        pytest.fail("offline replay must not use network")
    monkeypatch.setattr(adapter, "http_client", forbidden)
    assert main([str(path)]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["label"] == "helpful"
    assert replay["tool_call_id"] == "call-1"
    assert json.loads(path.read_text())["label"] == "wrong"


def test_rescore_requires_explicit_export_consent(tmp_path):
    from scripts.read_assessment import main
    path = tmp_path / "saved.json"
    path.write_text("{}")
    with pytest.raises(SystemExit):
        main([str(path), "--rescore"])


def test_rescore_uses_saved_evidence_not_live_file(tmp_path, monkeypatch, capsys):
    from scripts.read_assessment import main
    import httpx
    from agent import read_assessment_typesafe as adapter
    from tests.agent.test_read_assessment import response
    record = {"assessment_id": "saved", "tool_call_id": "call-1", "session_id": "session-1",
              "rubric_version": "read-v1", "provider": "typesafe", "requested_model": "jev-latest",
              "state": {"evidence": {"result_excerpt": {"text": "SAVED SYNTHETIC"}}}}
    path = tmp_path / "saved.json"
    path.write_text(json.dumps(record))
    monkeypatch.setenv("TYPESAFE_API_KEY", "synthetic")
    real_client = httpx.Client
    sent = []
    monkeypatch.setattr(adapter, "http_client", lambda **kw: real_client(transport=httpx.MockTransport(
        lambda req: sent.append(json.loads(req.content)) or httpx.Response(200, json=response())), **kw))
    assert main([str(path), "--rescore", "--allow-export"]) == 0
    assert json.loads(sent[0]["state"]) == record["state"]
    assert json.loads(capsys.readouterr().out)["label"] == "helpful"
    assert json.loads(path.read_text()) == record
