"""Contracts for inspectable packets and predeclared context-map experiments."""
import json

import httpx
import pytest

from scripts import context_map as m

def test_session_ledger_accounts_across_clients_without_resetting_safe_run_caps(tmp_path):
    from scripts import context_map_experiments as e
    ledger = tmp_path / "ledger.json"
    qs = {"q": {"type": "noul", "instructions": "test"}}
    def handler(request):
        return httpx.Response(200, json={"model": "fixture", "answers": {"q": {"type": "noul", "noul": 1}},
                                        "usage": {"input_tokens": 17, "output_tokens": 2}})
    first = e.SessionClient("fake", ledger, transport=httpx.MockTransport(handler))
    first.ask({}, qs)
    second = e.SessionClient("fake", ledger, transport=httpx.MockTransport(handler))
    second.ask({}, qs)
    data = json.loads(ledger.read_text())
    assert len(data) == 2
    assert sum(r["usage"]["input_tokens"] for r in data) == 34
    assert "fake" not in ledger.read_text()
    second.reserved = 300000
    with pytest.raises(ValueError, match="token_budget"):
        second.ask({}, qs)
    ledger.write_text(json.dumps([data[0]] * 35))
    with pytest.raises(ValueError, match="session_request_budget"):
        e.SessionClient("fake", ledger, transport=httpx.MockTransport(handler)).ask({}, qs)
    ledger.write_text(json.dumps([{"status": "pending", "reserved_tokens": 499999}]))
    with pytest.raises(ValueError, match="session_token_budget"):
        e.SessionClient("fake", ledger, transport=httpx.MockTransport(handler)).ask({}, qs)

@pytest.mark.platforms("posix")
@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_session_ledger_ignores_preexisting_pending_links(tmp_path, link_kind):
    from scripts import context_map_experiments as e

    tmp_path = tmp_path / "ledger-dir"
    tmp_path.mkdir()
    ledger = tmp_path / "ledger.json"
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_bytes(b"do not overwrite")
    sentinel.chmod(0o640)
    pending = ledger.with_suffix(".pending")
    if link_kind == "symlink":
        pending.symlink_to(sentinel)
    else:
        pending.hardlink_to(sentinel)

    def handler(request):
        reservation = json.loads(ledger.read_text())
        assert reservation[0]["status"] == "pending"
        assert ledger.stat().st_mode & 0o777 == 0o600
        return httpx.Response(200, json={"model": "fixture", "answers": {"q": {"type": "noul", "noul": 1}},
                                        "usage": {"input_tokens": 17, "output_tokens": 2}})

    client = e.SessionClient("fake", ledger, transport=httpx.MockTransport(handler))
    client.ask({}, {"q": {"type": "noul", "instructions": "test"}})
    assert sentinel.read_bytes() == b"do not overwrite"
    assert sentinel.stat().st_mode & 0o777 == 0o640
    assert pending.samefile(sentinel)
    assert json.loads(ledger.read_text())[0]["usage"]["input_tokens"] == 17
    assert ledger.stat().st_mode & 0o777 == 0o600
    assert set(tmp_path.iterdir()) == {ledger, sentinel, pending}


def test_labeled_cli_option_preserves_exact_raw_packet(tmp_path):
    source = tmp_path / "f.md"
    source.write_text("hello\n")
    assert m.main(["--file", str(source), "--task", "task", "--intent", "intent", "--labeled-packet", "--output", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out/packet.txt").read_text() == "hello\n"
    assert '[SOURCE' in (tmp_path / "out/packet-labeled.txt").read_text()


def test_labeled_packet_preserves_raw_and_marks_leading_internal_trailing_gaps(tmp_path):
    text = "zero\none\ntwo\nthree\nfour\n"
    rows = m.compose(text, m.segment("guide.md", text, size=5, mode="window"), {})["regions"]
    for row in rows:
        row["selected"] = row["id"] in {"r0001", "r0003"}
    result = {**m.finalize(rows), "source": text}
    m.save_report(tmp_path / "out", result, labeled=True)
    assert (tmp_path / "out/packet.txt").read_text() == "".join(r["text"] for r in rows if r["selected"])
    labeled = (tmp_path / "out/packet-labeled.txt").read_text()
    assert '[OMITTED guide.md chars [0,5)]' in labeled
    assert '[OMITTED guide.md chars [10,15)]' in labeled
    assert '[OMITTED guide.md chars [20,24)]' in labeled
    assert '[SOURCE guide.md r0001 L2:1–L3:2 chars [5,10)]' in labeled
    assert "packet-labeled.txt" in (tmp_path / "out/report.html").read_text()
    assert m.labeled_packet([]) == "[EMPTY SOURCE]\n"


def test_experiment_metrics_separate_missing_uncertain_and_irrelevant():
    from scripts import context_map_experiments as e
    rows = m.compose("abcdefghij", m.segment("f", "abcdefghij", mode="window", size=2), {})["regions"]
    rows[0].update(status="scored", reasons=["direct"])
    rows[1].update(status="ambiguous", reasons=["ambiguous"])
    rows[3].update(selected=False, status="scored", reasons=[])
    metrics = e.metrics(rows, [{"name": "needed", "start": 0, "end": 3}], [{"start": 4, "end": 10}])
    assert metrics["required_span_recall"] == 1
    assert metrics["required_chars_retained"] == 3
    assert metrics["irrelevant_retained_chars"] == 4
    assert metrics["nonrequired_retained_chars"] == 5
    assert metrics["unavailable_retained_chars"] == 4
    assert metrics["uncertain_retained_chars"] == 2
    assert metrics["positive_retained_chars"] == 2
    assert metrics["miss_details"] == []
    rows[1]["reasons"].append("neighbor_of:r0000")
    assert e.metrics(rows, [], [])["uncertain_retained_chars"] == 2
    rows[1]["selected"] = False
    assert e.metrics(rows, [{"name": "needed", "start": 0, "end": 3}], [])["miss_details"] == [{"name": "needed", "missing_ranges": [[2, 3]]}]


def test_pairwise_neighbor_verification_drops_irrelevant_neighbor_not_continuation():
    from scripts import context_map_experiments as e
    text = "# Action\nRun now\n# Continuation\nOnly if empty\n# Office\nBuy mugs\n"
    regions = m.segment("f", text)
    scores = {r["id"]: dict.fromkeys(m.SIGNALS, 0.0) for r in regions}
    for value in scores.values():
        value["evidence"] = 1
    scores["r0001"].update(direct=1, neighbor=1)
    result = {**m.compose(text, regions, scores), "source": text, "task": "run", "declared_intent": "conditions", "path": "f"}
    class Client:
        key = ""
        def ask(self, state, qs):
            assert set(qs) == {"r0001.r0000", "r0001.r0002"}
            assert state["regions"][0]["text"] == "# Action\nRun now\n"
            assert state["regions"][2]["text"] == "# Office\nBuy mugs\n"
            assert all('Candidate' in q['instructions'] and 'Anchor' in q['instructions'] for q in qs.values())
            return {"model": "fixture", "answers": {k: {"type": "noul", "noul": 1 if k.endswith("r0000") else 0} for k in qs}, "usage": {"input_tokens": 1, "output_tokens": 1}}
    e.verify_neighbors(result, Client())
    assert result["retained"] == ["r0000", "r0001"]
    assert result["regions"][0]["reasons"] == ["verified_neighbor:r0001"]
    assert result["regions"][2]["selected"] is False


def test_pair_failure_preserves_existing_recovery_and_redacts():
    from scripts import context_map_experiments as e
    text = "# A\npassword=secretvalue123\n# B\npublic\n"
    rows = m.segment("f", text)
    scores = {r["id"]: dict.fromkeys(m.SIGNALS, 0.0) for r in rows}
    scores["r0000"].update(evidence=1, direct=1, neighbor=1)
    result = {**m.compose(text, rows, scores), "source": text, "task": "task", "declared_intent": "intent", "path": "f"}
    before = result["packet"]
    class Broken:
        key = "secretvalue123"
        def ask(self, state, qs):
            assert "secretvalue123" not in json.dumps([state, qs])
            raise ValueError("failure")
    e.verify_neighbors(result, Broken())
    assert result["packet"] == before
    assert result["neighbor_verification"]["status"] == "unavailable"


def test_small_batches_keep_long_path_within_payload_bounds(tmp_path):
    text = "".join(f"# Section {i}\n" + "a" * 500 + "\n" for i in range(13))
    seen = []
    class Client:
        key = ""
        receipts = []
        def ask(self, state, qs):
            seen.append(qs)
            assert len(qs) <= 36
            return {"model": "fixture", "answers": {k: {"type": "noul", "noul": 1} for k in qs}, "usage": {"input_tokens": 1, "output_tokens": 1}}
    result = m.map_source("long/" * 20, text, "task", "intent", Client(), batch_regions=6)
    assert not result["errors"] and len(seen) == 3
    assert result["packet"] == text


def test_experiment_cli_offline_and_export_gate(tmp_path):
    from scripts import context_map_experiments as e
    case = {"name": "sample", "path": "f", "text": "abc", "task": "a", "intent": "b",
            "required_spans": [], "irrelevant_spans": []}
    source = tmp_path / "case.json"
    source.write_text(json.dumps(case))
    assert e.main(["--case", str(source), "--output", str(tmp_path / "out")]) == 0
    assert json.loads((tmp_path / "out/results.json").read_text())["variants"]["heading-direct"]["metrics"]["unavailable_retained_chars"] == 3
    with pytest.raises(SystemExit):
        e.main(["--case", str(source), "--output", str(tmp_path / "bad"), "--live"])


def test_factorial_runner_saves_predeclared_oracle_and_all_four_arms(tmp_path):
    from scripts import context_map_experiments as e
    case = {"name": "sample", "path": "f.md", "text": "# A\nneeded\n# B\ndecoy\n", "task": "find needed",
            "intent": "retain evidence", "required_spans": [{"name": "rule", "start": 4, "end": 10}],
            "irrelevant_spans": [{"start": 11, "end": 21}]}
    class Client:
        key = ""
        receipts = []
        def ask(self, state, qs):
            assert json.loads((tmp_path / "out/oracle.json").read_text()) == case
            return {"model": "fixture", "answers": {k: {"type": "noul", "noul": int(k.endswith("evidence") or k.startswith("r0000"))} for k in qs},
                    "usage": {"input_tokens": 1, "output_tokens": 1}}
    record = e.run_case(case, tmp_path / "out", Client(), size=16)
    assert set(record["variants"]) == {"heading-direct", "heading-enriched", "window-direct", "window-enriched"}
    for name, result in record["variants"].items():
        assert "first_metrics" in result and "metrics" in result
        assert (tmp_path / "out" / name / "packet-labeled.txt").exists()
    aggregate = e.aggregate([record])
    assert aggregate["heading-direct"]["required_spans"] == 1
    assert aggregate["heading-direct"]["covered_spans"] == 1


@pytest.mark.parametrize("text,error", [("", "missing_input_no_export"), ("x" * 17000, "input_bound_exceeded_no_export")])
def test_empty_and_long_source_never_export_and_keep_exact_recovery(text, error):
    class NoExport:
        key = ""
        receipts = []
        def ask(self, *args):
            raise AssertionError("must not export")
    result = m.map_source("f", text, "task", "intent", NoExport())
    assert result["errors"] == [error]
    assert result["packet"] == text
    assert "".join(r["text"] for r in result["regions"]) == text
