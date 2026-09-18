"""Structured planning evidence; never user approval or a second task state."""
from __future__ import annotations

import json

from .common import PipelineError, read_state, safe_path, validate_schema

AREAS = ('goal_scope', 'user_flow', 'exceptions', 'data_integrations',
         'constraints', 'acceptance')


def template(state):
    return {'schema_version': '1.0', 'task_id': state['task_id'],
            'revision': state['revision'],
            'analysis': [{'area': area, 'finding': '', 'sources': []} for area in AREAS],
            'questions': []}


def inspect(root, state):
    """Read-only diagnostic. CLEAR means recorded questions resolved, not READY."""
    path = safe_path(root, f"Docs/Work/{state['task_id']}/CLARIFICATIONS.json")
    required = state.get('planning_version') == 1
    if not required and not path.exists():
        return {'result': 'NOT_CONFIGURED', 'errors': [], 'questions': [], 'next_action': 'CONTINUE',
                'reason': 'Legacy task has no structured planning evidence; revise to enable it'}
    errors = []
    questions = []
    try:
        if not path.is_file():
            raise PipelineError('missing CLARIFICATIONS.json planning record')
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        validate_schema(root, 'clarifications', data)
        questions = data['questions']
        if data['task_id'] != state['task_id'] or data['revision'] != state['revision']:
            errors.append('planning record task/revision is stale; retain answers and reanalyze this revision')
        areas = [entry['area'] for entry in data['analysis']]
        if sorted(areas) != sorted(AREAS):
            errors.append('planning analysis must cover each required area exactly once')
        for entry in data['analysis']:
            if not entry['finding'].strip() or not entry['sources']:
                errors.append(f"planning analysis incomplete: {entry['area']}")
            for source in entry['sources']:
                _source(root, source)
        ids = [item['id'] for item in questions]
        if len(ids) != len(set(ids)):
            errors.append('clarification question IDs must be unique')
        acceptance = json.loads(safe_path(root, f"Docs/Work/{state['task_id']}/ACCEPTANCE.json", True).read_text(encoding='utf-8-sig'))
        validate_schema(root, 'acceptance', acceptance)
        criteria = {item['id'] for item in acceptance.get('criteria', [])}
        for question in questions:
            resolution = question['resolution']
            if resolution is None:
                errors.append(f"unresolved material clarification {question['id']}: {question['question']}")
                continue
            _source(root, resolution['source'])
            if not set(resolution['acceptance_ids']).issubset(criteria):
                errors.append(f"clarification {question['id']} references unknown acceptance criteria")
    except (PipelineError, OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'planning clarification: {exc}')
    action = ('REPAIR_RECORD' if any(not error.startswith('unresolved material clarification ') for error in errors)
              else 'CHECK_EXISTING_REQUIREMENTS' if errors else 'CONTINUE')
    return {'result': 'NEEDS_INPUT' if errors else 'CLEAR', 'errors': errors, 'next_action': action,
            'questions': questions, 'required': required}


def _source(root, source):
    # A file source must actually exist. Conversation provenance is transcription,
    # not authentication; the agent must preserve the real user's words and context.
    if source['kind'] == 'document':
        path = safe_path(root, source['reference'], True)
        if not path.is_file():
            raise PipelineError('planning source must reference a file')
        if source['excerpt'] not in path.read_text(encoding='utf-8-sig'):
            raise PipelineError(f"planning source excerpt no longer matches: {source['reference']}")


def source_hashes(root, state):
    """Bind referenced documents too, including documents outside standard sources."""
    from .common import hash_file
    path = safe_path(root, f"Docs/Work/{state['task_id']}/CLARIFICATIONS.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        validate_schema(root, 'clarifications', data)
        sources = [source for item in data['analysis'] for source in item['sources']]
        sources += [item['resolution']['source'] for item in data['questions'] if item['resolution']]
        return {source['reference']: hash_file(safe_path(root, source['reference'], True))
                for source in sources if source['kind'] == 'document'}
    except (OSError, ValueError) as exc:
        raise PipelineError(f'Invalid planning source evidence: {exc}') from exc


def errors(root, state):
    return inspect(root, state)['errors']


def report(root, task_id):
    state = read_state(root, task_id)
    return {'task_id': task_id, 'revision': state['revision'], **inspect(root, state)}
