"""Behavior contracts for the standalone, observational context-map experiment."""
import importlib
import importlib.util
import json

import pytest


def api():
    assert importlib.util.find_spec("scripts.context_map") is not None, "context-map implementation missing"
    return importlib.import_module("scripts.context_map")


@pytest.mark.parametrize("mode", ["heading", "window"])
@pytest.mark.parametrize("text", ["", "# One\r\naé\r\n## Two\n" + "x" * 41, "no newline", "a\nb\n"])
def test_segmentation_complete_exact_and_bounded(mode, text):
    regions = api().segment("fixture.md", text, mode, 12)
    assert "".join(text[r["start"]:r["end"]] for r in regions) == text
    cursor = 0
    for r in regions:
        assert r["start"] == cursor
        assert 0 < r["end"] - r["start"] <= 12
        assert r["line_start"] == text.count("\n", 0, r["start"]) + 1
        assert r["line_end"] == text.count("\n", 0, r["end"] - 1) + 1
        cursor = r["end"]
    assert cursor == len(text)


def test_heading_and_equal_window_are_distinct_and_deterministic():
    m = api()
    text = "# A\na\n# B\nb\n"
    heading = m.segment("f", text, "heading", 100)
    assert [text[r["start"]:r["end"]] for r in heading] == ["# A\na\n", "# B\nb\n"]
    assert m.segment("f", text, "window", 100)[0]["end"] == len(text)
    assert heading == m.segment("f", text, "heading", 100)
    with pytest.raises(ValueError):
        m.segment("f", text, "heading", 0)


def test_map_composition_keeps_exact_slices_and_flags_unknowns():
    m = api()
    assert hasattr(m, "compose"), "map composition missing"
    text = "# Direct\nevidence\n# Glossary\nmeaning\n# Other\nunrelated\n# Unknown\n?"
    regions = m.segment("f.md", text, size=100)
    scores = {r["id"]: dict.fromkeys(m.SIGNALS, 0.0) for r in regions[:3]}
    for values in scores.values():
        values["evidence"] = 1.0
    scores[regions[0]["id"]]["direct"] = .9
    scores[regions[1]["id"]]["prerequisite"] = .85
    enriched = m.compose(text, regions, scores, enriched=True)
    baseline = m.compose(text, regions, scores, enriched=False)
    assert enriched["retained"] == [regions[i]["id"] for i in (0, 1, 3)]
    assert baseline["retained"] == [regions[i]["id"] for i in (0, 3)]
    assert enriched["omitted"] == [regions[2]["id"]]
    assert enriched["regions"][3]["status"] == "unavailable"
    assert enriched["regions"][1]["reasons"] == ["prerequisite"]
    assert enriched["packet"] == "".join(text[r["start"]:r["end"]] for r in enriched["regions"] if r["selected"])
    assert enriched["selected_chars"] == len(enriched["packet"])
    # Unknown or ambiguous scores are NEVER silently treated as irrelevant.
    scores[regions[0]["id"]]["direct"] = .5
    assert m.compose(text, regions, scores)["regions"][0]["status"] == "ambiguous"
    assert m.compose(text, regions, scores)["regions"][0]["selected"]


def test_neighbor_signal_recovers_only_bounded_adjacent_regions():
    m = api()
    assert hasattr(m, "compose"), "map composition missing"
    text = "abcdefghijklmno"
    regions = m.segment("f", text, "window", 3)
    scores = {r["id"]: dict.fromkeys(m.SIGNALS, 0.0) for r in regions}
    for s in scores.values():
        s["evidence"] = 1
    scores["r0002"].update(direct=.9, neighbor=.9)
    result = m.compose(text, regions, scores)
    assert result["retained"] == ["r0001", "r0002", "r0003"]
    assert result["regions"][1]["reasons"] == ["neighbor_of:r0002"]


def test_service_questions_cover_all_regions_explicitly_and_validate_answers():
    m = api()
    assert hasattr(m, "questions"), "parallel questions missing"
    regions = m.segment("manual.md", "# A\na\n# B\nb\n", size=100)
    qs = m.questions("Find limits", "read policy", regions, True)
    assert len(qs) == len(regions) * len(m.SIGNALS)
    for r in regions:
        for signal in m.SIGNALS:
            instructions = qs[r["id"] + "." + signal]["instructions"]
            assert "Find limits" in instructions and "read policy" in instructions
            assert "manual.md" in instructions and r["id"] in instructions
    good = {"model": "jev-1.14.0", "answers": {k: {"type": "noul", "noul": .9} for k in qs},
            "usage": {"input_tokens": 100, "output_tokens": 10}}
    assert m.validate(good, qs)["model"] == "jev-1.14.0"
    for value in [float("nan"), -1, 1.01, True, "0.9"]:
        bad = json.loads(json.dumps(good))
        bad["answers"][next(iter(qs))]["noul"] = value
        with pytest.raises(ValueError):
            m.validate(bad, qs)
    del good["answers"][next(iter(qs))]
    with pytest.raises(ValueError):
        m.validate(good, qs)


def test_transport_bounds_no_redirect_proxy_or_retry_and_budget():
    m = api()
    assert hasattr(m, "Client"), "bounded transport missing"
    import httpx
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "https://example.invalid/"})
    client = m.Client("synthetic-key", transport=httpx.MockTransport(handler))
    qs = {"q": {"type": "noul", "instructions": "test"}}
    with pytest.raises(ValueError, match="http_status"):
        client.ask({"text": "fixture"}, qs)
    assert len(seen) == 1 and str(seen[0].url) == "https://api.typesafe.ai/v1/systemone"
    assert client.requests == 1 and client.reserved > 0
    with pytest.raises(ValueError, match="question_limit"):
        client.ask({}, {str(i): qs["q"] for i in range(97)})
    with pytest.raises(ValueError, match="payload_limit"):
        client.ask({"text": "x" * 70000}, qs)
    client.requests = 30
    with pytest.raises(ValueError, match="request_budget"):
        client.ask({}, qs)
    client.requests = 0
    client.reserved = 300000
    with pytest.raises(ValueError, match="token_budget"):
        client.ask({}, qs)
    assert len(seen) == 1


def test_map_pipeline_redacts_whole_source_and_recovers_dependencies():
    m = api()
    assert hasattr(m, "map_source"), "map pipeline missing"
    text = "# A\nanswer\n# B\nlinked definition\n# C\npassword=secretfixture123\n"
    seen = []
    class Fake:
        receipts = []
        key = "secretfixture123"
        def ask(self, state, qs):
            seen.append((state, qs))
            assert "secretfixture123" not in json.dumps([state, qs])
            answers = {}
            for k in qs:
                score = 1 if k.endswith(".evidence") or k == "r0000.direct" or k == "r0001.recover" else 0
                answers[k] = {"type": "noul", "noul": score}
            return {"model": "fixture", "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 1}}
    result = m.map_source("f.md", text, "answer?", "find definition", Fake(), second_pass=True, size=100)
    assert len(seen) == 2
    assert result["retained"] == ["r0000", "r0001"]
    assert result["regions"][1]["reasons"] == ["second_pass_dependency"]
    assert result["source"] == text and result["redacted"]
    assert result["second_pass"]["status"] == "scored"
    assert "r0000" in seen[1][0]["retained"]
    assert all("f.md" in q["instructions"] and "answer?" in q["instructions"] for q in seen[1][1].values())
    # Service failure retains the full source and a visible error, never fabricates scores.
    class Broken(Fake):
        def ask(self, state, qs):
            raise ValueError("remote potentially secret body")
    failure = m.map_source("f", text, "task", "intent", Broken(), size=100)
    assert failure["packet"] == text
    assert failure["errors"] == ["service_or_validation_error"]
    assert all(r["status"] == "unavailable" for r in failure["regions"])


def test_local_artifacts_exact_recovery_and_html_inert(tmp_path):
    m = api()
    assert hasattr(m, "save_report"), "local report missing"
    text = '<script>alert(1)</script>\r\né\n'
    result = {**m.compose(text, m.segment("<img src=x onerror=alert(1)>", text), {}),
              "source": text, "task": "</pre><script>bad()</script>", "errors": ["missing input"], "redacted": False}
    target = tmp_path / "report"
    m.save_report(target, result)
    assert (target / "source.txt").read_bytes() == text.encode()
    assert (target / "packet.txt").read_bytes() == text.encode()
    data = json.loads((target / "map.json").read_text())
    assert data["source"] == text
    html = (target / "report.html").read_text()
    assert "<script>" not in html and "<img src=" not in html
    assert "&lt;script&gt;" in html and "Content-Security-Policy" in html
    assert "missing input" in html and "source.txt" in html
    with pytest.raises(FileExistsError):
        m.save_report(target, result)


def test_demo_cli_offline_and_consent_gate(tmp_path, capsys):
    m = api()
    assert hasattr(m, "main"), "CLI missing"
    target = tmp_path / "demo"
    assert m.main(["--demo", "--output", str(target)]) == 0
    data = json.loads((target / "battery.json").read_text())
    assert len(data["cases"]) >= 4
    assert data["requests"] == 0 and data["input_tokens"] == 0
    for case in data["cases"]:
        for variant in case["variants"]:
            report = json.loads((target / case["name"] / variant["name"] / "map.json").read_text())
            assert report["source"] == report["packet"]
            assert "offline_no_semantic_judgment" in report["errors"]
    with pytest.raises(SystemExit):
        m.main(["--demo", "--live", "--output", str(tmp_path / "forbidden")])
    assert not (tmp_path / "forbidden").exists()


def test_required_span_recall_checks_whole_span_not_substring_coincidence():
    m = api()
    assert hasattr(m, "span_metrics"), "reference-span metrics missing"
    text = "abcdefabcdef"
    rows = m.compose(text, m.segment("f", text, "window", 3), {})["regions"]
    for r in rows:
        r["selected"] = r["start"] >= 6
    metrics = m.span_metrics(rows, [{"name": "first", "start": 1, "end": 5}, {"name": "second", "start": 7, "end": 11}])
    assert metrics["required_span_recall"] == .5
    assert metrics["misses"] == ["first"]


def test_profile_key_resolution_restores_existing_scope(tmp_path, monkeypatch):
    m = api()
    assert hasattr(m, "profile_key"), "profile-aware secret resolver missing"
    from agent.secret_scope import set_secret_scope, reset_secret_scope, current_secret_scope
    token = set_secret_scope({"TYPESAFE_API_KEY": "fixture-key"}, profile_home=str(tmp_path))
    try:
        before = current_secret_scope()
        assert m.profile_key() == "fixture-key"
        assert current_secret_scope() is before
    finally:
        reset_secret_scope(token)


def test_one_command_launcher_runs_offline(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "context-map-demo.sh"
    assert launcher.exists(), "one-command launcher missing"
    proc = subprocess.run(["bash", str(launcher), "--python", sys.executable, "--output", str(tmp_path / "launch")],
                          capture_output=True, check=False, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads((tmp_path / "launch" / "battery.json").read_text())["requests"] == 0


def test_redaction_masks_entire_changed_line_before_boundary_splits():
    m = api()
    original = "public\napi_key=ABCDEFsharedXYZ\nother\n"
    masked, changed = m.redact_copy(original, "ABCDEFsharedXYZ")
    assert changed and len(masked) == len(original)
    assert masked.splitlines() == ["public", "█" * len("api_key=ABCDEFsharedXYZ"), "other"]


def test_live_transport_has_killable_total_deadline(monkeypatch):
    m = api()
    assert hasattr(m, "bounded_post"), "killable request deadline missing"
    import subprocess
    calls = []
    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired("safe-command", kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ValueError, match="request_deadline"):
        m.bounded_post(b'{"state":"fixture"}', "fixture-key")
    assert calls[0]["timeout"] <= 35
    assert "fixture-key" not in str(calls[0].get("args", ""))


def test_missing_input_and_invalid_coverage_are_visible_without_partial_scoring():
    m = api()
    class Invalid:
        key = ""
        receipts = []
        def ask(self, state, qs):
            return {"model": "jev-fixture", "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 1}}
    missing = m.map_source("f", "abc", "", "intent", Invalid())
    assert missing["missing_input"] == ["task"]
    assert missing["errors"] == ["missing_input_no_export"]
    invalid = m.map_source("f", "abc", "task", "intent", Invalid())
    assert invalid["packet"] == "abc" and invalid["errors"]
    assert invalid["regions"][0]["scores"] is None


def test_live_cli_reports_semantic_failure_nonzero_but_keeps_recovery(tmp_path, monkeypatch, capsys):
    m = api()
    monkeypatch.setattr(m, "profile_key", lambda: "synthetic")
    def fail(*args):
        raise ValueError("not echoed secret")
    monkeypatch.setattr(m.Client, "ask", fail)
    source = tmp_path / "f.txt"
    source.write_bytes(b"exact original\r\n")
    code = m.main(["--file", str(source), "--task", "task", "--intent", "intent", "--live", "--allow-export", "--output", str(tmp_path / "out")])
    assert code == 1
    assert (tmp_path / "out" / "source.txt").read_bytes() == source.read_bytes()
    assert "not echoed secret" not in capsys.readouterr().out


def test_first_pass_preserved_for_recovery_comparison():
    m = api()
    class Fake:
        key = ""
        receipts = []
        def ask(self, state, qs):
            return {"model": "fixture", "answers": {k: {"type": "noul", "noul": 1 if k.endswith("evidence") or k.startswith("r0000") or k.endswith("recover") else 0} for k in qs}, "usage": {"input_tokens": 1, "output_tokens": 1}}
    result = m.map_source("f", "# A\na\n# B\nb\n# C\nc\n", "task", "intent", Fake(), second_pass=True)
    assert result["first_pass"]["retained"] == ["r0000", "r0001"]
    assert result["retained"] == ["r0000", "r0001", "r0002"]


def test_response_size_and_invalid_usage_rejected():
    m = api()
    import httpx
    client = m.Client("fixture", transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 131073)))
    with pytest.raises(ValueError, match="response_limit"):
        client.ask({}, {"q": {"type": "noul", "instructions": "fixture"}})
    for usage in [{}, {"input_tokens": True, "output_tokens": 0}, {"input_tokens": -1, "output_tokens": 0}]:
        with pytest.raises(ValueError, match="invalid_usage"):
            m.validate({"model": "fixture", "answers": {}, "usage": usage}, {})


def test_fresh_profile_env_key_loaded_without_home_writes(tmp_path, monkeypatch):
    from agent.secret_scope import reset_secret_scope, set_secret_scope, current_secret_scope
    home = tmp_path / "profile"
    home.mkdir()
    (home / ".env").write_text("TYPESAFE_API_KEY=synthetic-profile-fixture\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    token = set_secret_scope(None)
    try:
        assert api().profile_key() == "synthetic-profile-fixture"
        assert current_secret_scope() is None
        assert sorted(p.name for p in home.iterdir()) == [".env"]
    finally:
        reset_secret_scope(token)
