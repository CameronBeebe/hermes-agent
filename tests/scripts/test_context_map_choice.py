"""Choice ranking is relative, never independent relevance or completeness."""
import copy
import json

import httpx
import pytest

from scripts import context_map as m


TEXT = '# Rule\nDelete after 21 days.\n# Exception\nNever delete on HOLD.\n'


def client_for(exists=.95, mutate=None):
    def handler(request):
        payload = json.loads(request.content)
        state = json.loads(payload['state'])
        assert ''.join(r['text'] for r in state['regions']) == TEXT
        assert set(payload['questions']) == {'where', 'exists'}
        assert payload['questions']['where']['criteria'] == {'r0000': None, 'r0001': None}
        for q in payload['questions'].values():
            assert 'delete' in q['instructions'] and 'HOLD' in q['instructions']
        data = response(exists)
        if mutate:
            mutate(data)
        return httpx.Response(200, json=data)
    return m.Client('', transport=httpx.MockTransport(handler))


def mapped(exists=.95, top_k=1, mutate=None):
    return m.map_source('f.md', TEXT, 'When delete?', 'Check HOLD', client_for(exists, mutate),
                        arm='choice-exists', top_k=top_k, enriched=False)


def test_choice_top_k_can_miss_required_exception_without_claiming_irrelevance():
    result = mapped()
    assert result['retained'] == ['r0000']
    assert result['existence'] == {'probability': .95, 'outcome': 'present'}
    assert result['regions'][1]['choice_probability'] == .01
    assert result['regions'][1]['scores'] is None
    assert 'exception' in result['warning'].lower()
    assert 'not independent relevance' in result['warning']
    assert result['source'] == TEXT
    assert len(result['receipts']) == 1
    start = TEXT.index('Never')
    assert m.span_metrics(result['regions'], [{'name': 'exception', 'start': start, 'end': len(TEXT)}])['misses'] == ['exception']
    assert mapped(top_k=2)['packet'] == TEXT


@pytest.mark.parametrize('p,outcome', [(0, 'absent'), (.2, 'absent'), (.5, 'uncertain'), (.8, 'present')])
def test_existence_outcomes_do_not_conflate_uncertainty_with_partial_coverage(p, outcome):
    result = mapped(p)
    assert result['existence']['outcome'] == outcome
    assert result['packet'] == ('' if outcome == 'absent' else TEXT if outcome == 'uncertain' else TEXT[:TEXT.index('# Exception')])
    assert result['choice_answer']['probabilities']['r0000'] == .99


def test_missing_exists_keeps_full_recovery_not_peaked_winner():
    result = mapped(mutate=lambda d: d['answers'].pop('exists'))
    assert result['errors'] == ['service_or_validation_error']
    assert result['existence']['outcome'] == 'unavailable'
    assert result['packet'] == TEXT
    assert all(r['status'] == 'unavailable' for r in result['regions'])


def test_choice_report_labels_relative_mass_and_existence_outside_raw_audit():
    from scripts.context_preview_render import render_report
    from scripts.context_preview_index import render_index
    result = mapped()
    page = render_report(result)
    visible = page.split('<h2>Audit evidence</h2>')[0]
    assert 'Choice ranking + answer existence' in visible
    assert 'Answer existence: present' in visible
    assert 'Top-K: 1' in visible and 'not independent relevance' in visible
    assert 'Relative Choice mass' in visible and '0.9900' in visible
    assert 'exceptions' in visible and 'source.html' in visible
    result['metrics'] = {'required_spans': 2, 'misses': ['HOLD exception']}
    assert 'Known oracle misses: HOLD exception' in render_report(result).split('<h2>Audit evidence</h2>')[0]
    index = render_index([{'variant': 'heading-choice-exists-k1', 'case': 'followup',
                           'relative': 'followup/heading-choice-exists-k1', 'result': result}])
    assert 'Choice-ranking follow-up' in index
    assert 'Answer existence: present' in index
    assert 'Recommended starting point' in index


@pytest.mark.parametrize('region_index', [0, 1])
def test_saved_choice_rank_cannot_inject_links(region_index):
    from scripts.context_preview_render import render_report
    result = mapped()
    malicious = '<a href="https://attacker.invalid/">Forged recovery</a>'
    result['regions'][region_index]['choice_rank'] = malicious
    page = render_report(result)
    assert malicious not in page
    assert '&lt;a href=' in page


def test_preview_cli_selects_choice_and_preserves_direct_default(tmp_path):
    from scripts import context_preview as p
    source = tmp_path / 'f.md'
    source.write_text(TEXT)
    base = ['--file', str(source), '--task', 'When delete?', '--intent', 'Check HOLD', '--render-only']
    assert p.main(base + ['--output', str(tmp_path / 'default')]) == 0
    old = json.loads((tmp_path / 'default/map.json').read_text())
    assert old['enriched'] is False and old['mode'] == 'heading'
    assert 'choice_answer' not in old
    assert p.main(base + ['--arm', 'choice-exists', '--top-k', '2', '--output', str(tmp_path / 'choice')]) == 0
    new = json.loads((tmp_path / 'choice/map.json').read_text())
    assert new['arm'] == 'choice-exists' and new['top_k'] == 2
    assert new['existence']['outcome'] == 'unavailable'
    assert new['source'] == new['packet'] == TEXT
    with pytest.raises(SystemExit):
        p.main(base + ['--arm', 'choice-exists', '--enriched', '--output', str(tmp_path / 'bad')])
    with pytest.raises(SystemExit):
        p.main(base + ['--arm', 'choice-exists', '--live', '--output', str(tmp_path / 'nogate')])


@pytest.mark.parametrize('kwargs', [{'top_k': 0}, {'top_k': True}, {'top_k': 97},
                                   {'enriched': True}, {'second_pass': True}, {'mode': 'window'}])
def test_invalid_choice_options_refused_before_export(kwargs):
    options = dict(arm='choice-exists', enriched=False)
    options.update(kwargs)
    with pytest.raises(ValueError):
        m.map_source('f', TEXT, 't', 'i', m.OfflineClient(''), **options)


def test_choice_limits_and_redaction_preserve_recovery():
    long = m.map_source('f', 'x' * 17000, 't', 'i', m.OfflineClient(''), arm='choice-exists', enriched=False)
    assert long['errors'] == ['input_bound_exceeded_no_export']
    assert long['packet'] == long['source']
    class Redacted(m.OfflineClient):
        def ask(self, state, qs):
            assert 'secret-fixture' not in json.dumps([state, qs])
            raise ValueError('offline')
    result = m.map_source('secret-fixture', TEXT + 'password=secret-fixture', 't', 'i', Redacted('secret-fixture'),
                          arm='choice-exists', enriched=False)
    assert result['redacted'] and result['source'] == result['packet']


def test_choice_experiment_runs_only_comparable_heading_arms_with_frozen_oracle(tmp_path):
    from scripts import context_map_experiments as e
    case = {'name': 'sample', 'path': 'f', 'text': TEXT, 'task': 'When delete?', 'intent': 'Check HOLD',
            'source': 'synthetic', 'required_spans': [], 'irrelevant_spans': []}
    path = tmp_path / 'case.json'
    path.write_text(json.dumps(case))
    out = tmp_path / 'out'
    assert e.main(['--case', str(path), '--output', str(out), '--comparison', 'choice-exists', '--top-k', '1']) == 0
    saved = json.loads((out / 'results.json').read_text())
    assert set(saved['variants']) == {'heading-direct-followup', 'heading-choice-exists-k1'}
    assert json.loads((out / 'oracle.json').read_text()) == case
    assert (out / 'heading-choice-exists-k1/report.html').is_file()


def test_choice_ranking_is_a_separate_metric_category():
    from scripts.context_map_experiments import metrics
    values = metrics(mapped()['regions'], [], [])
    assert values['ranking_retained_chars'] == len(mapped()['packet'])
    assert values['uncertain_retained_chars'] == values['positive_retained_chars'] == 0


def test_stricter_followup_session_budget_persists_across_clients(tmp_path):
    from scripts.context_map_experiments import SessionClient
    ledger = tmp_path / 'ledger.json'
    ledger.write_text(json.dumps([{'status': 'failed', 'reserved_tokens': 100}] * 12))
    with pytest.raises(ValueError, match='session_request_budget'):
        SessionClient('', ledger, max_requests=12, max_input_tokens=100000).ask({}, questions())
    ledger.write_text(json.dumps([{'status': 'pending', 'reserved_tokens': 99999}]))
    with pytest.raises(ValueError, match='session_token_budget'):
        SessionClient('', ledger, max_requests=12, max_input_tokens=100000).ask({}, questions())


def questions():
    return {'where': {'type': 'choice', 'criteria': {'r0000': None, 'r0001': None}},
            'exists': {'type': 'noul'}}


def response(exists=.95):
    return {'model': 'test-only', 'answers': {
        'where': {'type': 'choice', 'choice': 'r0000', 'confidence': .9,
                  'probabilities': {'r0000': .99, 'r0001': .01}},
        'exists': {'type': 'noul', 'noul': exists}},
        'usage': {'input_tokens': 10, 'output_tokens': 5}}


def test_mixed_choice_noul_validates_without_rewriting_distribution():
    data = response()
    original = copy.deepcopy(data)
    assert m.validate(data, questions()) == original


@pytest.mark.parametrize('mutation', [
    lambda d: d['answers'].pop('exists'),
    lambda d: d['answers'].update(unknown={'type': 'noul', 'noul': .5}),
    lambda d: d['answers']['where']['probabilities'].pop('r0001'),
    lambda d: d['answers']['where']['probabilities'].update(unknown=0),
    lambda d: d['answers']['where']['probabilities'].update(r0001=.5),
    lambda d: d['answers']['where']['probabilities'].update(r0000=float('nan')),
    lambda d: d['answers']['where']['probabilities'].update(r0000=True),
    lambda d: d['answers']['where']['probabilities'].update(r0001=-.01),
    lambda d: d['answers']['where'].update(choice='unknown'),
    lambda d: d['answers']['where'].update(choice='r0001'),
    lambda d: d['answers']['where'].update(confidence=float('inf')),
    lambda d: d['answers']['where'].pop('confidence'),
    lambda d: d['answers']['exists'].update(noul=.5, extra='bad'),
    lambda d: d['answers']['exists'].update(noul=True),
])
def test_invalid_choice_or_exists_is_rejected(mutation):
    data = response()
    mutation(data)
    with pytest.raises(ValueError):
        m.validate(data, questions())
