"""Cumulative usage and explicit, additive execution-budget grants.

These are local audit records, not human approvals or an adversarial trust store.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import uuid

from .common import (PipelineError, canonical_hash, hash_file, parse_time, safe_path, utc_now,
                     validate_schema)


class BudgetLimit(PipelineError):
    pass


def seconds_between(start, end):
    seconds = (parse_time(end) - parse_time(start)).total_seconds()
    if seconds < 0:
        raise PipelineError('Clock moved backwards; inspect timing evidence before resuming')
    return seconds


def new_accounting(task=False):
    result = {'budget_version': 1, 'active_seconds': 0.0, 'renewals': []}
    if task:
        result.update(failed_attempts=0, pending_run=None)
    return result


def additions(root, data):
    ids, minutes, attempts = set(), 0, 0
    for record in data.get('renewals', []):
        validate_schema(root, 'renewal', record)
        if record['id'] in ids or not record['reason'].strip():
            raise PipelineError('Duplicate renewal or empty renewal reason')
        ids.add(record['id'])
        minutes += record['extra_minutes']
        attempts += record['extra_attempts']
    return minutes, attempts


def grant(root, reason, extra_minutes, extra_attempts):
    record = {'id': uuid.uuid4().hex, 'at': utc_now(), 'reason': reason,
              'extra_minutes': extra_minutes, 'extra_attempts': extra_attempts}
    validate_schema(root, 'renewal', record)
    if not reason.strip() or not (extra_minutes or extra_attempts):
        raise PipelineError('Renew requires a substantive reason and a positive additional budget')
    return record


def task_remaining(config, iteration):
    minutes, _ = additions(Path('.'), iteration)
    return (config['iteration_limits']['elapsed_minutes'] + minutes) * 60 - iteration['active_seconds']


def enforce_task(config, state):
    limits, iteration = config.get('iteration_limits', {}), state.get('iteration', {})
    # Keep original hard-stop behavior for unmigrated installations.
    if iteration.get('budget_version') != 1:
        if iteration.get('attempts', iteration.get('total_attempts', 0)) >= limits.get('total_attempts', 5):
            raise BudgetLimit('total attempt limit reached; use loop renew --task to migrate and add budget')
        if iteration.get('started_utc') and seconds_between(iteration['started_utc'], utc_now()) >= limits.get('elapsed_minutes', 120) * 60:
            raise BudgetLimit('iteration elapsed-time limit reached; use loop renew --task')
        raise BudgetLimit('Legacy task accounting requires explicit loop renew --task migration')
    else:
        _, attempts = additions(Path('.'), iteration)
        if iteration.get('pending_run'):
            raise BudgetLimit('Interrupted verification reservation; inspect processes then loop renew --task to settle budget')
        if iteration['failed_attempts'] >= limits.get('total_attempts', 5) + attempts:
            raise BudgetLimit('failed-attempt limit reached; use loop renew --task')
        if task_remaining(config, iteration) <= 0:
            raise BudgetLimit('iteration active-time limit reached; use loop renew --task')
    if iteration.get('same_failure', 0) >= limits.get('same_failure', 3):
        raise PipelineError('same-failure limit reached')
    if iteration.get('external_retries', 0) >= limits.get('external_retries', 2):
        raise PipelineError('external retry limit reached')


def finish_run(iteration, summary):
    """Settle a pre-execution reservation; actual sequence/external counters are separate."""
    pending = iteration['pending_run']
    if not pending or pending['run_id'] != summary['run_id']:
        raise PipelineError('Verification budget reservation mismatch')
    duration = seconds_between(summary['started_utc'], summary['completed_utc'])
    iteration['active_seconds'] += duration
    if summary['status'] == 'PASS':
        iteration['failed_attempts'] -= 1
    iteration['pending_run'] = None


def _historical_summary(root, path, task_id):
    from .evidence import validate_artifact_hashes
    summary = json.loads(path.read_text(encoding='utf-8-sig'))
    validate_schema(root, 'pipeline-summary', summary)
    if summary['task_id'] != task_id or summary['run_id'] != path.parent.name or summary['profile'] not in {'Fast', 'Task', 'Phase', 'Full'}:
        raise PipelineError('Historical verification identity mismatch')
    validate_artifact_hashes(path.parent, summary['artifacts'])
    recorded = {item['path'] for item in summary['artifacts']}
    if any(c.get('log') and c['log'] not in recorded for c in summary['checks']):
        raise PipelineError('Historical check log is not hash-bound')
    if summary['status'] == 'PASS' and any(
            c['status'] not in {'PASS', 'NOT_APPLICABLE'} or
            (c['status'] == 'PASS' and (c['exit_code'] != 0 or not c['log']))
            for c in summary['checks']):
        raise PipelineError('Historical PASS contradicts executed check evidence')
    seconds_between(summary['started_utc'], summary['completed_utc'])
    return summary


def migrate_task(root, config, state):
    iteration = state['iteration']
    if iteration.get('budget_version') == 1:
        return None
    before = copy.deepcopy(iteration)
    reports = safe_path(root, config['project']['report_root'])
    summaries, hashes = [], {}
    uncertain = False
    for candidate in sorted(reports.glob('*/summary.json')):
        path = safe_path(root, candidate.relative_to(root).as_posix(), True)
        try:
            raw = json.loads(path.read_text(encoding='utf-8-sig'))
            if raw.get('task_id') != state['task_id'] or raw.get('profile') not in {'Fast', 'Task', 'Phase', 'Full'}:
                continue
            summaries.append(_historical_summary(root, path, state['task_id']))
            hashes[path.relative_to(root).as_posix()] = hash_file(path)
        except (PipelineError, OSError, ValueError, AttributeError):
            uncertain = True
    exact = not uncertain and len(summaries) == iteration['attempts']
    iteration.update(new_accounting(task=True))
    if exact:
        iteration['failed_attempts'] = sum(s['status'] != 'PASS' for s in summaries)
        iteration['active_seconds'] = sum(seconds_between(s['started_utc'], s['completed_utc']) for s in summaries)
    else:
        # Unknown old results are not invented as PASS or zero-time work.
        iteration['failed_attempts'] = before['attempts']
        iteration['active_seconds'] = seconds_between(before['started_utc'], utc_now()) if before['started_utc'] else 0
        if before['attempts'] and not before['started_utc']:
            raise PipelineError('Legacy attempts lack a start timestamp; restore original timing evidence')
    return {'before': before, 'method': 'retained_summaries' if exact else 'conservative_legacy_usage',
            'summary_hashes': hashes}


def settle_interrupted(root, config, state):
    iteration = state['iteration']
    pending = iteration.get('pending_run')
    if not pending:
        return None
    path = safe_path(root, f"{config['project']['report_root']}/{pending['run_id']}/summary.json")
    if path.is_file():
        summary = _historical_summary(root, path, state['task_id'])
        if summary['started_utc'] != pending['started_utc']:
            raise PipelineError('Interrupted summary does not match the reserved execution start')
        finish_run(iteration, summary)
        return {'run_id': pending['run_id'], 'method': 'retained_summary', 'sha256': hash_file(path)}
    duration = seconds_between(pending['started_utc'], utc_now())
    iteration['active_seconds'] += duration
    iteration['pending_run'] = None  # reserved failure stays; no false PASS or pointer restoration
    return {'run_id': pending['run_id'], 'method': 'unknown_nonpass_conservative_time', 'seconds': duration}


def migrate_queue(queue):
    if queue.get('budget_version') == 1:
        return None
    if queue['lease']:
        raise PipelineError('Recover the unfinished lease before renewing the queue')
    pending, seconds, claims = None, 0.0, 0
    before_hash = canonical_hash(queue)
    for event in queue['events']:
        if event['kind'] == 'SELECT':
            if pending:
                raise PipelineError('Legacy queue has overlapping claims; inspect its history')
            pending = event
            claims += 1
        elif event['kind'] in {'EXECUTED', 'WAIT', 'DECISION', 'RECOVER'}:
            if not pending or pending['task_id'] != event['task_id']:
                raise PipelineError('Legacy queue action history is incomplete')
            seconds += seconds_between(pending['at'], event['at'])
            pending = None
    if pending or claims != queue['steps']:
        raise PipelineError('Legacy queue history cannot account for every step; restore its checkpoint')
    queue.update(new_accounting())
    queue['active_seconds'] = seconds
    return {'before_sha256': before_hash, 'method': 'retained_lease_intervals', 'claims': claims}
