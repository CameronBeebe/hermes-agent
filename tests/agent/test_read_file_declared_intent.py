"""Opt-in read_file intent: real schema, dispatch, files, and durable call IDs."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.agent_init import _load_tools
from hermes_cli.config import atomic_config_write
from hermes_constants import get_hermes_home


def _configure(enabled):
    atomic_config_write(get_hermes_home() / "config.yaml", {
        "agent": {"read_file_declared_intent": enabled},
    })


def _surface():
    agent = SimpleNamespace(platform="cli", quiet_mode=True)
    _load_tools(agent, ["file"], None)
    return agent


def _read_schema(agent):
    return next(t["function"] for t in agent.tools if t["function"]["name"] == "read_file")


def test_intent_schema_is_opt_in_and_frozen_per_agent():
    from toolsets import agent_tool_surface
    import model_tools

    off = _surface()
    baseline = copy.deepcopy(_read_schema(off))
    assert "declared_intent" not in baseline["parameters"]["properties"]
    _configure(True)
    on = _surface()
    params = _read_schema(on)["parameters"]
    assert "declared_intent" in params["required"]
    assert params["properties"]["declared_intent"]["type"] == "string"
    assert _read_schema(off) == baseline

    _configure(False)
    fresh = model_tools.get_tool_definitions(enabled_toolsets=["file"], quiet_mode=True)
    assert next(t["function"] for t in fresh if t["function"]["name"] == "read_file") == baseline
    assert agent_tool_surface(on, fresh) == on.tools
    assert _read_schema(_surface()) == baseline


def _agent():
    from run_agent import AIAgent

    # No model/network needed: the schema, executor, registry and reader stay real.
    with patch("agent.process_bootstrap.OpenAI"), patch(
        "agent.model_metadata.fetch_model_metadata", return_value={}
    ):
        agent = AIAgent(api_key="test-key", base_url="https://example.invalid/v1",
                        enabled_toolsets=["file"], quiet_mode=True,
                        skip_context_files=True, skip_memory=True)
    agent._should_emit_quiet_tool_messages = lambda: False
    return agent


def _execute(agent, calls, mode="sequential"):
    wire = [{"id": f"read-{i}", "type": "function", "function": {
        "name": "read_file", "arguments": json.dumps(args),
    }} for i, args in enumerate(calls)]
    messages = [{"role": "user", "content": "Inspect fixture files"},
                {"role": "assistant", "content": "", "tool_calls": wire}]
    tc = [SimpleNamespace(id=w["id"], type="function", function=SimpleNamespace(**w["function"])) for w in wire]
    agent._flush_messages_to_session_db(messages)
    getattr(agent, f"_execute_tool_calls_{mode}")(
        SimpleNamespace(content="", tool_calls=tc), messages, agent.session_id)
    return messages


@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
@pytest.mark.parametrize("intent", [None, "", " \t\n", 7, False, [], {}])
def test_missing_intent_is_rejected_before_file_reader(tmp_path, mode, intent):
    _configure(True)
    agent = _agent()
    path = tmp_path / "input.txt"
    path.write_text("private fixture content", encoding="utf-8")
    from tools import file_tools
    with patch.object(file_tools, "read_file_tool", wraps=file_tools.read_file_tool) as reader:
        args = {"path": str(path)}
        if intent is not None:
            args["declared_intent"] = intent
        messages = _execute(agent, [args], mode)
    result = json.loads(messages[-1]["content"])
    assert "declared_intent" in result.get("error", "")
    reader.assert_not_called()


@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
def test_real_reads_keep_intents_in_hooks_and_sqlite_but_not_display(tmp_path, monkeypatch, mode):
    from hermes_state import SessionDB
    from hermes_cli.plugins import get_plugin_manager
    from agent.display import build_tool_preview, redact_tool_args_for_display

    _configure(True)
    agent = _agent()
    monkeypatch.setattr("agent.title_generator.maybe_auto_title", lambda *a, **k: None)
    db_path = tmp_path / "state.db"
    db = SessionDB(db_path=db_path)
    db.create_session(session_id="intent-session", source="cli", model="test/model")
    agent._session_db, agent._session_db_created, agent.session_id = db, True, "intent-session"
    agent._last_flushed_db_idx = 0
    agent._flushed_db_message_ids = set()
    agent._flushed_db_message_session_id = None
    agent._persist_disabled = False
    seen = {"pre_tool_call": [], "post_tool_call": []}
    manager = get_plugin_manager()
    for event in seen:
        monkeypatch.setitem(manager._hooks, event, [lambda _event=event, **kw: seen[_event].append(kw)])
    calls = []
    intents = ["  Identify configuration defaults  ", "[red]inspect[/red]\x1b[2J\r\n\u202eobjective"]
    for i, intent in enumerate(intents):
        path = tmp_path / f"input-{i}.txt"
        path.write_text(f"first {i}\nsecond {i}\nthird {i}\n", encoding="utf-8")
        calls.append({"path": str(path), "offset": 2, "limit": 1, "declared_intent": intent})
    try:
        messages = _execute(agent, calls, mode)
    finally:
        db.close()
    with_db = SessionDB(db_path=db_path)
    try:
        durable = with_db.get_messages_as_conversation("intent-session")
    finally:
        with_db.close()
    for i, call in enumerate(durable[1]["tool_calls"]):
        assert json.loads(call["function"]["arguments"]) == calls[i]
    results = [m for m in durable if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in results] == ["read-0", "read-1"]
    for i, result in enumerate(results):
        assert json.loads(result["content"])["content"] == f"2|second {i}"
    for event, payloads in seen.items():
        assert len(payloads) == 2, (event, payloads)
        by_id = {p["tool_call_id"]: p for p in payloads}
        for i in range(2):
            assert by_id[f"read-{i}"]["args"]["declared_intent"] == intents[i]
    assert len(messages) == len(durable)
    for args in calls:
        display = redact_tool_args_for_display("read_file", args)
        assert isinstance(display, dict)
        assert "declared_intent" not in display
        assert args["declared_intent"] not in (build_tool_preview("read_file", display) or "")


@pytest.mark.parametrize("enabled", [False, True])
def test_resume_uses_pinned_contract_not_new_config(tmp_path, enabled):
    from tools.mcp_tool_agent import restore_agent_tool_prefix, tool_pin_version

    _configure(enabled)
    original = _surface()
    saved = {"version": tool_pin_version(), "tools": original.tools}
    _configure(not enabled)
    agent = _agent()
    restore_agent_tool_prefix(agent, saved)
    assert agent.tools == original.tools
    path = tmp_path / "resume.txt"
    path.write_text("resume fixture", encoding="utf-8")
    result = json.loads(_execute(agent, [{"path": str(path)}])[-1]["content"])
    if enabled:
        assert "declared_intent" in result["error"]
    else:
        assert result["content"] == "1|resume fixture"


@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
def test_off_reads_without_intent_and_does_not_validate_extra_metadata(tmp_path, mode):
    agent = _agent()
    assert "declared_intent" not in _read_schema(agent)["parameters"]["properties"]
    # A newly enabled agent must not change this existing agent's execution contract.
    _configure(True)
    assert "declared_intent" in _read_schema(_surface())["parameters"]["required"]
    calls = []
    for i, extra in enumerate([{}, {"declared_intent": None}, {"declared_intent": 42}]):
        path = tmp_path / f"legacy-{i}.txt"
        path.write_text(f"legacy {i}", encoding="utf-8")
        calls.append({"path": str(path), **extra})
    results = _execute(agent, calls, mode)[2:]
    assert [json.loads(m["content"])["content"] for m in results] == [f"1|legacy {i}" for i in range(3)]


@pytest.mark.parametrize("intent", [None, "x", "This objective deliberately exceeds ten words without being rejected by a brittle word counter"])
def test_intent_is_type_and_blank_validation_not_word_count(tmp_path, intent):
    _configure(True)
    agent = _agent()
    path = tmp_path / "objective.txt"
    path.write_text("objective fixture", encoding="utf-8")
    result = json.loads(_execute(agent, [{"path": str(path), "declared_intent": intent}])[-1]["content"])
    if intent is None:
        assert "declared_intent" in result["error"]
    else:
        assert result["content"] == "1|objective fixture"


@pytest.mark.parametrize("with_path", [False, True])
def test_cli_progress_never_renders_intent_even_without_path(tmp_path, capsys, with_path):
    _configure(True)
    agent = _agent()
    agent.quiet_mode = False
    agent.verbose_logging = True
    agent.tool_progress_mode = "all"
    starts = []
    agent.tool_start_callback = lambda call_id, name, args: starts.append(args)
    intent = "[red]UNTRUSTED_OBJECTIVE[/red]\x1b[2J\r\n\u202e"
    args = {"declared_intent": intent}
    if with_path:
        path = tmp_path / "display.txt"
        path.write_text("display fixture", encoding="utf-8")
        args["path"] = str(path)
    _execute(agent, [args])
    assert "UNTRUSTED_OBJECTIVE" not in capsys.readouterr().out
    assert starts and all("declared_intent" not in a for a in starts)


@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
def test_mixed_batch_rejects_only_invalid_call_and_keeps_correlation(tmp_path, monkeypatch, mode):
    from hermes_cli.plugins import get_plugin_manager
    from tools import file_tools

    _configure(True)
    agent = _agent()
    posts = []
    monkeypatch.setitem(get_plugin_manager()._hooks, "post_tool_call", [lambda **kw: posts.append(kw)])
    path = tmp_path / "mixed.txt"
    path.write_text("mixed fixture", encoding="utf-8")
    calls = [{"path": str(path), "declared_intent": ""},
             {"path": str(path), "declared_intent": "Inspect mixed batch fixture"},
             {"path": str(path), "declared_intent": []}]
    with patch.object(file_tools, "read_file_tool", wraps=file_tools.read_file_tool) as reader:
        results = _execute(agent, calls, mode)[2:]
    assert reader.call_count == 1
    assert "declared_intent" not in reader.call_args.kwargs
    assert [m["tool_call_id"] for m in results] == ["read-0", "read-1", "read-2"]
    assert json.loads(results[1]["content"])["content"] == "1|mixed fixture"
    for i in (0, 2):
        assert "declared_intent" in json.loads(results[i]["content"])["error"]
    assert len(posts) == 3
    by_id = {p["tool_call_id"]: p for p in posts}
    for i, args in enumerate(calls):
        assert by_id[f"read-{i}"]["args"] == args
    assert by_id["read-0"]["error_type"] == "invalid_declared_intent"
    assert by_id["read-2"]["error_type"] == "invalid_declared_intent"
