"""Declared objectives compose with the gateway's session-pinned delegation surface."""

from types import SimpleNamespace

import pytest

from agent.agent_init import _load_tools
from tests.agent.test_read_file_declared_intent import _configure
from tools.delegate_tool_config import gateway_delegation_inline_scope
from tools.mcp_tool_agent import refresh_agent_mcp_tools, restore_agent_tool_prefix, tool_pin_version


def _built(intent, inline):
    _configure(intent)
    agent = SimpleNamespace(platform="whatsapp", quiet_mode=True)
    with gateway_delegation_inline_scope(inline):
        _load_tools(agent, ["hermes-cli"], None)
    return agent


@pytest.mark.parametrize("intent", [False, True])
@pytest.mark.parametrize("inline", [False, True])
def test_intent_and_joined_delegation_survive_restore_and_rebuild(intent, inline):
    original = _built(intent, inline)
    functions = {tool["function"]["name"]: tool["function"] for tool in original.tools}
    assert ("declared_intent" in functions["read_file"]["parameters"]["required"]) is intent
    controls = {"action", "subagent_id", "message"}
    assert bool(controls & functions["delegate_task"]["parameters"]["properties"].keys()) is not inline

    restored = _built(not intent, not inline)
    restore_agent_tool_prefix(restored, {"version": tool_pin_version(), "tools": original.tools})
    for preserve_prefix in (True, False):
        refresh_agent_mcp_tools(restored, content_aware=True, preserve_prefix=preserve_prefix)
        actual = {tool["function"]["name"]: tool["function"] for tool in restored.tools}
        assert actual["read_file"] == functions["read_file"]
        assert actual["delegate_task"] == functions["delegate_task"]
