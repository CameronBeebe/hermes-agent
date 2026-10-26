"""Opt-in read objectives reach ordinary labels without changing the tool contract."""

import copy
import json

import pytest

from agent.display import build_tool_label, build_tool_preview, get_cute_tool_message
from hermes_cli.config import atomic_config_write
from hermes_constants import get_hermes_home
from tests.agent.test_read_file_declared_intent import _agent, _execute, _read_schema


def _configure(required=False, visible=False):
    atomic_config_write(get_hermes_home() / "config.yaml", {
        "agent": {"read_file_declared_intent": required},
        "display": {"read_file_declared_intent": visible},
    })


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("visible", [False, True])
def test_display_is_independent_of_required_contract(tmp_path, required, visible):
    _configure(required, visible)
    agent = _agent()
    schema = copy.deepcopy(_read_schema(agent))
    assert ("declared_intent" in schema["parameters"]["required"]) is required
    path = tmp_path / "config.txt"
    path.write_text("unchanged fixture", encoding="utf-8")
    args = {"path": str(path), "offset": 1, "declared_intent": "Identify configuration defaults"}
    for render in (build_tool_preview, build_tool_label):
        label = render("read_file", args)
        assert label is not None
        assert "config.txt L1" in label
        assert (args["declared_intent"] in label) is visible
    assert (args["declared_intent"] in get_cute_tool_message("read_file", args, 0.1)) is visible
    result = json.loads(_execute(agent, [args])[-1]["content"])
    assert result["content"] == "1|unchanged fixture"
    assert path.read_text(encoding="utf-8") == "unchanged fixture"
    # Display changes never rebuild the cached model-facing schema, even mid-session.
    _configure(required, not visible)
    assert (args["declared_intent"] in build_tool_preview("read_file", args)) is not visible
    assert _read_schema(agent) == schema
    missing = json.loads(_execute(agent, [{"path": str(path)}])[-1]["content"])
    assert ("error" in missing) is required


def test_visible_intent_is_bounded_literal_text():
    from rich.text import Text
    from agent.display import redact_tool_args_for_display

    _configure(visible=True)
    raw = "[red]inspect[/red]\x1b[2J\r\n\u202e\u2066\x00\x7f\x85\u2028" + "z" * 200
    args = {"path": "file.txt", "declared_intent": raw}
    safe = redact_tool_args_for_display("read_file", args)
    assert isinstance(safe, dict)
    intent = safe.get("declared_intent", "")
    assert "inspect" in intent
    assert len(intent) <= 80
    assert intent.endswith("…")
    assert all(char.isprintable() for char in intent)
    assert not Text.from_markup(intent).spans
    assert Text.from_markup(intent).plain == intent
    assert "[" not in intent
    assert redact_tool_args_for_display("read_file", safe) == safe
    assert args["declared_intent"] == raw
    assert intent in build_tool_preview("read_file", safe, max_len=0)


@pytest.mark.parametrize("value", [None, 42, [], "", " \n\t", "\u202e\x1b\x00"])
def test_empty_or_invalid_display_metadata_has_no_label(value):
    _configure(visible=True)
    assert build_tool_preview("read_file", {"declared_intent": value}) is None


def test_display_defaults_off_and_does_not_resurrect_redacted_args():
    from hermes_cli.config import load_config
    from agent.display import redact_tool_args_for_display

    assert load_config()["display"]["read_file_declared_intent"] is False
    args = {"declared_intent": "Hidden objective"}
    assert redact_tool_args_for_display("read_file", args) == {}
    assert build_tool_preview("read_file", args) is None
    assert "Hidden objective" not in get_cute_tool_message("read_file", args, 0.1)
