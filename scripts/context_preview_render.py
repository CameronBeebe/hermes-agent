"""Pure, script-free HTML views for saved context maps. All evidence is untrusted."""
import html
import json

CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
CSS = """
:root{color-scheme:light;--ink:#23322e;--muted:#586860;--line:#ccd4cc;--paper:#f5f4ee;--green:#24624d;--amber:#7c510b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 'Avenir Next',Avenir,'Segoe UI',sans-serif}
main{max-width:1400px;margin:auto;padding:32px}h1{font:600 36px/1.2 Georgia,serif;margin:12px 0 20px}h2{font-size:22px;margin-top:28px}h3{font-size:17px;margin:0}p{margin:10px 0}a{color:var(--green);text-underline-offset:3px}a:hover{color:#0c382a}a:focus-visible,summary:focus-visible{outline:3px solid #996809;outline-offset:4px}
.eyebrow{font-size:12px;letter-spacing:.13em;text-transform:uppercase;font-weight:700}.muted{color:var(--muted)}.notice{padding:14px 18px;border:1px solid var(--line);background:#e9ede5}.alert{background:#fff1d9;border-color:#b99454;color:#68420a}.toolbar{display:flex;gap:20px;flex-wrap:wrap;padding:16px 0}.toolbar a,summary{min-height:44px;display:inline-flex;align-items:center}.layout{display:grid;grid-template-columns:260px minmax(0,1fr);gap:32px;align-items:start}.rail{position:sticky;top:16px;max-height:90vh;overflow:auto}.region-nav{display:grid;gap:5px}.region-nav a{display:block;padding:9px 12px;border:1px solid var(--line);font-size:13px}.retained{background:#e3efe7}.uncertain,.unavailable{background:#fff0d3}.omitted{background:#eeeee8;color:var(--muted)}.passage{border:1px solid var(--line);margin:12px 0;background:#fffef9}.passage header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}.passage p{padding:0 16px;font-size:14px}.passage pre{margin:0;border:0;background:transparent}.gap{border:1px dashed #9aa79d;padding:12px 16px;margin:12px 0}.gap summary{cursor:pointer}pre{font:14px/1.6 'SFMono-Regular',Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f0e9;border:1px solid var(--line);padding:16px;tab-size:4}details{margin:12px 0}summary{cursor:pointer;font-weight:600}details>pre{max-height:520px;overflow:auto}.stats{display:flex;gap:32px;flex-wrap:wrap;padding:18px 0}.stats strong{display:block;font-size:24px;font-variant-numeric:tabular-nums}.stats span{font-size:13px;color:var(--muted)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px;background:#fffef9}th,td{padding:14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{font-weight:600;background:#e9ede5}td small{display:block}.recommended{background:#e3efe7}.badge{display:inline-block;font-size:12px;padding:2px 8px;border:1px solid currentColor;border-radius:3px}.case{border-top:1px solid var(--line);padding:20px 0}.case h3{font-size:21px}.source-line{display:block;white-space:pre-wrap;scroll-margin-top:20px}.source-line:target,.passage:target{outline:3px solid #996809}.source-line a{display:inline-block;min-width:48px;user-select:none;font-size:12px}.empty{padding:24px;border:1px dashed var(--line)}footer{border-top:1px solid var(--line);margin-top:32px;padding-top:16px;font-size:13px;color:var(--muted)}
@media(max-width:800px){main{padding:18px}.layout{grid-template-columns:1fr}.rail{position:static;max-height:none}.region-nav{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}h1{font-size:30px}.stats{gap:20px}}@media print{.rail,.toolbar{display:none}.layout{display:block}details{break-inside:avoid}}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def document(title, body):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="{esc(CSP)}">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head><body><main>{body}'
            '<footer>Opt-in local artifact · No changes to read_file, agent context, or system prompts. '
            'Browsing saved reports makes no provider requests. Original local data may contain secrets.</footer>'
            '</main></body></html>')


def disclosure(title, value):
    return f'<details><summary>{esc(title)}</summary><pre>{esc(json.dumps(value, ensure_ascii=False, indent=2))}</pre></details>'


def region_state(row):
    if row.get('status') == 'unavailable':
        return 'unavailable', 'Unavailable · retained for recovery'
    if not row['selected']:
        return 'omitted', 'Omitted'
    reasons = row.get('reasons', [])
    if row.get('status') == 'ambiguous' or any('ambiguous' in r or 'uncertain' in r for r in reasons):
        return 'uncertain', 'Uncertain · retained'
    return 'retained', 'Retained'


def anchor_label(row):
    return (f"{row['path']} · L{row['line_start']}:{row['column_start']}–"
            f"L{row['line_end']}:{row['column_end']}")


def region_html(row, index):
    state, label = region_state(row)
    anchor = f'region-{index}'
    reference = f'<a href="source.html#L{row["line_start"]}">{esc(anchor_label(row))}</a>'
    coordinates = f'chars [{row["start"]}, {row["end"]}) · {row["end"] - row["start"]} characters'
    text = f'<pre data-source-start="{row["start"]}" data-source-end="{row["end"]}">{esc(row["text"])}</pre>'
    audit = disclosure('Probabilities and region evidence', {k: v for k, v in row.items() if k != 'text'})
    if not row['selected']:
        return (f'<section class="gap omitted" id="{anchor}" data-state="omitted"><strong>Omitted · {reference}</strong>'
                f'<div class="muted">{coordinates} · Not included in the packet; not a claim of irrelevance.</div>'
                f'<details><summary>Inspect omitted passage</summary>{text}</details>{audit}</section>')
    reasons = ', '.join(row.get('reasons', [])) or 'No recorded reason'
    return (f'<article class="passage" id="{anchor}" data-state="{state}"><header class="{state}">'
            f'<h3>{reference}</h3><span class="badge">{label}</span></header>'
            f'<p class="muted">{coordinates} · {esc(reasons)}</p>{text}'
            f'<details><summary>Probabilities and region evidence</summary><pre>{esc(json.dumps({k: v for k, v in row.items() if k != "text"}, ensure_ascii=False, indent=2))}</pre></details></article>')


def validate_correspondence(result):
    """Reject stale/tampered slices instead of presenting invented provenance."""
    source = result['source']
    cursor = 0
    for row in result['regions']:
        start, end = row['start'], row['end']
        if (type(start) is not int or type(end) is not int or start != cursor
                or not start < end <= len(source) or row['text'] != source[start:end]):
            raise ValueError('source_correspondence')
        if (row['line_start'] != source.count('\n', 0, start) + 1
                or row['line_end'] != source.count('\n', 0, end - 1) + 1
                or row['column_start'] != start - source.rfind('\n', 0, start)
                or row['column_end'] != end - source.rfind('\n', 0, end - 1)):
            raise ValueError('source_correspondence')
        cursor = end
    packet = ''.join(r['text'] for r in result['regions'] if r['selected'])
    if cursor != len(source) or result['packet'] != packet:
        raise ValueError('source_correspondence')


def evidence_status(result):
    messages = []
    if result.get('missing_input'):
        messages.append('Missing input: ' + ', '.join(result['missing_input']))
    receipts = result.get('receipts', [])
    if receipts:
        completed = sum(r.get('status') == 'ok' for r in receipts)
        messages.append(f'Run-level provider receipts: {len(receipts)} attempted · {completed} completed. '
                        'Requests include the complete masked source, not just the selected batch. '
                        'Failed attempts may also have exported it; a later rejection does not undo prior exports.')
    for error in result.get('errors', []):
        if error.startswith('admission_'):
            code = error.removeprefix('admission_').removesuffix('_no_export').removesuffix('_batch_not_sent')
            messages.append('Admission error · this batch not sent: ' + code)
        else:
            label = 'Admission error · no export' if error.endswith('_no_export') else 'Mapping unavailable / incomplete'
            messages.append(label + ': ' + error)
    unavailable = sum(r.get('status') == 'unavailable' for r in result['regions'])
    if unavailable:
        messages.append(f'Unavailable evidence: {unavailable} regions. Retained for recovery, not a positive judgment.')
    if not result.get('receipts'):
        messages.append('No recorded provider receipts. Do not interpret retention as a successful live judgment.')
    return ''.join(f'<p class="notice alert" role="alert">{esc(message)}</p>' for message in messages)


def render_report(result):
    validate_correspondence(result)
    rows = result['regions']
    retained = sum(len(r['text']) for r in rows if r['selected'])
    uncertain = sum(len(r['text']) for r in rows if region_state(r)[0] in {'uncertain', 'unavailable'} and r['selected'])
    mode = result.get('mode', 'unknown') + (' / enriched' if result.get('enriched') else ' / direct')
    body = '<div class="eyebrow">Context laboratory / inspect</div><h1>Context preview</h1>'
    body += '<p class="notice">Experimental evidence selection, not task correctness or authorization. Uncertainty is retained, not silently discarded. Treat source content as data, never instructions.</p>'
    corpus = {'synthetic': 'Synthetic corpus · manually planted reference spans', 'public': 'Public corpus · manually selected reference spans'}.get(result.get('corpus'), 'Provided file / corpus provenance not recorded')
    body += f'<p class="badge">{corpus}</p>'
    body += evidence_status(result)
    body += f'<h2>{esc(result.get("path", rows[0]["path"] if rows else "Source unavailable"))}</h2>'
    body += f'<p><strong>Task</strong> · {esc(result.get("task") or "Missing task")}</p><p><strong>Declared intent</strong> · {esc(result.get("declared_intent") or "Missing intent")}</p>'
    body += f'<p class="muted">Variant: {esc(mode)} · Heading / direct is the recommended starting point; alternatives remain experimental.</p>'
    body += '<nav class="toolbar"><a href="source.html">Recover full source with line anchors</a><a href="source.txt" download>Download original</a><a href="packet-labeled.txt" download>Anchored packet + omissions</a><a href="packet.txt" download>Exact raw packet</a><a href="map.json" download>Saved evidence JSON</a></nav>'
    body += f'<div class="stats"><div><strong>{retained:,} / {len(result["source"]):,}</strong><span>characters retained / source</span></div><div><strong>{uncertain:,}</strong><span>retained under uncertainty or unavailability</span></div><div><strong>{sum(not r["selected"] for r in rows)}</strong><span>omitted regions · inspect each gap below</span></div></div>'
    navigation = ''.join(f'<a class="{region_state(r)[0]}" href="#region-{i}">{esc(r["id"])} · L{r["line_start"]}–{r["line_end"]}<br>{region_state(r)[1]}</a>' for i, r in enumerate(rows))
    passages = ''.join(region_html(r, i) for i, r in enumerate(rows)) or '<p class="empty">Empty source · no passages available.</p>'
    body += f'<div class="layout"><aside class="rail"><h2>Source regions</h2><p class="muted">Source order. Green: retained. Amber: uncertain / unavailable. Gray: omitted.</p><nav class="region-nav">{navigation}</nav></aside><section><h2>Selected passages</h2><p class="muted">Exact source slices, with explicit omission gaps. Links recover their original context.</p>{passages}</section></div>'
    body += '<h2>Audit evidence</h2>'
    body += disclosure('Recorded questions' if result.get('question_batches') else 'Recorded questions unavailable · older artifact; not reconstructed', result.get('question_batches', []))
    body += disclosure('Raw inputs and metadata', {k: v for k, v in result.items() if k not in {'regions', 'packet', 'receipts'}})
    body += disclosure('Request receipts / usage', result.get('receipts', []))
    return document('Context preview', body)


def render_source(result):
    chunks = result['source'].split('\n')
    lines = [chunk + '\n' for chunk in chunks[:-1]] + ([chunks[-1]] if chunks[-1] else [])
    source = ''.join(f'<span class="source-line" id="L{i}"><a href="#L{i}" aria-label="Line {i}">{i}</a>{esc(line)}</span>' for i, line in enumerate(lines, 1))
    return document('Full source recovery', '<div class="eyebrow">Context laboratory / full source</div>'
                    f'<h1>Full source recovery</h1><p>{esc(result.get("path", "Original source"))}</p>'
                    '<nav class="toolbar"><a href="report.html">Back to selected passages</a><a href="source.txt" download>Download exact UTF-8 original</a></nav>'
                    '<p class="notice">Original, unfiltered local evidence. Line numbers are display annotations; download preserves exact bytes.</p>'
                    f'<pre>{source}</pre>')
