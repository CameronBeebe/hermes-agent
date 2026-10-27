"""Replay resolves profile credentials without publishing them to the process environment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("source", ["dotenv", "environment", "both"])
def test_rescore_module_resolves_credentials_in_fresh_process(tmp_path, source):
    home = tmp_path / "home"
    profile = home / "profile"
    profile.mkdir(parents=True)
    key = "synthetic-review-only"
    if source in {"dotenv", "both"}:
        (profile / ".env").write_text(f'TYPESAFE_API_KEY="{key}" # synthetic fixture\n')
    record = {"rubric_version": "read-v1", "provider": "typesafe",
              "requested_model": "jev-latest", "state": {"evidence": {}}}
    path = tmp_path / "saved.json"
    path.write_text(json.dumps(record))
    env = {name: value for name, value in os.environ.items()
           if name in {"PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP"}}
    env.update(HOME=str(home), USERPROFILE=str(home), HERMES_HOME=str(profile),
               HERMES_MANAGED_DIR=str(home / "no-managed-scope"))
    if source in {"environment", "both"}:
        env["TYPESAFE_API_KEY"] = key if source == "environment" else "synthetic-ambient-other"
    # Exercise the actual module entry point and threaded HTTP adapter, not a secret mock.
    code = textwrap.dedent('''
        import json, os, runpy, sys
        import httpx
        from agent import read_assessment_typesafe as adapter
        from agent.secret_scope import current_secret_scope, get_secret
        before = dict(os.environ)
        sent = []
        def deny_network(event, args):
            if event in {"socket.connect", "socket.getaddrinfo"}:
                raise AssertionError("real network forbidden")
        sys.addaudithook(deny_network)
        def serve(request):
            assert request.headers["authorization"] == "Bearer synthetic-review-only"
            assert get_secret("TYPESAFE_API_KEY") == "synthetic-review-only"
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={
                "model": "jev-test", "usage": {"input_tokens": 1, "output_tokens": 3},
                "answers": {k: {"type": "noul", "noul": .99}
                            for k in ("evidence", "relevance", "objective")}})
        real_client = httpx.Client
        adapter.http_client = lambda **kw: real_client(transport=httpx.MockTransport(serve), **kw)
        sys.argv = ["scripts.read_assessment", sys.argv[1], "--rescore", "--allow-export"]
        try:
            runpy.run_module("scripts.read_assessment", run_name="__main__")
        except SystemExit as exc:
            assert exc.code == 0
        assert len(sent) == 1, "rescore did not reach the mock transport"
        assert os.environ == before, "profile credentials polluted the environment"
        assert current_secret_scope() is None, "replay leaked its secret scope"
    ''')
    proc = subprocess.run([sys.executable, "-c", code, str(path)],
                          cwd=Path(__file__).resolve().parents[2], env=env,
                          capture_output=True, text=True, timeout=30, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["label"] == "helpful"
    assert key not in proc.stdout + proc.stderr
    assert json.loads(path.read_text()) == record


@pytest.mark.parametrize("key_present", [True, False])
@pytest.mark.parametrize("bound_scope", [True, False])
def test_rescore_isolates_routed_profiles(tmp_path, monkeypatch, capsys, key_present, bound_scope):
    import httpx
    from agent import read_assessment_typesafe as adapter
    from agent.secret_scope import current_secret_scope, reset_secret_scope, set_secret_scope
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    from scripts.read_assessment import main
    from tests.agent.test_read_assessment import response

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    launch = tmp_path / "launch"
    routed = tmp_path / "routed"
    launch.mkdir()
    routed.mkdir()
    (launch / ".env").write_text("TYPESAFE_API_KEY=synthetic-launch-only\n")
    (routed / ".env").write_text("TYPESAFE_API_KEY=synthetic-routed-only\n" if key_present or bound_scope else "")
    monkeypatch.setenv("HERMES_HOME", str(launch))
    monkeypatch.setenv("TYPESAFE_API_KEY", "synthetic-ambient-only")
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(tmp_path / "absent-managed"))
    path = tmp_path / "saved.json"
    path.write_text(json.dumps({"rubric_version": "read-v1", "provider": "typesafe",
                               "requested_model": "jev-latest", "state": {"evidence": {}}}))
    original_env = dict(os.environ)
    requests = []
    real_client = httpx.Client
    monkeypatch.setattr(adapter, "http_client", lambda **kw: real_client(transport=httpx.MockTransport(
        lambda req: requests.append(req.headers["authorization"]) or httpx.Response(200, json=response())), **kw))
    # An existing scope (even empty) remains authoritative over on-disk credentials.
    mapping = {"TYPESAFE_API_KEY": "synthetic-bound-only"} if key_present else {}
    token = set_secret_scope(mapping if bound_scope else None, profile_home=str(routed))
    home_token = set_hermes_home_override(routed)
    try:
        assert main([str(path), "--rescore", "--allow-export"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert current_secret_scope() is (mapping if bound_scope else None)
        if key_present:
            assert result["label"] == "helpful"
            assert requests == ["Bearer synthetic-bound-only" if bound_scope else "Bearer synthetic-routed-only"]
        else:
            assert result["reason"] == "missing_key"
            assert requests == []
        assert os.environ == original_env
    finally:
        reset_hermes_home_override(home_token)
        reset_secret_scope(token)


def test_rescore_restores_scope_after_transport_error(tmp_path, monkeypatch, capsys):
    import httpx
    from agent import read_assessment_typesafe as adapter
    from agent.secret_scope import current_secret_scope
    from hermes_constants import get_hermes_home
    from scripts.read_assessment import main

    (get_hermes_home() / ".env").write_text("TYPESAFE_API_KEY=synthetic-error-key\n")
    path = tmp_path / "saved.json"
    path.write_text(json.dumps({"rubric_version": "read-v1", "provider": "typesafe",
                               "requested_model": "jev-latest", "state": {"evidence": {}}}))
    original_scope = current_secret_scope()
    original_env = dict(os.environ)
    def fail(**kwargs):
        raise httpx.ConnectError("synthetic-error-key")
    monkeypatch.setattr(adapter, "http_client", fail)
    assert main([str(path), "--rescore", "--allow-export"]) == 1
    assert json.loads(capsys.readouterr().out) == {"label": "unavailable", "reason": "replay_error"}
    assert current_secret_scope() is original_scope
    assert os.environ == original_env
