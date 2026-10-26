"""Real executor -> classic CLI progress, independent of verbose JSON output."""

import json
from unittest.mock import patch

import pytest
from rich.text import Text

from tests.agent.test_read_file_intent_display import _configure
from tests.agent.test_read_file_declared_intent import _agent, _execute
from tests.hermes_cli.test_tool_progress_scrollback import _make_cli


@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
@pytest.mark.parametrize("visible", [False, True])
def test_classic_cli_progress_and_callbacks(tmp_path, mode, visible):
    _configure(required=True, visible=visible)
    cli = _make_cli(tool_progress="all", verbose=False)
    cli._modern_layout = False
    agent = _agent()
    starts, completes, metadata, progress = [], [], [], []

    def on_progress(event, name=None, preview=None, args=None, **kwargs):
        cli._on_tool_progress(event, name, preview, args, **kwargs)
        if event == "tool.started":
            progress.append((preview, args, cli._spinner_text))

    agent.tool_progress_callback = on_progress
    agent.tool_start_callback = lambda cid, name, args: starts.append((cid, args))
    agent.tool_complete_callback = lambda cid, name, args, result: completes.append((cid, args))
    agent.tool_result_metadata_callback = lambda cid, name, args, result: metadata.append((cid, args))
    path = tmp_path / "fixture.txt"
    path.write_text("original content", encoding="utf-8")
    raw = "[red]Inspect fixture[/red]\x1b[2J\r\n\u202e\u2066"
    args = {"path": str(path), "declared_intent": raw}
    with patch("cli._cprint") as printed:
        messages = _execute(agent, [args], mode)
    line = "\n".join(str(c.args[0]) for c in printed.call_args_list)
    assert "fixture.txt" in line
    assert ("Inspect fixture" in line) is visible
    assert progress
    for preview, display_args, spinner in progress:
        assert ("Inspect fixture" in preview) is visible
        assert ("Inspect fixture" in spinner) is visible
        if visible:
            assert display_args["declared_intent"] in preview
    for callbacks in (starts, completes, metadata):
        assert len(callbacks) == 1
        cid, safe = callbacks[0]
        assert cid == "read-0"
        assert ("declared_intent" in safe) is visible
        if visible:
            intent = safe["declared_intent"]
            assert all(c.isprintable() for c in intent)
            assert len(intent) <= 80
            assert not Text.from_markup(intent).spans
            assert "[" not in intent
    assert json.loads(messages[-1]["content"])["content"] == "1|original content"
    assert json.loads(messages[1]["tool_calls"][0]["function"]["arguments"]) == args
    assert path.read_text(encoding="utf-8") == "original content"
