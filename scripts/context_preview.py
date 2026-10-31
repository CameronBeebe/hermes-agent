"""Offline report refresh and loopback preview. Provider imports are live-only."""
import json
import os
from pathlib import Path

from scripts.context_preview_index import render_index
from scripts.context_preview_render import render_report, render_source, validate_correspondence


def private_write(path, content):
    """Replace the directory entry, never truncate a possibly hardlinked inode."""
    import tempfile
    path = Path(path)
    if path.is_symlink():
        raise OSError('report_symlink')
    fd, temporary = tempfile.mkstemp(prefix='.preview-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def saved_entries(root):
    entries = []
    for path in sorted(root.rglob('map.json')):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('report_symlink')
        result = json.loads(path.read_text(encoding='utf-8-sig'))
        validate_correspondence(result)
        for name, key in (('source.txt', 'source'), ('packet.txt', 'packet')):
            companion = path.parent / name
            if companion.is_symlink() or not companion.resolve().is_relative_to(root):
                raise ValueError('report_symlink')
            if companion.read_bytes() != result[key].encode('utf-8'):
                raise ValueError('companion_correspondence')
        relative = path.parent.relative_to(root)
        oracle = path.parent.parent / 'oracle.json'
        # Corpus labels come from recorded provenance, never model guesses.
        if oracle.is_file() and oracle.resolve().is_relative_to(root):
            metadata = json.loads(oracle.read_text(encoding='utf-8-sig'))
            result['corpus'] = 'public' if metadata.get('source_url') else 'synthetic' if 'synthetic' in metadata.get('source', '').lower() else 'unknown'
        elif (root / 'battery.json').is_file():
            result['corpus'] = 'synthetic'
        entries.append({'result': result, 'relative': relative.as_posix(),
                        'case': relative.parts[0] if len(relative.parts) > 1 else 'Provided file',
                        'variant': relative.name if relative.parts else 'heading-direct'})
    if not entries:
        raise ValueError('no_saved_maps')
    return entries


def refresh(directory):
    """Re-render only from saved JSON. Original maps and receipts stay byte-identical."""
    root = Path(directory).resolve(strict=True)
    entries = saved_entries(root)
    for entry in entries:
        target = root / entry['relative']
        result = entry['result']
        private_write(target / 'report.html', render_report(result))
        private_write(target / 'source.html', render_source(result))
        # No provider module import is needed for historical offline browsing.
        parts = []
        for row in result['regions']:
            if row['selected']:
                parts.append(f"[SOURCE {row['path']} {row['id']} L{row['line_start']}:{row['column_start']}–L{row['line_end']}:{row['column_end']} chars [{row['start']},{row['end']})]\n{row['text']}\n[END SOURCE]\n")
            else:
                parts.append(f"[OMITTED {row['path']} chars [{row['start']},{row['end']})]\n")
        private_write(target / 'packet-labeled.txt', ''.join(parts) or '[EMPTY SOURCE]\n')
    aggregate_path = root / 'aggregate.json'
    aggregate = json.loads(aggregate_path.read_text(encoding='utf-8-sig')) if aggregate_path.is_file() and not aggregate_path.is_symlink() else None
    landing = render_report(entries[0]['result']) if len(entries) == 1 and entries[0]['relative'] == '.' else render_index(entries, aggregate)
    private_write(root / 'index.html', landing)
    return len(entries)


def make_server(directory, port=0):
    """Serve a fixed snapshot of report artifacts only, never a filesystem handler."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import unquote, urlsplit
    from scripts.context_preview_render import CSP
    root = Path(directory).resolve(strict=True)
    entries = saved_entries(root)
    names = {'report.html', 'source.html', 'source.txt', 'packet.txt', 'packet-labeled.txt', 'map.json'}
    paths = [root / entry['relative'] / name for entry in entries for name in names]
    paths.append(root / 'index.html')
    snapshot = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            continue
        snapshot['/' + path.relative_to(root).as_posix()] = path.read_bytes()
    # Use the verified map copy, not a second mutable read of companions.
    for entry in entries:
        for name, key in (('source.txt', 'source'), ('packet.txt', 'packet')):
            path = root / entry['relative'] / name
            snapshot['/' + path.relative_to(root).as_posix()] = entry['result'][key].encode('utf-8')
    landing = '/index.html' if '/index.html' in snapshot else '/report.html'
    if landing not in snapshot:
        raise ValueError('missing_report_index')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # No user-controlled paths or source fragments in terminal logs.
            return

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_GET(self, head=False):
            allowed_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in allowed_hosts:
                self.send_error(403)
                return
            path = unquote(urlsplit(self.path).path)
            if any(part in {'.', '..'} for part in path.split('/')) or '\\' in path:
                self.send_error(403)
                return
            if path == '/':
                path = landing
            if path not in snapshot:
                self.send_error(404)
                return
            body = snapshot[path]
            content_type = 'text/html; charset=utf-8' if path.endswith('.html') else 'application/json; charset=utf-8' if path.endswith('.json') else 'text/plain; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Content-Security-Policy', CSP + "; frame-ancestors 'none'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if not head:
                self.wfile.write(body)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def create_file_report(args):
    """Keep mapping/export separate from the stdlib-only offline viewer."""
    from scripts import context_map as m
    argv = ['--file', str(args.file), '--task', args.task, '--intent', args.intent,
            '--output', str(args.output), '--mode', args.mode, '--arm', args.arm, '--top-k', str(args.top_k)]
    if not args.enriched:
        argv.append('--direct-only')
    if args.live:
        argv.extend(['--live', '--allow-export'])
    if args.second_pass:
        argv.append('--second-pass')
    return m.main(argv)


def main(argv=None):
    import argparse
    import webbrowser
    parser = argparse.ArgumentParser(description='Opt-in context preview. Saved browsing is offline; live mapping exports masked evidence only with explicit consent.')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--report', type=Path, help='Browse a chosen saved report directory; never exports')
    source.add_argument('--file', type=Path, help='One UTF-8 source file to map')
    parser.add_argument('--output', type=Path, help='New private report directory for --file')
    parser.add_argument('--task', default='')
    parser.add_argument('--intent', default='')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--allow-export', action='store_true')
    parser.add_argument('--mode', choices=['heading', 'window'], default='heading')
    parser.add_argument('--arm', choices=['independent-noul', 'choice-exists'], default='independent-noul')
    parser.add_argument('--top-k', type=int, choices=range(1, 97), default=3)
    parser.add_argument('--enriched', action='store_true', help='Experimental additional signals; not recommended by default')
    parser.add_argument('--second-pass', action='store_true')
    parser.add_argument('--port', type=int, default=0, help='0 selects an available loopback port')
    parser.add_argument('--no-open', action='store_true', help='Print URL without opening browser')
    parser.add_argument('--render-only', action='store_true', help='Refresh static HTML and exit without a server')
    args = parser.parse_args(argv)
    if args.file and (not args.output or not args.task.strip() or not args.intent.strip()):
        parser.error('--file requires --output, --task and --intent')
    if args.live and (not args.file or not args.allow_export):
        parser.error('live mapping requires --file and explicit --allow-export')
    if args.report and (args.allow_export or args.output):
        parser.error('saved report browsing does not accept export/output options')
    if not 0 <= args.port <= 65535:
        parser.error('port must be 0..65535')
    if args.arm == 'choice-exists' and (args.enriched or args.second_pass or args.mode != 'heading'):
        parser.error('choice-exists requires heading without enriched/recovery')
    if args.second_pass and not args.enriched:
        parser.error('--second-pass requires --enriched')
    try:
        status = create_file_report(args) if args.file else 0
        directory = args.output if args.file else args.report
        if not directory.is_dir():
            return 1
        count = refresh(directory)
        if args.render_only:
            print(f'Refreshed {count} saved map(s); no provider calls during rendering.')
            return status
        with make_server(directory, args.port) as server:
            url = f'http://127.0.0.1:{server.server_port}/'
            print(url, flush=True)
            print('Saved preview only. Ctrl-C stops the loopback server. Local originals may contain secrets.', flush=True)
            if not args.no_open:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return status
    except (OSError, ValueError, KeyError, TypeError):
        print('Preview failed: invalid/missing saved evidence, unsafe path, unavailable port, or unreadable input. Try --port 0 for an available port.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
