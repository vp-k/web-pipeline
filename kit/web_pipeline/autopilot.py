"""Durable scheduling for the active coding agent; never a human approver.

Only queue commands cooperate with this lease. External filesystem writers and
independent engine invocations still require host/workspace isolation.
"""
from __future__ import annotations

import json
from pathlib import Path
import uuid

from .common import (PipelineError, atomic_json, canonical_hash, code_snapshot, hash_file,
                     load_config, lock, read_state, safe_path, source_fingerprint,
                     utc_now, validate_schema)
from .common import write_state
from .budget import (BudgetLimit, additions, grant, migrate_queue, migrate_task,
                     new_accounting, seconds_between, settle_interrupted, time_mode, time_warnings)
from .runner import _enforce_iteration_limits, run_profile, validate_completion
from .state import policy_check, transition
from .local_review import ordinary_work, record_review, validate_decision
from .git_state import require_settled_checkout

QUEUE = 'Docs/Work/AUTOPILOT.json'


def _save(root, queue):
    validate_schema(root, 'autopilot', queue)
    atomic_json(safe_path(root, QUEUE), queue)


def _load(root):
    queue = json.loads(safe_path(root, QUEUE, True).read_text(encoding='utf-8-sig'))
    validate_schema(root, 'autopilot', queue)
    if queue.get('schema_version') != '1.0':
        raise PipelineError('Unsupported autopilot checkpoint')
    validate_schema(root, 'autopilot-plan', queue['plan'])
    if [item['task_id'] for item in queue['items']] != [item['task_id'] for item in queue['plan']['tasks']]:
        raise PipelineError('Queue task inventory mismatch')
    additions(root, queue)
    if [event['sequence'] for event in queue['events']] != list(range(1, len(queue['events']) + 1)):
        raise PipelineError('Queue event sequence is incomplete')
    if queue.get('budget_version') == 1 and [r['id'] for r in queue['renewals']] != [
            e.get('grant', {}).get('id') for e in queue['events'] if e['kind'] == 'RENEW']:
        raise PipelineError('Queue renewals do not match their audit events')
    return queue


def _event(queue, kind, task_id=None, **details):
    queue['events'].append({'sequence': len(queue['events']) + 1, 'at': utc_now(),
                            'kind': kind, 'task_id': task_id, **details})


def _identity(root, state, config):
    return {'revision': state['revision'], 'state_hash': canonical_hash(state),
            'fingerprint': source_fingerprint(root, config, state),
            'tree_digest': code_snapshot(root, config)['tree_digest'],
            'full_run': state['full_run']}


def start(root, plan, trust=None):
    root = Path(root).resolve()
    config = load_config(root)  # NOT_READY and kit are not execution modes.
    validate_schema(root, 'autopilot-plan', plan)
    # Freeze the project default at creation; never reinterpret old checkpoints.
    plan = {**plan, 'time_budget_mode': plan.get('time_budget_mode', time_mode(config['iteration_limits']))}
    identifiers = [item['task_id'] for item in plan['tasks']]
    if len(set(identifiers)) != len(identifiers):
        raise PipelineError('Duplicate queued task')
    graph = {item['task_id']: item['depends_on'] for item in plan['tasks']}
    visited = set()
    def visit(name, stack):
        if name in stack:
            raise PipelineError('Dependency cycle')
        if name not in graph:
            raise PipelineError('Dependency outside authorized queue')
        if name in visited:
            return
        for dependency in graph[name]:
            visit(dependency, stack | {name})
        visited.add(name)
    for name in identifiers:
        visit(name, set())
    from .scopes import enabled, task_scope
    if enabled(config):
        for name in identifiers:
            scope = task_scope(root, config, read_state(root, name))
            if scope['level'] == 'phase' and not set(scope['members']) <= set(graph[name]):
                raise PipelineError('Queued phases require explicit dependencies on every member task')
    with lock(root, 'autopilot'):
        require_settled_checkout(root)
        from .implementation_groups import validate_groups
        validate_groups(root, config, plan, starting=True)
        if safe_path(root, QUEUE).exists():
            previous = _load(root)
            if previous['lease'] or _completion_result(root, previous, trust)['status'] != 'COMPLETE':
                raise PipelineError('Queue already exists; resume it, or use loop renew --queue/--task after user authorization; never reset history')
            history = safe_path(root, f"Docs/Work/AUTOPILOT-{previous['queue_id']}.json")
            if history.exists():
                raise PipelineError('Queue history already exists; refusing overwrite')
            atomic_json(history, previous)
        items = [{'task_id': name, 'revision': read_state(root, name)['revision'],
                  'cursor': 'IMPLEMENT', 'waiting': None, 'advisory': None} for name in identifiers]
        queue = {'schema_version': '1.0', 'queue_id': uuid.uuid4().hex, 'plan': plan,
                 'started_utc': utc_now(), 'steps': 0, 'lease': None, 'items': items, 'events': [], **new_accounting()}
        _event(queue, 'START', reason=plan['objective'], task_order=identifiers,
               dependencies=graph, authority='user-scoped work, not human approval')
        _save(root, queue)
    return {'status': 'STARTED', 'queue_id': queue['queue_id'], 'checkpoint': QUEUE}


def status(root):
    root = Path(root).resolve()
    queue = _load(root)
    paused = _limited(queue)
    return {'status': 'BUSY' if queue['lease'] else ('PAUSED_LIMIT' if paused else 'IDLE'), 'queue_id': queue['queue_id'],
            'paused_reason': paused,
            'warnings': _time_warnings(root, queue),
            'steps': queue['steps'], 'lease': queue['lease'], 'events': queue['events'],
            'budget': {key: queue.get(key) for key in ('budget_version', 'active_seconds', 'renewals')},
            'tasks': [{**item, 'task_status': read_state(root, item['task_id'])['status'],
                       'iteration': read_state(root, item['task_id'])['iteration']}
                      for item in queue['items']]}


def _limited(queue):
    if queue.get('budget_version') != 1:
        return 'legacy queue accounting requires loop renew --queue migration'
    minutes, steps = additions(Path('.'), queue)
    if queue['steps'] >= queue['plan'].get('max_steps', 100) + steps:
        return 'queue step limit reached; use loop renew --queue --extra-attempts'
    if (time_mode(queue['plan']) == 'enforce'
            and queue['active_seconds'] >= (queue['plan'].get('elapsed_minutes', 120) + minutes) * 60):
        return 'queue active-time limit reached; use loop renew --queue --extra-minutes'
    return None


def _time_warnings(root, queue):
    warnings = time_warnings(queue['plan'], queue, 'Queue')
    # Diagnostics must not hide an existing lease during readiness repairs.
    # Execution still uses normal project validation before each action.
    config = load_config(root, kit=True)
    for item in queue['items']:
        state = read_state(root, item['task_id'])
        warnings.extend(time_warnings(config['iteration_limits'], state['iteration'],
                                      f"Task {item['task_id']}"))
    return warnings


def _claim(root, queue, item, state, config, worker, action, agent, reason, alternatives):
    queue['steps'] += 1
    lease = {'token': uuid.uuid4().hex, 'worker': worker, 'task_id': state['task_id'],
             'action': action, 'agent': agent, 'identity': _identity(root, state, config), 'started_utc': utc_now()}
    queue['lease'] = lease
    _event(queue, 'SELECT', state['task_id'], action=action, reason=reason,
           alternatives=alternatives, identity=lease['identity'], token=lease['token'])
    _save(root, queue)  # checkpoint BEFORE any machine or agent side effect
    return lease


def _close_lease(queue):
    lease = queue['lease']
    if queue.get('budget_version') == 1:
        duration = seconds_between(lease['started_utc'], utc_now())
        queue['active_seconds'] += duration
        _event(queue, 'LEASE_END', lease['task_id'], token=lease['token'], active_seconds=duration)
    queue['lease'] = None


def _done_valid(root, task_id, trust):
    return (read_state(root, task_id)['status'] == 'DONE'
            and policy_check(root, task_id=task_id, trust_path=trust)['status'] == 'PASS')


def _completion_result(root, queue, trust):
    """One completion contract for both next and checkpoint replacement."""
    waits = []
    for item in queue['items']:
        name = item['task_id']
        state = read_state(root, name)
        if state['revision'] != item['revision'] or state['status'] != 'DONE':
            waits.append({'task_id': name, 'reason': 'Queued revision requires current DONE evidence and approvals'})
            continue
        checked = policy_check(root, task_id=name, trust_path=trust)
        if checked['status'] != 'PASS':
            waits.append({'task_id': name, 'reason': '; '.join(checked['errors'])})
    if waits:
        return {'status': 'WAITING', 'tasks': waits}
    scope = queue['plan'].get('completion_gate', 'queue')
    gate = (policy_check(root, trust_path=trust, gate='merge') if scope == 'merge' else
            {'status': 'NOT_APPLICABLE', 'reason': 'Queue completion does not request merge readiness'})
    if scope == 'merge' and gate['status'] != 'PASS':
        return {'status': 'WAITING', 'completion_gate': scope, 'merge_gate': gate,
                'reason': 'Required merge readiness failed; resolve the reported blockers before starting another queue'}
    return {'status': 'COMPLETE', 'completion_gate': scope, 'merge_gate': gate}


def _dependency_valid(root, config, queue, task_id, trust, for_task=None):
    if _done_valid(root, task_id, trust):
        return True
    from .scopes import enabled, historical_completion, task_scope
    if not enabled(config):
        return False
    for item in queue['items']:
        phase = read_state(root, item['task_id'])
        scope = task_scope(root, config, phase)
        if (phase['status'] == 'DONE' or phase['revision'] != item['revision']
                or scope['level'] != 'phase' or task_id not in scope['members']):
            continue
        declared = next(entry['depends_on'] for entry in queue['plan']['tasks'] if entry['task_id'] == phase['task_id'])
        if not set(scope['members']) <= set(declared):
            continue
        if for_task and for_task not in [phase['task_id'], *scope['members']]:
            continue
        try:
            historical_completion(root, config, read_state(root, task_id), trust)
            return True  # scheduling only; completion still needs the current Phase
        except (PipelineError, OSError, ValueError, KeyError):
            return False
    return False


def advance(root, worker='claude', trust=None):
    root = Path(root).resolve()
    if not worker.strip():
        raise PipelineError('Worker identity is required')
    with lock(root, 'autopilot'):
        queue = _load(root)
        def respond(result):
            return {**result, 'warnings': _time_warnings(root, queue)}
        if queue['lease']:
            return respond({'status': 'BUSY', 'reason': 'Unfinished action; inspect status and recover explicitly'})
        while True:
            try:
                require_settled_checkout(root)
            except PipelineError as exc:
                _event(queue, 'WAITING', scope='workspace', reason=str(exc))
                _save(root, queue)
                return respond({'status': 'WAITING', 'scope': 'workspace', 'reason': str(exc)})
            if all(read_state(root, i['task_id'])['status'] == 'DONE' for i in queue['items']):
                result = _completion_result(root, queue, trust)
                if result['status'] != 'COMPLETE':
                    _event(queue, 'WAITING', result=result)
                    _save(root, queue)
                return respond(result)
            reason = _limited(queue)
            if reason:
                return respond({'status': 'PAUSED_LIMIT', 'reason': reason, 'steps': queue['steps']})
            config = load_config(root)
            from .implementation_groups import waits as implementation_waits
            group_waits = implementation_waits(root, config, queue, trust)
            waits = []
            progress = False
            for item in queue['items']:
                name = item['task_id']
                state = read_state(root, name)
                dependencies = next(t['depends_on'] for t in queue['plan']['tasks'] if t['task_id'] == name)
                try:
                    if state['revision'] != item['revision']:
                        raise PipelineError('Revision differs from authorized queue; scope must be reconciled explicitly')
                    if state['status'] == 'DONE':
                        if not _dependency_valid(root, config, queue, name, trust):
                            raise PipelineError('DONE evidence/approval is no longer current; explicit task revision is required')
                        continue
                    if name in group_waits:
                        raise PipelineError(group_waits[name])
                    unmet = [dep for dep in dependencies if not _dependency_valid(root, config, queue, dep, trust, name)]
                    if unmet:
                        raise PipelineError('Waiting for dependencies: ' + ', '.join(unmet))
                    if item['waiting']:
                        raise PipelineError(item['waiting'])
                    if state['status'] == 'BLOCKED':
                        raise PipelineError('Task is BLOCKED; resolve it through the normal engine gates')
                    action, agent = None, False
                    if state['status'] == 'DRAFT':
                        _enforce_iteration_limits(config, state)
                        if not state['fingerprint']:
                            action, agent = 'PLAN', True
                        elif not state['baseline_run']:
                            action = 'Baseline'
                        else:
                            action = 'READY'
                    elif state['status'] == 'READY':
                        action = 'IN_PROGRESS'
                    elif state['status'] in {'IN_PROGRESS', 'VERIFYING'}:
                        checked = policy_check(root, task_id=name, trust_path=trust)
                        if checked['status'] != 'PASS':
                            raise PipelineError('; '.join(checked['errors']))
                        _enforce_iteration_limits(config, state)
                        if item['cursor'] in {'IMPLEMENT', 'REPAIR'}:
                            action, agent = item['cursor'], True
                        elif item['cursor'] == 'FAST':
                            action = 'Fast'
                        elif state['status'] == 'IN_PROGRESS':
                            action = 'VERIFYING'
                        else:
                            from .scopes import completion_profile
                            action = completion_profile(root, config, state)
                    elif state['status'] == 'REVIEW':
                        # Never turn stale source/evidence into a successful review.
                        summary = validate_completion(root, config, state, state['full_run'], trust_path=trust)
                        digest = hash_file(safe_path(root, f"{config['project']['report_root']}/{state['full_run']}/summary.json", True))
                        if item['advisory'] != digest:
                            action, agent = 'REVIEW', True
                        else:
                            action = 'DONE'
                    if not action:
                        raise PipelineError('No valid next action')
                    if agent and action in {'IMPLEMENT', 'REPAIR'}:
                        from .implementation_groups import validate_action
                        validate_action(root, config, queue, name, trust)
                    alternatives = [f"{w['task_id']}: {w['reason']}" for w in waits]
                    alternatives += [other['task_id'] + ': later in authorized order' for other in queue['items'][queue['items'].index(item)+1:]]
                    lease = _claim(root, queue, item, state, config, worker, action, agent,
                                   'First dependency-ready task in authorized order; next action derived from STATE and evidence', alternatives)
                    if agent:
                        return respond({'status': 'ACTION_REQUIRED', **lease, 'checkpoint': QUEUE,
                                'instruction': 'Perform the scoped action, record a decision, complete this token, then call loop next again. Do not end the turn here.'})
                    try:
                        if action in {'Baseline', 'Fast', 'Task', 'Phase', 'Full'}:
                            summary = run_profile(root, name, action, trust_path=trust)
                            if action == 'Baseline' and not read_state(root, name)['baseline_run']:
                                item['waiting'] = 'Baseline did not establish valid pre-change evidence'
                            elif action in {'Fast', 'Task', 'Phase', 'Full'}:
                                if summary['status'] != 'PASS':
                                    item['cursor'] = 'REPAIR'
                                elif action == 'Fast':
                                    item['cursor'] = 'FULL'
                                else:
                                    transition(root, name, 'REVIEW', trust_path=trust)
                                    item['advisory'] = None
                            outcome = {'run_id': summary['run_id'], 'status': summary['status']}
                        else:
                            transition(root, name, action, trust_path=trust)
                            outcome = {'transition': action}
                        _event(queue, 'EXECUTED', name, action=action, outcome=outcome,
                               identity=_identity(root, read_state(root, name), config))
                    except PipelineError as exc:
                        # Budget exhaustion is recomputed after renew, not cached
                        # as an unrelated external gate requiring a synthetic retry.
                        item['waiting'] = None if isinstance(exc, BudgetLimit) else str(exc)
                        _event(queue, 'WAIT', name, action=action, reason=str(exc))
                    _close_lease(queue)
                    _save(root, queue)
                    progress = True
                    break
                except PipelineError as exc:
                    waits.append({'task_id': name, 'reason': str(exc), 'budget_limit': isinstance(exc, BudgetLimit)})
            if progress:
                continue
            if waits:
                _event(queue, 'WAITING', reasons=waits)
                _save(root, queue)
                return respond({'status': 'PAUSED_LIMIT' if all(w['budget_limit'] for w in waits) else 'WAITING', 'tasks': waits})
            return respond(_completion_result(root, queue, trust))


def complete(root, token, outcome, decision, trust=None):
    root = Path(root).resolve()
    validate_decision(root, decision)
    with lock(root, 'autopilot'):
        queue = _load(root)
        lease = queue['lease']
        if not lease or lease['token'] != token or not lease['agent']:
            raise PipelineError('Stale, duplicate or non-agent action token')
        if outcome != 'blocked':
            require_settled_checkout(root)
        config = load_config(root)
        name = lease['task_id']
        state = read_state(root, name)
        item = next(i for i in queue['items'] if i['task_id'] == name)
        if state['revision'] != item['revision']:
            raise PipelineError('Task revision changed during action; recover explicitly')
        action = lease['action']
        if action != 'PLAN' and canonical_hash(state) != lease['identity']['state_hash']:
            raise PipelineError('Task state changed during action; recover explicitly')
        if action != 'PLAN' and source_fingerprint(root, config, state) != lease['identity']['fingerprint']:
            raise PipelineError('Task scope changed during action; recover explicitly')
        allowed = {'PLAN': {'prepared', 'blocked'}, 'IMPLEMENT': {'implemented', 'blocked'},
                   'REPAIR': {'implemented', 'blocked'}, 'REVIEW': {'reviewed', 'changes_required', 'blocked'}}
        if outcome not in allowed[action]:
            raise PipelineError('Outcome is not valid for this action')
        if outcome == 'blocked':
            item['waiting'] = decision['rationale']
        elif action == 'PLAN':
            if state['status'] != 'DRAFT' or not state['fingerprint'] or state['fingerprint'] != source_fingerprint(root, config, state):
                raise PipelineError('PLAN completion requires an actually prepared DRAFT')
        elif action == 'REVIEW':
            if code_snapshot(root, config)['tree_digest'] != lease['identity']['tree_digest']:
                raise PipelineError('Review changed source; do not approve unverified changes')
            validate_completion(root, config, state, state['full_run'], trust_path=trust)
            if outcome == 'changes_required':
                transition(root, name, 'IN_PROGRESS', trust_path=trust)
                item['cursor'], item['advisory'] = 'REPAIR', None
            else:
                if ordinary_work(config, state) and state['risk_tier'] != 'T0':
                    record_review(root, name, decision)
                item['advisory'] = hash_file(safe_path(root, f"{config['project']['report_root']}/{state['full_run']}/summary.json", True))
        else:
            item['cursor'] = 'FAST'
        _event(queue, 'DECISION', name, action=action, outcome=outcome, decision=decision,
               before=lease['identity'], after=_identity(root, read_state(root, name), config),
               authority='agent advisory only; no human approval')
        _close_lease(queue)
        _save(root, queue)
        return {'status': 'CONTINUE', 'instruction': 'Call loop next; this acknowledgement is not task completion'}


def recover(root, token, reason):
    """Explicitly release an inspected interrupted action, without replaying it."""
    if not reason.strip():
        raise PipelineError('Recovery requires inspection notes')
    root = Path(root).resolve()
    with lock(root, 'autopilot'):
        queue = _load(root)
        lease = queue['lease']
        if not lease or lease['token'] != token:
            raise PipelineError('Recovery token does not match unfinished action')
        _event(queue, 'RECOVER', lease['task_id'], token=token, action=lease['action'], reason=reason)
        item = next(i for i in queue['items'] if i['task_id'] == lease['task_id'])
        item['waiting'] = 'Interrupted action inspected; use loop retry when safe to continue'
        _close_lease(queue)
        _save(root, queue)
    return {'status': 'RECOVERED', 'budgets_reset': False}


def retry(root, task_id, reason):
    if not reason.strip():
        raise PipelineError('Retry requires evidence of the changed external condition')
    root = Path(root).resolve()
    with lock(root, 'autopilot'):
        queue = _load(root)
        if queue['lease']:
            raise PipelineError('Unfinished action must be completed or recovered first')
        item = next((i for i in queue['items'] if i['task_id'] == task_id), None)
        if item is None:
            raise PipelineError('Task is outside queue')
        item['waiting'] = None
        _event(queue, 'RETRY', task_id, reason=reason)
        _save(root, queue)
    return {'status': 'CONTINUE', 'budgets_reset': False}


def reconcile(root, task_id, reason):
    """Explicitly accept an authorized revised task in the existing queue."""
    if not reason.strip():
        raise PipelineError('Scope reconciliation needs the user-authorized change rationale')
    root = Path(root).resolve()
    with lock(root, 'autopilot'):
        queue = _load(root)
        if queue['lease']:
            raise PipelineError('Recover/complete the unfinished action before reconciling scope')
        item = next((i for i in queue['items'] if i['task_id'] == task_id), None)
        if item is None:
            raise PipelineError('Task is outside queue')
        state = read_state(root, task_id)
        if state['status'] != 'DRAFT' or state['revision'] <= item['revision']:
            raise PipelineError('Reconcile requires a new DRAFT revision created with revise')
        _event(queue, 'RECONCILE', task_id, reason=reason, previous_revision=item['revision'], revision=state['revision'])
        item.update(revision=state['revision'], cursor='IMPLEMENT', waiting=None, advisory=None)
        _save(root, queue)
    return {'status': 'CONTINUE', 'budgets_reset': False}


def renew(root, *, task_id=None, queue_target=False, reason, extra_minutes=0, extra_attempts=0):
    """Add a bounded user-requested grant, never approval, reset, or scope change."""
    root = Path(root).resolve()
    if bool(task_id) == bool(queue_target):
        raise PipelineError('Select exactly one renewal target: --queue or --task')
    record = grant(root, reason, extra_minutes, extra_attempts)
    config = load_config(root)
    with lock(root, 'autopilot'):
        queue = _load(root) if safe_path(root, QUEUE).exists() else None
        if queue and queue['lease']:
            raise PipelineError('Complete or recover the unfinished lease before renew; inspect running processes')
        if queue_target:
            if queue is None:
                raise PipelineError('No queue exists to renew')
            record['usage_before'] = {key: queue.get(key) for key in ('steps', 'active_seconds')}
            record['migration'] = migrate_queue(queue)
            queue['renewals'].append(record)
            _event(queue, 'RENEW', reason=reason, grant=record)
            _save(root, queue)
            return {'status': 'RENEWED', 'target': 'queue', 'grant': record,
                    'active_seconds': queue['active_seconds'], 'steps': queue['steps'],
                    'remaining_limit': _limited(queue), 'budgets_reset': False}
        with lock(root, f'task-{task_id}'):
            state = read_state(root, task_id)
            if state['status'] == 'DONE':
                raise PipelineError('DONE work needs no new execution budget; revise authorized scope first')
            record['usage_before'] = {key: state['iteration'].get(key) for key in
                                      ('attempts', 'failed_attempts', 'active_seconds')}
            record['migration'] = migrate_task(root, config, state)
            additions(root, state['iteration'])
            record['settlement'] = settle_interrupted(root, config, state)
            state['iteration']['renewals'].append(record)
            state['updated_utc'] = utc_now()
            write_state(root, state)
            try:
                _enforce_iteration_limits(config, state)
                remaining_limit = None
            except PipelineError as exc:
                remaining_limit = str(exc)
            return {'status': 'RENEWED', 'target': task_id, 'grant': record,
                    'iteration': state['iteration'], 'budgets_reset': False,
                    'remaining_limit': remaining_limit,
                    'instruction': 'Resume through normal gates; renew grants no approval and does not clear failure guards'}
