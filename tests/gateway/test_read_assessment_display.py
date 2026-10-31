"""Actual read -> gateway print projection -> classic CLI render, no external IO."""
import json

import httpx
import pytest

from agent import read_assessment_typesafe as adapter
from gateway import local_viewer_events
from gateway.config import Platform
from hermes_cli.gateway_agent import GatewayAgent
from tests.agent.test_read_assessment import configure, response
from tests.agent.test_read_file_declared_intent import _agent, _execute
from tests.gateway.test_local_viewer_events_turn import _turn


@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
def test_live_annotation_reaches_classic_cli_via_gateway(tmp_path, monkeypatch, capsys, mode):
    configure()
    monkeypatch.setenv("TYPESAFE_API_KEY", "synthetic")
    real_client = httpx.Client
    monkeypatch.setattr(adapter, "http_client", lambda **kw: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response())), **kw))
    agent = _agent()
    published = []
    previous = local_viewer_events.wire(_turn(Platform.LOCAL, published), agent)
    paths = []
    for i in range(2):
        path = tmp_path / f"fixture-{i}.txt"
        path.write_text(f"fixture {i}")
        paths.append({"path": str(path), "declared_intent": "Inspect fixture"})
    try:
        _execute(agent, paths, mode)
    finally:
        local_viewer_events.restore(agent, previous)
    viewer = object.__new__(GatewayAgent)
    viewer.suppress_status_output = False
    from cli import _cprint
    viewer._print_fn = _cprint
    for kind, payload in published:
        viewer._dispatch(kind, payload, None, {})
    text = capsys.readouterr().out
    for i in range(2):
        assert f"read_file [read-{i}]: helpful" in text


def test_hostile_call_id_and_suppressed_output(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    from agent.read_assessment import assess_read
    configure()
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    agent = _agent()
    ref = SimpleNamespace(name="read_file", call_id="evil[red]\x1b[2J\n\u202e", args={})
    assess_read(agent, [], ref, json.dumps({"content": "fixture"}), blocked=False, is_error=False)
    text = capsys.readouterr().out
    assert "\x1b[2J" not in text and "\u202e" not in text and "[red]" not in text
    agent.suppress_status_output = True
    assess_read(agent, [], ref, json.dumps({"content": "fixture"}), blocked=False, is_error=False)
    assert not capsys.readouterr().out
