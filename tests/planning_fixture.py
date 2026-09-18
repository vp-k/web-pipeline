"""Explicit synthetic planning evidence for isolated regression fixtures only."""
from web_pipeline.clarifications import template
from web_pipeline.common import atomic_json, read_state


def record_fixture_planning(root, task):
    state = read_state(root, task)
    data = template(state)
    relative = f'Docs/Work/{task}/BRIEF.md'
    source = {'kind': 'document', 'reference': relative,
              'excerpt': (root / relative).read_text(encoding='utf-8')}
    findings = {
        'goal_scope': 'Synthetic test scope is defined by the fixture brief.',
        'user_flow': 'Only the explicitly exercised CLI or engine lifecycle is in scope.',
        'exceptions': 'Negative outcomes are specified by each regression assertion.',
        'data_integrations': 'Temporary fixture files and local checks only; no production integration.',
        'constraints': 'Keep classification, approval and evidence checks active in the fixture.',
        'acceptance': 'The fixture ACCEPTANCE.json declares the checks under test.'}
    for entry in data['analysis']:
        entry.update(finding=findings[entry['area']], sources=[source])
    atomic_json(root / f'Docs/Work/{task}/CLARIFICATIONS.json', data)
    return data
