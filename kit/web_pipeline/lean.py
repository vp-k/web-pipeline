"""Lean workflow: check the working tree before a commit, without a task.

Tracked tasks (STATE, fingerprints, approvals) stay available for work that
needs them. A lean check records logs and a summary under the report root but
creates nothing under Docs/Work and grants no approval.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from .common import PipelineError, atomic_json, load_config, output_exclusions, safe_path, utc_now

WORKFLOWS = ('lean', 'tracked')
CHECK_PROFILES = ('Fast', 'Full')
TRACKED_TIER = 'T4'


def workflow(config: dict[str, Any]) -> str:
    """Configs written before 2.14 have no key and keep the tracked workflow."""
    return config.get('workflow', 'tracked')


def _table(results: list[dict[str, Any]]) -> str:
    rows = [f"| {item['id']} | {item['status']} | {item['duration_ms'] / 1000:.1f}s |" for item in results]
    return '\n'.join(['| check | result | time |', '|---|---|---|', *rows])


def check(root: Path, profile: str = 'Full', base_ref: str = 'HEAD') -> dict[str, Any]:
    if profile not in CHECK_PROFILES:
        raise PipelineError(f'check profile must be one of {", ".join(CHECK_PROFILES)}')
    from .policy import _changed_paths, path_risk
    from .runner import _execute
    config = load_config(root)
    commands = [item for item in config['verification']['commands'] if item['enabled'] and profile in item['profiles']]
    paths, diff_errors = _changed_paths(root, base_ref)
    risk = path_risk(root, config, paths)
    warnings = diff_errors + risk['errors']
    tracked = risk['risk_tier'] == TRACKED_TIER
    result: dict[str, Any] = {
        'workflow': workflow(config), 'profile': profile, 'base_ref': base_ref,
        'changed_paths': risk['changed_paths'], 'risk_tier': risk['risk_tier'],
        'change_domains': risk['change_domains'], 'decisions': risk['protected_changes'],
        'tracked_required': tracked, 'warnings': warnings, 'checks': []}
    if not commands:
        return {**result, 'status': 'FAIL', 'commit_table': _table([]),
                'next': f'No enabled check runs in {profile}: enable real checks in pipeline.config.yaml.'}
    report, _ = output_exclusions(root, config)
    run_id = time.strftime('check-%Y%m%dT%H%M%SZ-', time.gmtime()) + uuid.uuid4().hex[:6]
    run_dir = safe_path(root, f'{report}/{run_id}')
    run_dir.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    results = [_execute(item, root, run_dir, profile=profile) for item in commands]
    failed = [item['id'] for item in results if item['status'] != 'PASS']
    status = 'FAIL' if failed else 'PASS'
    table = _table(results)
    if failed:
        hint = 'Fix ' + ', '.join(failed) + ' and run check again. Do not commit a failing check.'
    elif tracked:
        hint = 'Checks pass, but the change touches T4 paths: move it to a tracked task (new ...) before release.'
    elif risk['protected_changes']:
        hint = ('Checks pass. Confirm the user decided ' + ', '.join(risk['protected_changes'])
                + '; ask once if not, then commit with the table and the decision.')
    else:
        hint = 'Checks pass: get one fresh-context review, then commit with the table.'
    summary = {**result, 'status': status, 'run_id': run_id, 'started_at': started, 'finished_at': utc_now(),
               'checks': results, 'commit_table': table, 'next': hint}
    atomic_json(run_dir / 'summary.json', summary)
    return {**summary, 'evidence': run_dir.relative_to(root).as_posix()}
