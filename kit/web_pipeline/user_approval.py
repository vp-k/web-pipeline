"""Scoped user-decision receipts, not authenticated identities or signatures."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .common import (PipelineError, atomic_json, canonical_hash, code_snapshot, hash_file,
                     load_config, lock, parse_time, read_state, safe_path,
                     source_fingerprint, utc_now, validate_schema, write_state)


def exception_requirements(config, state, check_id):
    if check_id not in {c['id'] for c in config['verification']['commands']} | {'browser-screenshots'}:
        raise PipelineError('Exception requires an exact configured check ID')
    relevant = {change for change in state.get('protected_changes', [])
                if any(check_id in ids for ids in config['risk']['protected_rules'][change]
                       .get('checks', {}).values())}
    roles = {'Tech Owner'}
    for change in relevant:
        roles.update(config['risk']['protected_rules'][change].get('roles', []))
    return sorted(roles), sorted(relevant)


def _request(root, config, state, phase, check_id=None, *, allow_unneeded=False, trust_path=None):
    from .state import _roles
    from .runner import validate_completion
    if config.get('approval_policy', 'strict') != 'standard':
        raise PipelineError('Strict policy requires signed approvals; user receipts are not accepted')
    if not state.get('fingerprint') or state['fingerprint'] != source_fingerprint(root, config, state):
        raise PipelineError('Approval request requires a current prepared fingerprint; revise/prepare first')
    if phase not in {'design', 'review', 'release', 'exception'}:
        raise PipelineError('Unknown approval phase')
    if phase == 'design' and state['status'] not in {'DRAFT', 'READY', 'BLOCKED'}:
        raise PipelineError('Design approval must precede implementation')
    if phase == 'review' and state['status'] != 'REVIEW':
        raise PipelineError('Review approval requires REVIEW with current completion evidence')
    if phase == 'release' and (state['status'] != 'DONE' or state['risk_tier'] != 'T4'):
        raise PipelineError('Release approval requires a DONE T4 task; no production authority is granted')
    if phase != 'exception' and check_id is not None:
        raise PipelineError('check_id is only valid for exception approval')
    roles, scope = (exception_requirements(config, state, check_id) if phase == 'exception'
                    else (_roles(config, state, phase), state['protected_changes']))
    if not roles:
        if allow_unneeded:
            return None
        raise PipelineError('No user approval required for this phase; ordinary review uses review --decision')
    request = {'task_id': state['task_id'], 'revision': state['revision'],
               'fingerprint': state['fingerprint'], 'phase': phase, 'roles': roles,
               'scope': sorted(scope), 'conditions': []}
    if phase == 'exception':
        request['check_id'] = check_id
    if phase in {'review', 'release'}:
        if not state.get('full_run'):
            raise PipelineError('Approval requires current passing completion evidence')
        summary = validate_completion(root, config, state, state.get('full_run'), trust_path=trust_path)
        request.update(tree_digest=summary['snapshot']['tree_digest'], run_id=summary['run_id'],
                       run_digest=hash_file(safe_path(root, f"{config['project']['report_root']}/{summary['run_id']}/summary.json", True)))
    return request


def approval_request(root, task_id, phase, check_id=None, *, trust_path=None):
    root = Path(root).resolve()
    with lock(root, f'task-{task_id}'):
        config, state = load_config(root), read_state(root, task_id)
        from .policy import classify
        classified = classify(root, config, state)
        if classified['errors'] or any(state[key] != classified[key] for key in
                                       ('risk_tier', 'change_domains', 'protected_changes')):
            raise PipelineError('Approval requirements need current task classification; reconcile the changed scope first')
        request = _request(root, config, state, phase, check_id, allow_unneeded=True, trust_path=trust_path)
        if request is None:
            return {'status': 'NO_APPROVAL_REQUIRED', 'task_id': task_id, 'phase': phase,
                    'next_action': 'CONTINUE',
                    'instruction': 'Continue the authorized work without asking for approval. Verification and local review still apply.'}
        from .approval import validate_approvals, validate_exception
        try:
            if phase == 'exception':
                validate_exception(root, config, state, check_id, trust_path=trust_path)
            else:
                snapshot = code_snapshot(root, config) if phase in {'review', 'release'} else None
                validate_approvals(root, config, state, request['roles'], phase,
                                   trust_path=trust_path, snapshot=snapshot, run_id=request.get('run_id'))
        except PipelineError as exc:
            return {'status': 'AWAITING_USER', 'request': request, 'reason': str(exc),
                    'next_action': 'CHECK_EXISTING_CONSENT',
                    'instruction': 'Inspect actual prior user messages for this unchanged phase and scope before prompting. Transcribe applicable explicit consent with approve, repair invalid evidence where possible, then rerun approval-request. If a decision remains missing, cite the project gate and ask once for that concrete decision and its current responsibilities; do not ask broadly for implementation/testing permission or bundle optional archival. Preserve separate design, review, exception and release decisions.'}
        return {'status': 'SATISFIED', 'request': request,
                'next_action': 'CONTINUE',
                'instruction': 'Current recorded approval already satisfies this phase. Do not ask again or create another receipt; continue through the normal gates.'}


def verify_receipt(root, config, state, record, phase, snapshot=None, run_id=None):
    from .approval import _validate_binding
    if config.get('approval_policy', 'strict') != 'standard':
        raise PipelineError('Strict policy requires signatures, not a user receipt')
    validate_schema(root, 'user-approval', record)
    if parse_time(record['recorded_utc']) > parse_time(utc_now()):
        raise PipelineError('User approval receipt is dated in the future')
    payload = record['payload']
    if state.get('fingerprint') != source_fingerprint(root, config, state):
        raise PipelineError('User approval fingerprint is stale')
    _validate_binding(root, state, payload, phase, snapshot, run_id, 'user receipt')
    from .state import _roles
    roles, scope = (exception_requirements(config, state, payload.get('check_id')) if phase == 'exception'
                    else (_roles(config, state, phase), state['protected_changes']))
    if not set(payload['roles']) <= set(roles) or not set(payload['scope']) <= set(scope):
        raise PipelineError('User approval roles/scope exceed this decision phase')
    if phase == 'review' and set(payload['scope']) != set(scope):
        raise PipelineError('Review approval must cover the full protected scope')
    if phase in {'review', 'release'}:
        digest = hash_file(safe_path(root, f"{config['project']['report_root']}/{run_id}/summary.json", True))
        if payload['run_digest'] != digest:
            raise PipelineError('User approval does not bind the completion summary bytes')
    return payload


def record_approval(root, task_id, data, *, trust_path=None):
    """Transcribe supplied user consent without inventing it or transitioning STATE."""
    root = Path(root).resolve()
    with lock(root, f'task-{task_id}'):
        config, state = load_config(root), read_state(root, task_id)
        if not isinstance(data, dict):
            raise PipelineError('Approval input must be an object')
        record = {'kind': 'user_approval', 'assurance': 'local_transcription',
                  'recorded_utc': utc_now(), 'payload': copy.deepcopy(data)}
        validate_schema(root, 'user-approval', record)
        expected = _request(root, config, state, data['phase'], data.get('check_id'), trust_path=trust_path)
        for key, value in expected.items():
            if key not in {'conditions', 'roles', 'scope'} and data.get(key) != value:
                raise PipelineError(f'Stale or mismatched approval request: {key}')
        snapshot = code_snapshot(root, config) if data['phase'] in {'review', 'release'} else None
        verify_receipt(root, config, state, record, data['phase'], snapshot, data.get('run_id'))
        # Partial responsibilities/scope may be recorded; the gate still requires
        # coverage of every configured responsibility before it can transition.
        relative = f'Docs/Work/{task_id}/USER_APPROVAL-{canonical_hash(data)}.json'
        path = safe_path(root, relative)
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf-8-sig'))
            verify_receipt(root, config, state, previous, data['phase'], snapshot, data.get('run_id'))
            if previous['payload'] != data:
                raise PipelineError('Refusing to overwrite a user approval receipt')
        else:
            atomic_json(path, record)
        field = 'exceptions' if data['phase'] == 'exception' else 'approvals'
        if relative not in state[field]:
            state[field].append(relative)
            state['updated_utc'] = utc_now()
            write_state(root, state)
        return {'status': 'RECORDED', 'path': relative, 'task_status': state['status'],
                'assurance': 'local_transcription', 'production_authorized': False}
