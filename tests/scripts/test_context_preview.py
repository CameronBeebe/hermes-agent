"""Behavior contracts for the opt-in static context preview."""
from html.parser import HTMLParser
import json

from scripts import context_map as m


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def sample():
    text = '# Omit\nnoise\n# Keep\névidence\r\n# Unknown\nmaybe\n# Tail\nnoise\n'
    regions = m.segment('guide.md', text)
    scores = {r['id']: {'evidence': 1, 'direct': 0} for r in regions}
    scores['r0001']['direct'] = .95
    scores['r0002']['direct'] = .5
    return {**m.compose(text, regions, scores, enriched=False), 'source': text,
            'path': 'guide.md', 'task': 'Find evidence', 'declared_intent': 'Check exceptions',
            'mode': 'heading', 'enriched': False, 'errors': [], 'receipts': []}


def test_preview_defaults_to_exact_passages_with_gaps_and_resolving_anchors(tmp_path):
    result = sample()
    m.save_report(tmp_path / 'out', result)
    page = (tmp_path / 'out/report.html').read_text()
    doc = Document(page)
    assert '<h1>Context preview</h1>' in page
    assert 'Find evidence' in page and 'Check exceptions' in page
    assert 'Selected passages' in page and 'Omitted ·' in page
    assert 'Uncertain · retained' in page
    assert 'guide.md · L3:1' in page
    ids = {a['id'] for _, a in doc.tags if 'id' in a}
    for _, attrs in doc.tags:
        href = attrs.get('href', '')
        if href.startswith('#'):
            assert href[1:] in ids
    assert {a.get('data-state') for _, a in doc.tags} >= {'retained', 'omitted', 'uncertain'}
    assert not any(tag == 'script' for tag, _ in doc.tags)
    assert not any('open' in a for tag, a in doc.tags if tag == 'details')
    assert (tmp_path / 'out/packet.txt').read_bytes() == result['packet'].encode()
    assert (tmp_path / 'out/source.txt').read_bytes() == result['source'].encode()
    assert (tmp_path / 'out/packet-labeled.txt').exists()


def test_untrusted_evidence_is_inert_and_failures_are_not_hidden(tmp_path):
    result = sample()
    attack = '\"><script>alert(1)</script><img src=x onerror=alert(1)>'
    result.update(task=attack, declared_intent='', errors=['input_bound_exceeded_no_export'],
                  missing_input=['intent'], path='javascript:alert(1)')
    result['regions'][0]['path'] = attack
    result['regions'][2].update(status='unavailable', scores=None, reasons=['unavailable'])
    m.save_report(tmp_path / 'out', result)
    page = (tmp_path / 'out/report.html').read_text()
    doc = Document(page)
    assert not any(tag in {'script', 'img', 'iframe'} for tag, _ in doc.tags)
    assert not any(k.startswith('on') for _, a in doc.tags for k in a)
    assert all(not a.get('href', '').startswith(('javascript:', 'file:', '/')) for _, a in doc.tags)
    assert 'Admission error' in page and 'Missing input: intent' in page
    assert 'Unavailable evidence' in page
    assert any(a.get('role') == 'alert' for _, a in doc.tags)
    assert '&lt;script&gt;' in page
    assert 'Recorded questions unavailable' in page
    result['corpus'] = 'public'
    from scripts.context_preview_render import render_report
    assert 'Public corpus · manually selected reference spans' in render_report(result)


def test_corrupt_source_correspondence_is_rejected_before_creating_report(tmp_path):
    import pytest
    result = sample()
    result['regions'][1]['text'] = 'not the source'
    with pytest.raises(ValueError, match='source_correspondence'):
        m.save_report(tmp_path / 'bad', result)
    assert not (tmp_path / 'bad').exists()


def test_source_line_links_resolve_for_crlf_unicode_and_empty_source(tmp_path):
    result = sample()
    m.save_report(tmp_path / 'out', result)
    source = Document((tmp_path / 'out/source.html').read_text())
    ids = {a['id'] for _, a in source.tags if 'id' in a}
    for _, attrs in Document((tmp_path / 'out/report.html').read_text()).tags:
        href = attrs.get('href', '')
        if href.startswith('source.html#'):
            assert href.split('#')[1] in ids
    empty = {**m.compose('', [], {}), 'source': '', 'errors': ['missing_input_no_export']}
    m.save_report(tmp_path / 'empty', empty)
    assert 'Empty source' in (tmp_path / 'empty/report.html').read_text()


def test_saved_report_refresh_builds_comparison_without_provider_calls(tmp_path):
    import importlib.util
    assert importlib.util.find_spec('scripts.context_preview') is not None, 'offline refresh/launcher missing'
    from scripts.context_preview import refresh
    variants = ['heading-direct', 'heading-enriched', 'window-direct', 'window-enriched']
    for name in variants:
        result = sample()
        result['metrics'] = {'required_spans': 1, 'misses': [], 'selected_chars': len(result['packet']),
                             'irrelevant_retained_chars': 0, 'uncertain_retained_chars': 16}
        result['first_metrics'] = result['metrics']
        result['mode'] = name.split('-')[0]
        result['enriched'] = name.endswith('enriched')
        result['corpus'] = 'synthetic'
        m.save_report(tmp_path / 'case' / name, result)
    before = (tmp_path / 'case/heading-direct/map.json').read_bytes()
    assert refresh(tmp_path) == 4
    page = (tmp_path / 'index.html').read_text()
    assert all(name in page for name in variants)
    assert 'Recommended starting point' in page
    assert 'Manually planted coverage' in page and 'not task correctness' in page
    assert 'Synthetic' in page and 'First pass' in page and 'After recovery' in page
    assert 'Missing evidence' in page
    for _, attrs in Document(page).tags:
        href = attrs.get('href', '')
        if href and not href.startswith('#'):
            from urllib.parse import unquote
            assert (tmp_path / unquote(href)).is_file(), href
    assert (tmp_path / 'case/heading-direct/map.json').read_bytes() == before


def test_bom_saved_json_and_single_report_landing(tmp_path):
    from scripts.context_preview import refresh
    m.save_report(tmp_path / 'out', sample())
    path = tmp_path / 'out/map.json'
    path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
    assert refresh(tmp_path / 'out') == 1
    assert '<h1>Context preview</h1>' in (tmp_path / 'out/index.html').read_text()


def test_comparison_shows_replacement_and_negative_results_without_raw_json():
    from scripts.context_preview_index import render_index
    aggregate = {'public_replacement': 'smaller batches', 'first_pass': {
        'heading-direct': {'covered_spans': 2, 'required_spans': 2, 'selected_chars': 10, 'source_chars': 30,
                           'irrelevant_retained_chars': 3, 'uncertain_retained_chars': 4, 'unavailable_retained_chars': 0}},
        'recovery': [{'regions_added': 0}], 'pair_comparison': {'note': 'negative'}}
    page = render_index([], aggregate)
    assert 'Completed-arm follow-up' in page
    assert '10 / 30' in page
    assert 'Recovery and neighbor checks' in page
    assert 'No downstream task-quality evaluation' in page


def test_partial_variant_metrics_are_unavailable_not_summed_as_success():
    from scripts.context_preview_index import comparison
    first = sample()
    first['first_metrics'] = {'required_spans': 1, 'misses': [], 'selected_chars': 3}
    second = sample()
    entries = [{'variant': 'heading-direct', 'result': r} for r in [first, second]]
    page = comparison(entries, 'first_metrics')
    assert 'Incomplete evidence · 1 / 2 cases have metrics' in page


def test_source_anchors_follow_newline_offsets_not_unicode_separators(tmp_path):
    text = '# A\nleft\u2028right\n# B\nnext\n'
    result = {**m.compose(text, m.segment('f.md', text), {}), 'source': text}
    m.save_report(tmp_path / 'out', result)
    page = (tmp_path / 'out/source.html').read_text()
    assert 'id="L3"' in page
    assert 'aria-label="Line 3">3</a># B\n' in page
    omitted = sample()
    m.save_report(tmp_path / 'omitted', omitted)
    # Both omitted and selected regions expose their actual probabilities.
    assert (tmp_path / 'omitted/report.html').read_text().count('Probabilities and region evidence') == len(omitted['regions'])


def test_hostile_case_names_are_encoded_as_local_links(tmp_path):
    from scripts.context_preview import refresh
    from urllib.parse import unquote, urlsplit
    folder = 'case # &"<tag>'
    m.save_report(tmp_path / folder / 'heading-direct', sample())
    refresh(tmp_path)
    page = (tmp_path / 'index.html').read_text()
    doc = Document(page)
    links = [a['href'] for _, a in doc.tags if 'href' in a and not a['href'].startswith('#')]
    assert links
    for href in links:
        assert not urlsplit(href).scheme and not urlsplit(href).fragment
        assert (tmp_path / unquote(href)).is_file()
    assert not any(tag == 'tag' for tag, _ in doc.tags)


def test_new_mapping_records_masked_questions_and_distinguishes_admission_failure():
    class Recording:
        key = 'secret-fixture'
        receipts = []
        def ask(self, state, qs):
            assert 'secret-fixture' not in json.dumps([state, qs])
            return {'model': 'test-only', 'answers': {k: {'type': 'noul', 'noul': 1.0} for k in qs},
                    'usage': {'input_tokens': 1, 'output_tokens': 1}}
    result = m.map_source('guide.md', 'password=secret-fixture\npublic', 'Find rule', 'Inspect', Recording(), enriched=False)
    assert result.get('question_batches'), 'actual questions must be recorded for new maps'
    assert result['exported_state']['regions'][0]['text'] != result['source']
    assert 'secret-fixture' not in json.dumps(result['question_batches'])
    class Admission(Recording):
        def ask(self, state, qs):
            raise ValueError('payload_limit')
    failure = m.map_source('guide.md', 'abc', 't', 'i', Admission(), enriched=False)
    assert failure['errors'] == ['admission_payload_limit_no_export']
    assert failure['packet'] == 'abc'
