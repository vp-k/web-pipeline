"""Source-bound self-review evidence, deliberately not human authorization."""
from __future__ import annotations

import json
from pathlib import Path

from .common import (PipelineError, atomic_json, code_snapshot, hash_file, load_config,
                     lock, read_state, safe_path, source_fingerprint, utc_now, validate_schema)


def ordinary_work(config, state):
    return (config.get('approval_policy', 'strict') == 'standard'
            and state['risk_tier'] in {'T0', 'T1', 'T2'}
            and not state.get('protected_changes'))


def validate_decision(root, decision):
    validate_schema(root, 'decision', decision)
    values = [decision['choice'], decision['rationale'], *decision['alternatives'], *decision['risks']]
    if any(not value.strip() for value in values):
        raise PipelineError('Decision fields must contain substantive non-empty text')


def _binding(root, config, state, snapshot=None):
    if not state['full_run']:
        raise PipelineError('Local review requires current completion evidence')
    digest = hash_file(safe_path(root, f"{config['project']['report_root']}/{state['full_run']}/summary.json", True))
    binding = {'task_id': state['task_id'], 'revision': state['revision'],
               'fingerprint': source_fingerprint(root, config, state),
               'tree_digest': (snapshot or code_snapshot(root, config))['tree_digest'],
               'run_id': state['full_run'], 'run_digest': digest}
    path = safe_path(root, f"Docs/Work/{state['task_id']}/LOCAL_REVIEW-{digest}.json")
    return binding, path


def record_review(root, task_id, decision):
    root = Path(root).resolve()
    validate_decision(root, decision)
    with lock(root, f'task-{task_id}'):
        config, state = load_config(root), read_state(root, task_id)
        if not ordinary_work(config, state) or state['risk_tier'] == 'T0':
            raise PipelineError('Local review gate is only for standard unprotected T1/T2 work; it cannot replace human approval')
        if state['status'] != 'REVIEW':
            raise PipelineError('Local review requires REVIEW state')
        from .state import policy_check
        checked = policy_check(root, task_id=task_id)
        if checked['status'] != 'PASS':
            raise PipelineError('; '.join(checked['errors']))
        binding, path = _binding(root, config, state)
        record = {**binding, 'kind': 'self_review', 'decision': decision, 'recorded_utc': utc_now()}
        validate_schema(root, 'local-review', record)
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf-8-sig'))
            validate_review(root, config, state)
            if previous['decision'] != decision:
                raise PipelineError('Review evidence already exists; do not overwrite decision history')
        else:
            atomic_json(path, record)
        return {'status': 'RECORDED', 'path': path.relative_to(root).as_posix(),
                'authority': 'self_review; not independent review or human approval'}


def validate_review(root, config, state, snapshot=None):
    """Caller must also validate completion, acceptance and task policy."""
    binding, path = _binding(root, config, state, snapshot)
    if not path.is_file():
        raise PipelineError('Current local review required: review --task <id> --decision <JSON>, or loop reviewed completion')
    record = json.loads(path.read_text(encoding='utf-8-sig'))
    validate_schema(root, 'local-review', record)
    validate_decision(root, record['decision'])
    if any(record[key] != value for key, value in binding.items()):
        raise PipelineError('Local review is stale; review the verified source and completion report')

