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


# Narrowest to widest. A pass clears the failure count only when it is at least as wide as the
# widest profile that failed since the count was last cleared.
BREADTH = ('Fast', 'Task', 'Phase', 'Full')


def seconds_between(start, end):
    seconds = (parse_time(end) - parse_time(start)).total_seconds()
    if seconds < 0:
        raise PipelineError('Clock moved backwards; inspect timing evidence before resuming')
    return seconds


def new_accounting(task=False):
    result = {'budget_version': 1, 'active_seconds': 0.0, 'renewals': []}
    if task:
        result.update(failed_attempts=0, failed_profile=None, pending_run=None)
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


def grant(root, reason, extra_minutes, extra_attempts, released=None):
    record = {'id': uuid.uuid4().hex, 'at': utc_now(), 'reason': reason,
              'extra_minutes': extra_minutes, 'extra_attempts': extra_attempts}
    if released:
        record['released'] = released
    validate_schema(root, 'renewal', record)
    if not reason.strip() or not (extra_minutes or extra_attempts or released):
        raise PipelineError('Renew requires a substantive reason and a positive additional budget')
    return record


def reached_stops(config, iteration):
    """The failure stops a task reached; a count below its limit is not one."""
    limits = config.get('iteration_limits', {})
    return {key: iteration[key] for key, default in (('same_failure', 3), ('external_retries', 2))
            if iteration.get(key, 0) >= limits.get(key, default)}


def release_stops(iteration, released):
    """End the sequences behind the released stops. Only a user-requested renewal calls this."""
    if 'same_failure' in released:
        iteration.update(same_failure=0, same_failure_profile=None)
        for key in ('last_failure', 'last_failure_fingerprint'):
            if key in iteration:
                iteration[key] = None
    if 'external_retries' in released:
        iteration['external_retries'] = 0


def task_remaining(config, iteration):
    minutes, _ = additions(Path('.'), iteration)
    return (config['iteration_limits']['elapsed_minutes'] + minutes) * 60 - iteration['active_seconds']


def time_mode(limits):
    """Absent policy preserves existing installations' hard time limits."""
    mode = limits.get('time_budget_mode', 'enforce')
    if mode not in {'warn', 'enforce'}:
        raise PipelineError('Invalid time_budget_mode; expected warn or enforce')
    return mode


def time_warnings(limits, accounting, label, extra_seconds=0.0):
    if time_mode(limits) != 'warn' or accounting.get('budget_version') != 1:
        return []
    minutes, _ = additions(Path('.'), accounting)
    threshold = (limits.get('elapsed_minutes', 120) + minutes) * 60
    used = accounting['active_seconds'] + extra_seconds
    if used < threshold:
        return []
    return [f'{label}: cumulative active time {used / 60:.2f} minutes reached '
            f'{threshold / 60:g} minutes; advisory only (time_budget_mode=warn)']


def budget_only(summary):
    """Refund only a conclusive budget pause, never mixed or unknown failures."""
    nonpass = [check for check in summary['checks']
               if check['status'] not in {'PASS', 'NOT_APPLICABLE'}]
    return (summary['status'] == 'BLOCKED' and bool(nonpass)
            and all(check['status'] == 'BLOCKED' and check.get('blocker_kind') == 'budget'
                    for check in nonpass))


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
        if time_mode(limits) == 'enforce' and task_remaining(config, iteration) <= 0:
            raise BudgetLimit('iteration active-time limit reached; use loop renew --task')
    if iteration.get('same_failure', 0) >= limits.get('same_failure', 3):
        raise PipelineError('same-failure limit reached; report the cause and log to the user. '
                            'Only a user-requested loop renew --task releases it')
    if iteration.get('external_retries', 0) >= limits.get('external_retries', 2):
        raise PipelineError('external retry limit reached; report the blocker to the user. '
                            'Only a user-requested loop renew --task releases it')


def _rank(profile):
    return BREADTH.index(profile) if profile in BREADTH else -1


def covers(profile, failing):
    """Whether a pass of `profile` ran what failed; `failing` is the widest profile that failed."""
    return failing is None or _rank(profile) >= _rank(failing)


def wider(first, second):
    return second if _rank(second) > _rank(first) else first


def _settle(iteration, summary):
    """Turn the attempt reserved for this run into its result.

    failed_attempts counts failures since the last covering pass. A test written first fails
    once and then passes, so red-green work never exhausts the limit; only a run of failures
    does. A narrower pass (Fast after a failed Full) proves nothing about the wider failure:
    it refunds its own attempt and leaves the count.
    """
    profile, failing = summary.get('profile'), iteration.get('failed_profile')
    if summary['status'] == 'PASS' and covers(profile, failing):
        iteration['failed_attempts'] = 0
        iteration['failed_profile'] = None
    elif summary['status'] == 'PASS' or budget_only(summary):
        iteration['failed_attempts'] -= 1
    else:
        iteration['failed_profile'] = wider(failing, profile)


def finish_run(iteration, summary):
    """Settle a pre-execution reservation; actual sequence/external counters are separate."""
    pending = iteration['pending_run']
    if not pending or pending['run_id'] != summary['run_id']:
        raise PipelineError('Verification budget reservation mismatch')
    duration = seconds_between(summary['started_utc'], summary['completed_utc'])
    iteration['active_seconds'] += duration
    _settle(iteration, summary)
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
        # Replay the retained runs under the same rule a live run follows.
        for summary in sorted(summaries, key=lambda s: (s['started_utc'], s['run_id'])):
            iteration['failed_attempts'] += 1
            _settle(iteration, summary)
        iteration['active_seconds'] = sum(seconds_between(s['started_utc'], s['completed_utc']) for s in summaries)
    else:
        # Unknown old results are not invented as PASS or zero-time work.
        iteration['failed_attempts'] = before['attempts']
        iteration['failed_profile'] = 'Full' if before['attempts'] else None  # only a Full pass clears unknowns
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
    # The reserved failure stays at the profile it was reserved for, so a narrower pass cannot
    # clear it. A reservation from before the profile was recorded counts as Full.
    iteration['failed_profile'] = wider(iteration.get('failed_profile'), pending.get('profile') or 'Full')
    iteration['pending_run'] = None  # no false PASS or pointer restoration
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
