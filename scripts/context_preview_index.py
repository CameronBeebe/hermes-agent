"""Comparison view built from saved evidence, never simulated judgments."""
from collections import defaultdict
from urllib.parse import quote

from scripts.context_preview_render import disclosure, document, esc

VARIANTS = ('heading-direct', 'heading-enriched', 'window-direct', 'window-enriched')
DEFINITIONS = '''<details><summary>Metric definitions and rubric</summary><dl>
<dt>Manually planted coverage</dt><dd>Whole manually designated required spans retained / required spans. This is not task correctness. Retain-all trivially achieves full coverage.</dd>
<dt>Selected characters</dt><dd>Unicode characters retained, not tokens. Compared with complete original source length; no invented bridging text.</dd>
<dt>Irrelevant retained</dt><dd>Overlap with explicitly annotated irrelevant spans. Nonrequired prose is not automatically irrelevant.</dd>
<dt>Uncertainty-only</dt><dd>Characters retained for ambiguity without a positive rubric reason. Unavailable is a separate recovery category, not positive evidence.</dd>
<dt>Direct / enriched</dt><dd>Direct asks readability and direct task relevance. Enriched also asks prerequisite, exception, instruction and neighbor signals. Evidence below .8 or active scores strictly between .2 and .8 retain conservatively; active scores at least .8 retain positively.</dd>
<dt>Heading / window</dt><dd>Heading boundaries plus a size ceiling versus equal-character windows. Inspect each map for its configured ceiling.</dd>
<dt>Missing evidence</dt><dd>An absent result, receipt, metric or failed admission cannot establish success. Zero is shown only when recorded.</dd>
</dl></details>'''


def metric_cells(metrics, source_chars):
    count = metrics.get('required_spans')
    coverage = 'Not annotated' if not count else f"{count - len(metrics.get('misses', []))} / {count}"
    selected = metrics.get('selected_chars', 'Unavailable')
    values = [coverage, f'{selected} / {source_chars}', metrics.get('irrelevant_retained_chars', 'Not annotated'),
              metrics.get('uncertain_retained_chars', 'Not recorded'), metrics.get('unavailable_retained_chars', 'Not recorded')]
    return ''.join(f'<td>{esc(value)}</td>' for value in values)


def comparison(entries, stage):
    totals = {}
    counts = defaultdict(int)
    measured = defaultdict(int)
    for entry in entries:
        name = entry['variant']
        if name not in VARIANTS:
            continue
        counts[name] += 1
        result = entry['result']
        metrics = result.get(stage)
        if metrics is None:
            continue
        measured[name] += 1
        total = totals.setdefault(name, {'required_spans': 0, 'misses': [], 'source_chars': 0})
        total['source_chars'] += len(result['source'])
        total['required_spans'] += metrics.get('required_spans', 0)
        total['misses'].extend(metrics.get('misses', []))
        for key in ('selected_chars', 'irrelevant_retained_chars', 'uncertain_retained_chars', 'unavailable_retained_chars'):
            if key in metrics:
                total[key] = total.get(key, 0) + metrics[key]
    rows = []
    for name in VARIANTS:
        values = totals.get(name)
        cells = metric_cells(values, values['source_chars']) if values else '<td colspan="5">Missing evidence · no recorded metrics for this arm</td>'
        if 0 < measured[name] < counts[name]:
            cells = f'<td colspan="5">Incomplete evidence · {measured[name]} / {counts[name]} cases have metrics</td>'
        label = '<small>Recommended starting point</small>' if name == 'heading-direct' else ''
        rows.append(f'<tr class="{"recommended" if name == "heading-direct" else ""}"><th scope="row">{name}{label}</th>{cells}</tr>')
    return ('<div class="table-wrap"><table><thead><tr><th>Variant</th><th>Manually planted coverage</th>'
            '<th>Selected / source chars</th><th>Irrelevant retained</th><th>Uncertainty-only chars</th><th>Unavailable chars</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')


def case_html(name, entries, index):
    first = entries[0]['result']
    corpus = first.get('corpus', 'unknown')
    label = {'synthetic': 'Synthetic corpus', 'public': 'Public corpus · manually selected reference spans'}.get(corpus, 'Corpus provenance not recorded')
    body = f'<section class="case" id="case-{index}"><span class="badge">{label}</span><h3>{esc(name)}</h3>'
    body += f'<p><strong>Task</strong> · {esc(first.get("task", "Missing task"))}</p><p class="muted"><strong>Intent</strong> · {esc(first.get("declared_intent", "Missing intent"))}</p>'
    body += '<div class="table-wrap"><table><thead><tr><th>Inspect saved variant</th><th>State</th><th>Coverage</th><th>Selected / source chars</th><th>Irrelevant</th><th>Uncertain</th><th>Unavailable</th></tr></thead><tbody>'
    for entry in sorted(entries, key=lambda e: (e['variant'] != 'heading-direct', e['variant'])):
        result = entry['result']
        errors = result.get('errors', [])
        status = '; '.join(errors) if errors else 'Recorded' if result.get('receipts') else 'Missing evidence · no receipts'
        if any(r.get('status') == 'unavailable' for r in result['regions']):
            status += ' · unavailable regions retained'
        href = quote(entry['relative'] + '/report.html', safe='/')
        body += f'<tr><th><a href="{href}">{esc(entry["variant"])}</a></th><td>{esc(status)}</td>{metric_cells(result.get("metrics", {}), len(result["source"]))}</tr>'
    return body + '</tbody></table></div></section>'


def followup_html(aggregate):
    body = '<h2>Completed-arm follow-up</h2><p class="muted">Saved aggregate uses the disclosed smaller-batch public replacement. Original-arm admission failure is preserved in the tables above.</p>'
    body += '<div class="table-wrap"><table><thead><tr><th>Variant</th><th>Coverage</th><th>Selected / source chars</th><th>Irrelevant</th><th>Uncertainty-only</th><th>Unavailable</th></tr></thead><tbody>'
    for name, values in aggregate.get('first_pass', {}).items():
        body += f'<tr><th>{esc(name)}</th>{metric_cells(values, values.get("source_chars", "Unknown"))}</tr>'
    body += '</tbody></table></div><h2>Recovery and neighbor checks</h2>'
    recovery = [row for row in aggregate.get('recovery', []) if row.get('status') == 'scored']
    if recovery:
        added = sum(row['added_chars'] for row in recovery)
        body += f'<p>{len(recovery)} scored dependency recovery passes · {added} characters added. Additional calls do not by themselves establish useful recovery.</p>'
    body += f'<p>{esc(aggregate.get("pair_initial_negative", "Initial pair-check outcome not recorded."))}</p>'
    for name, values in aggregate.get('pair_comparison', {}).items():
        if isinstance(values, dict):
            body += f'<p><strong>{esc(name)}</strong> · {esc(values.get("selected_chars", "Unknown"))} selected characters; {esc(values.get("irrelevant_retained_chars", "Unknown"))} explicitly irrelevant characters retained. Synthetic subset only; compare against heading/direct, not just broad-neighbor expansion.</p>'
    body += '<p class="notice">No downstream task-quality evaluation. Single exploratory runs; correlated planted examples; no significance or calibration claim. Public-corpus uncertainty remains unresolved.</p>'
    return body


def render_index(entries, aggregate=None):
    aggregate = aggregate or {}
    body = '<div class="eyebrow">Context laboratory / compare</div><h1>Context preview laboratory</h1>'
    body += '<p class="notice">Opt-in, inspectable selections from saved evidence. Manually planted coverage is <strong>not task correctness</strong>. No automatic context filtering. Saved browsing is offline and free of provider calls.</p>'
    body += '<h2>Start with heading / direct</h2><p>Recommended starting point for inspection, not a universal winner. Richer signals can retain irrelevant neighbors; uncertainty can dominate the public corpus. Inspect alternatives and omissions before trusting a packet.</p>'
    body += DEFINITIONS
    body += '<h2>First pass · four-way comparison</h2><p class="muted">Only the four original arm directories are aggregated below; failed admissions remain unavailable. Follow-up variants are listed separately, never silently substituted.</p>'
    body += comparison(entries, 'first_metrics')
    body += '<h2>After recovery</h2>' + comparison(entries, 'metrics')
    if aggregate:
        body += '<p class="notice alert">Historical follow-up: the public heading/enriched admission failure was rerun with smaller batches. The original failure remains above; the replacement and directed-pair negative results remain clickable below. This intervention is not an unchanged replicate.</p>'
        body += followup_html(aggregate)
        body += disclosure('Saved aggregate including explicitly replaced public arm / negative pair results / receipts', aggregate)
    groups = defaultdict(list)
    for entry in entries:
        groups[entry['case']].append(entry)
    body += '<h2>Inspect a case</h2><nav class="toolbar">' + ''.join(f'<a href="#case-{i}">{esc(name)}</a>' for i, name in enumerate(sorted(groups))) + '</nav>'
    body += ''.join(case_html(name, groups[name], i) for i, name in enumerate(sorted(groups)))
    return document('Context preview laboratory', body)
