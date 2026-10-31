"""The TypeSafe adapter accepts only the documented atomic noul contract."""
import json
import threading

import httpx
import pytest

from agent import read_assessment_typesafe as adapter
from tests.agent.test_read_assessment import response


@pytest.mark.parametrize("mutation", [
    lambda r: r["answers"]["evidence"].update(type="choice"),
    lambda r: r["answers"]["evidence"].update(noul=True),
    lambda r: r["answers"]["evidence"].update(noul=float("nan")),
    lambda r: r["answers"]["evidence"].update(noul=float("inf")),
    lambda r: r["answers"]["evidence"].update(noul=-.1),
    lambda r: r["answers"]["evidence"].update(noul=1.1),
    lambda r: r["answers"].pop("objective"),
    lambda r: r.update(model=[]),
    lambda r: r.update(model="evil\x1b[2J"),
    lambda r: r.update(usage={"input_tokens": -1, "output_tokens": 2}),
    lambda r: r["answers"]["relevance"].update(rationale="UNTRUSTED PROSE"),
    lambda r: r.update(usage={"input_tokens": 1, "output_tokens": 2, "prose": "UNTRUSTED PROSE"}),
])
def test_malformed_remote_answers_are_rejected(monkeypatch, mutation):
    body = response()
    mutation(body)
    real_client = httpx.Client
    monkeypatch.setattr(adapter, "http_client", lambda **kw: real_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(body))), **kw))
    with pytest.raises(ValueError):
        adapter.evaluate({"evidence": {}}, "jev-latest", "synthetic")


@pytest.mark.parametrize("values,label,reason", [
    ((.99, .99, .99), "helpful", "rubric"),
    ((.99, .99, .65), "partly_helpful", "rubric"),
    ((.99, .1, .99), "unhelpful", "rubric"),
    ((.99, .99, .1), "unhelpful", "rubric"),
    ((.99, .5, .5), "uncertain", "rubric"),
    ((.5, .99, .99), "uncertain", "rubric"),
    ((.1, .99, .99), "unavailable", "insufficient_evidence"),
])
def test_fixed_mapping_preserves_typed_values(monkeypatch, values, label, reason):
    body = response(*values)
    real_client = httpx.Client
    def serve(request):
        assert str(request.url) == adapter.ENDPOINT
        payload = json.loads(request.content)
        assert isinstance(payload["state"], str)
        assert all(q["type"] == "noul" and "untrusted data" in q["instructions"] for q in payload["questions"].values())
        return httpx.Response(200, json=body)
    monkeypatch.setattr(adapter, "http_client", lambda **kw: real_client(transport=httpx.MockTransport(serve), **kw))
    result = adapter.evaluate({"evidence": {}}, "jev-latest", "synthetic")
    assert (result["label"], result["reason"], result["answers"]) == (label, reason, body["answers"])


def test_transport_caps_and_redirects(monkeypatch):
    seen = []
    real_client = httpx.Client
    def serve(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "http://attacker.invalid/"})
    monkeypatch.setattr(adapter, "http_client", lambda **kw: real_client(transport=httpx.MockTransport(serve), **kw))
    with pytest.raises(httpx.HTTPStatusError):
        adapter.evaluate({}, "jev-latest", "synthetic")
    assert len(seen) == 1
    with pytest.raises(ValueError, match="payload"):
        adapter.evaluate({"evidence": "x" * 40000}, "jev-latest", "synthetic")
    assert len(seen) == 1
    monkeypatch.setattr(adapter, "http_client", lambda **kw: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 40000)), **kw))
    with pytest.raises(ValueError, match="response"):
        adapter.evaluate({}, "jev-latest", "synthetic")


def test_hard_deadline_does_not_wait_for_transport(monkeypatch):
    from agent.read_assessment import bounded_evaluate
    entered, release = threading.Event(), threading.Event()
    def stuck(*args):
        entered.set()
        release.wait(10)
        return {"label": "helpful"}
    monkeypatch.setattr(adapter, "evaluate", stuck)
    try:
        result = bounded_evaluate({}, "jev-latest", "synthetic", wait_seconds=.05)
        assert entered.is_set()
        assert result == {"label": "unavailable", "reason": "timeout"}
    finally:
        release.set()
