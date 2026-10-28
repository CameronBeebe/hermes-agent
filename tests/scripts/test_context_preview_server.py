"""Real loopback HTTP and one-command CLI contracts; no remote requests."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from scripts import context_map as m
from scripts import context_preview as p


def test_server_confines_requests_and_symlinks_to_chosen_report(tmp_path):
    assert hasattr(p, 'make_server'), 'confined preview server missing'
    root = tmp_path / 'report'
    m.save_report(root, {**m.compose('hello', m.segment('f', 'hello'), {}), 'source': 'hello'})
    (tmp_path / 'secret.txt').write_text('outside')
    (root / 'leak.txt').symlink_to(tmp_path / 'secret.txt')
    server = p.make_server(root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
    try:
        assert server.server_address[0] == '127.0.0.1'
        conn.request('GET', '/report.html')
        response = conn.getresponse()
        assert response.status == 200 and b'Context preview' in response.read()
        assert response.getheader('Content-Security-Policy')
        for path in ['/../secret.txt', '/%2e%2e/secret.txt', '/%2e%2e%2fsecret.txt', '/leak.txt', '/.env', '/unknown/', '//evil.example/report.html']:
            conn.request('GET', path)
            response = conn.getresponse()
            assert response.status in {400, 403, 404}, path
            assert b'outside' not in response.read()
        conn.request('GET', '/', headers={'Host': 'evil.example'})
        response = conn.getresponse()
        assert response.status == 403
        response.read()
        conn.request('GET', '/source.txt')
        response = conn.getresponse()
        assert response.getheader('Content-Type').startswith('text/plain')
        assert response.read() == b'hello'
        with pytest.raises(OSError):
            p.make_server(root, server.server_address[1])
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_launcher_serves_saved_report_offline_and_prints_dynamic_url(tmp_path):
    launcher = Path(__file__).resolve().parents[2] / 'scripts/context-preview.sh'
    assert launcher.is_file(), 'one-command browser launcher missing'
    root = tmp_path / 'report'
    m.save_report(root, {**m.compose('hello', m.segment('f', 'hello'), {}), 'source': 'hello'})
    proc = subprocess.Popen(['bash', str(launcher), '--python', sys.executable, '--report', str(root), '--no-open'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # The CLI flushes its URL before entering the server loop.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor() as pool:
            line = pool.submit(proc.stdout.readline).result(timeout=15)
        assert line.startswith('http://127.0.0.1:'), line
        from urllib.request import urlopen
        with urlopen(line.strip(), timeout=5) as response:
            assert b'Context preview' in response.read()
    finally:
        proc.terminate()
        proc.communicate(timeout=5)


def test_file_cli_defaults_heading_direct_and_requires_export_consent(tmp_path):
    assert hasattr(p, 'main'), 'preview CLI missing'
    source = tmp_path / 'a.md'
    source.write_bytes('# One\r\névidence\n'.encode())
    output = tmp_path / 'out'
    assert p.main(['--file', str(source), '--task', 'Find rule', '--intent', 'Check exceptions', '--output', str(output), '--render-only']) == 0
    saved = json.loads((output / 'map.json').read_text())
    assert saved['mode'] == 'heading' and saved['enriched'] is False
    assert saved['path'] == 'a.md'
    assert saved['packet'] == saved['source']
    assert saved['receipts'] == []
    assert 'offline_no_semantic_judgment' in saved['errors']
    with pytest.raises(SystemExit):
        p.main(['--file', str(source), '--task', 't', '--intent', 'i', '--output', str(tmp_path / 'bad'), '--live', '--render-only'])
    assert not (tmp_path / 'bad').exists()


def test_existing_output_is_refused_without_refresh(tmp_path):
    source = tmp_path / 'a.txt'
    source.write_text('hello')
    output = tmp_path / 'out'
    m.save_report(output, {**m.compose('old', m.segment('f', 'old'), {}), 'source': 'old'})
    before = (output / 'report.html').read_bytes()
    with pytest.raises(SystemExit):
        p.main(['--file', str(source), '--task', 't', '--intent', 'i', '--output', str(output), '--render-only'])
    assert (output / 'report.html').read_bytes() == before


@pytest.mark.parametrize('name', ['source.txt', 'packet.txt'])
@pytest.mark.parametrize('operation', [p.refresh, p.make_server])
def test_companion_mismatch_is_refused_without_changing_evidence(tmp_path, name, operation):
    root = tmp_path / 'report'
    text = 'évidence\r\n'
    m.save_report(root, {**m.compose(text, m.segment('f', text), {}), 'source': text})
    (root / name).write_bytes(b'tampered')
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    with pytest.raises(ValueError, match='companion_correspondence'):
        operation(root)
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


def test_refresh_replaces_hardlinked_artifact_without_writing_outside(tmp_path):
    root = tmp_path / 'report'
    m.save_report(root, {**m.compose('hello', m.segment('f', 'hello'), {}), 'source': 'hello'})
    outside = tmp_path / 'outside'
    outside.write_text('unchanged')
    artifact = root / 'report.html'
    artifact.unlink()
    artifact.hardlink_to(outside)
    p.refresh(root)
    assert outside.read_text() == 'unchanged'
    assert 'Context preview' in artifact.read_text()
    assert artifact.stat().st_ino != outside.stat().st_ino
    assert artifact.stat().st_mode & 0o777 == 0o600


def test_refresh_refuses_external_symlink_without_writing_outside(tmp_path):
    root = tmp_path / 'report'
    m.save_report(root, {**m.compose('hello', m.segment('f', 'hello'), {}), 'source': 'hello'})
    outside = tmp_path / 'outside'
    outside.write_text('unchanged')
    (root / 'report.html').unlink()
    (root / 'report.html').symlink_to(outside)
    with pytest.raises(OSError):
        p.refresh(root)
    assert outside.read_text() == 'unchanged'
