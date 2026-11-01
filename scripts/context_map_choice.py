"""TypeSafe semantic_find baseline; relative ranking is not per-region relevance."""
import math


def probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('invalid_probability')


def validate_choice(answer, question):
    if not isinstance(answer, dict) or set(answer) != {'type', 'choice', 'confidence', 'probabilities'} or answer['type'] != 'choice':
        raise ValueError('invalid_choice_answer')
    options = question.get('criteria')
    if not isinstance(options, dict) or not 1 <= len(options) <= 255:
        raise ValueError('invalid_choice_options')
    distribution = answer['probabilities']
    if not isinstance(distribution, dict) or set(distribution) != set(options):
        raise ValueError('invalid_choice_coverage')
    for value in distribution.values():
        probability(value)
    probability(answer['confidence'])
    if not math.isclose(math.fsum(distribution.values()), 1, rel_tol=0, abs_tol=1e-6):
        raise ValueError('invalid_choice_sum')
    selected = answer['choice']
    if not isinstance(selected, str) or selected not in options or distribution[selected] != max(distribution.values()):
        raise ValueError('invalid_choice_winner')


def questions(task, intent, regions):
    import json
    from scripts.context_map import GUARD
    prefix = GUARD + f'Known task: {json.dumps(task)}. Declared intent: {json.dumps(intent)}. '
    return {
        'where': {'type': 'choice', 'instructions': prefix +
                  'Which tagged region best supplies evidence answering the task and declared intent? '
                  'Rank the region IDs from the supplied complete source.',
                  'criteria': {r['id']: None for r in regions}},
        'exists': {'type': 'noul', 'instructions': prefix +
                   'Does the supplied document contain evidence that states or directly implies an answer '
                   'to the task and declared intent? Shared topic alone is not an answer. '
                   'This is answer existence, not whether a selected packet covers every requirement.'}}


def compose(text, regions, answer, top_k):
    from scripts.context_map import finalize
    exists = answer['exists']['noul'] if answer else None
    outcome = ('unavailable' if exists is None else 'present' if exists >= .8
               else 'absent' if exists <= .2 else 'uncertain')
    choice = answer['where'] if answer else None
    distribution = choice['probabilities'] if choice else {}
    ranked = sorted(regions, key=lambda r: (-distribution.get(r['id'], 0), r['start']))
    ranks = {r['id']: i for i, r in enumerate(ranked, 1)}
    rows = []
    for region in regions:
        selected = outcome in {'uncertain', 'unavailable'} or (outcome == 'present' and ranks[region['id']] <= top_k)
        reason = ('choice_top_k' if outcome == 'present' else 'existence_uncertain'
                  if outcome == 'uncertain' else 'unavailable')
        rows.append({**region, 'text': text[region['start']:region['end']], 'scores': None,
                     'choice_probability': distribution.get(region['id']),
                     'choice_rank': ranks[region['id']] if choice else None,
                     'status': 'ambiguous' if outcome == 'uncertain' else 'unavailable' if outcome == 'unavailable' else 'scored',
                     'selected': selected, 'reasons': [reason] if selected else []})
    return {**finalize(rows), 'arm': 'choice-exists', 'top_k': top_k,
            'choice_answer': choice, 'existence': {'probability': exists, 'outcome': outcome},
            'warning': 'Choice probabilities are relative ranking mass, not independent relevance. '
                       'A peaked winner does not prove an answer exists. Top-K may omit required exceptions '
                       'and other relevant regions; low mass does not mean irrelevant. Existence is not '
                       'packet completeness. Inspect every omission or recover the full source.'}
