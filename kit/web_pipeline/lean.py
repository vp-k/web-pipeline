"""Lean workflow: check the working tree before a commit, without a task.

Tracked tasks (STATE, fingerprints, approvals) stay available for work that
needs them. A lean check records logs and a summary under the report root but
creates nothing under Docs/Work and grants no approval.
"""
from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .common import PipelineError, atomic_json, load_config, missing_checks, output_exclusions, safe_path, utc_now

WORKFLOWS = ('lean', 'tracked')
CHECK_PROFILES = ('Fast', 'Full')
TRACKED_TIER = 'T4'


def workflow(config: dict[str, Any]) -> str:
    """Configs written before 2.14 have no key and keep the tracked workflow."""
    return config.get('workflow', 'tracked')


def _table(results: list[dict[str, Any]], missing: list[str]) -> str:
    rows = [f"| {item['id']} | {item['status']} | {item['duration_ms'] / 1000:.1f}s |" for item in results]
    table = '\n'.join(['| check | result | time |', '|---|---|---|', *rows])
    return table + ('\n\nNot enabled: ' + ', '.join(missing) if missing else '')


def _referenced(config: dict[str, Any]) -> set[str]:
    """Check IDs that the requirements or protected rules name; the rest are project-defined."""
    verification = config['verification']
    known = set(verification['policy_checks'])
    for profiles in verification['requirements'].values():
        for ids in profiles.values():
            known.update(ids)
    for rule in config['risk']['protected_rules'].values():
        for ids in rule.get('checks', {}).values():
            known.update(ids)
    return known


def selected_commands(config: dict[str, Any], profile: str, domains: set[str]) -> list[dict[str, Any]]:
    """Enabled commands for a lean profile. Policy commands run in every profile.

    Fast runs a check that the requirements name only when a domain in play lists
    it under Fast. Project-defined checks follow their own profiles.
    """
    verification = config['verification']
    fast = set(verification['policy_checks'])
    for domain in domains:
        fast.update(verification['requirements'].get(domain, {}).get('Fast', []))
    known = _referenced(config)
    return [item for item in verification['commands']
            if item['enabled'] and {profile, 'Policy'} & set(item['profiles'])
            and (profile != 'Fast' or item['id'] in fast or item['id'] not in known)]


def config_weakening(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Ways the new configuration runs or requires less than the old one."""
    found: list[str] = []
    old_verification, new_verification = before.get('verification', {}), after['verification']
    new_commands = {item['id']: item for item in new_verification['commands']}
    for old in old_verification.get('commands', []):
        new = new_commands.get(old['id'])
        dropped = sorted(set(old.get('profiles', [])) - set(new['profiles'])) if new else []
        if new is None:
            found.append(f"{old['id']}: check removed")
        elif old.get('enabled') and not new['enabled']:
            found.append(f"{old['id']}: check disabled")
        elif old.get('enabled') and dropped:
            found.append(f"{old['id']}: profiles {', '.join(dropped)} removed")
    for domain, profiles in old_verification.get('requirements', {}).items():
        for name, ids in profiles.items():
            for check_id in sorted(set(ids) - set(new_verification['requirements'].get(domain, {}).get(name, []))):
                found.append(f'{check_id}: no longer required for {domain} {name}')
    for check_id in sorted(set(old_verification.get('policy_checks', [])) - set(new_verification['policy_checks'])):
        found.append(f'{check_id}: no longer a policy check')
    for domain in sorted(set(before.get('project', {}).get('supported_domains', []))
                         - set(after['project']['supported_domains'])):
        found.append(f'{domain}: no longer a supported domain')
    new_rules = {json.dumps(rule, sort_keys=True) for rule in after['risk']['path_rules']}
    for rule in before.get('risk', {}).get('path_rules', []):
        guarded = rule.get('protected_changes') or rule.get('tier') in {'T3', 'T4'}
        if guarded and json.dumps(rule, sort_keys=True) not in new_rules:
            pattern = rule['pattern'] if isinstance(rule['pattern'], str) else ' '.join(rule['pattern'])
            found.append(f'path rule {pattern}: removed or changed')
    return found


def _weakened(root: Path, config: dict[str, Any], base_ref: str) -> list[str]:
    """Compare the working configuration with the one at base_ref. No base file means nothing to compare."""
    from .policy import option_shaped
    if not base_ref or option_shaped(base_ref):
        return []
    shown = subprocess.run(['git', 'show', f'{base_ref}:./pipeline.config.yaml'], cwd=root,
                           capture_output=True, check=False, timeout=60)
    if shown.returncode:
        return []
    try:
        before = json.loads(shown.stdout.decode('utf-8-sig'))
    except ValueError:
        return []
    return config_weakening(before, config) if isinstance(before, dict) else []


def check(root: Path, profile: str = 'Full', base_ref: str = 'HEAD') -> dict[str, Any]:
    if profile not in CHECK_PROFILES:
        raise PipelineError(f'check profile must be one of {", ".join(CHECK_PROFILES)}')
    from .policy import _changed_paths, path_risk
    from .runner import _execute
    config = load_config(root)
    paths, diff_errors = _changed_paths(root, base_ref)
    risk = path_risk(root, config, paths)
    domains = set(config['project']['supported_domains']) | set(risk['change_domains'])
    commands = selected_commands(config, profile, domains)
    missing = missing_checks(config, sorted(domains), (profile,), risk['protected_changes'])
    weakened = _weakened(root, config, base_ref)
    tracked = risk['risk_tier'] == TRACKED_TIER
    result: dict[str, Any] = {
        'workflow': workflow(config), 'profile': profile, 'base_ref': base_ref,
        'changed_paths': risk['changed_paths'], 'risk_tier': risk['risk_tier'],
        'change_domains': risk['change_domains'], 'decisions': risk['protected_changes'],
        'tracked_required': tracked, 'notices': risk['notices'], 'weakened_checks': weakened,
        'missing_checks': missing, 'warnings': diff_errors + risk['errors'], 'checks': []}
    if not commands:
        return {**result, 'status': 'FAIL', 'commit_table': _table([], missing),
                'next': f'No enabled check runs in {profile}: enable at least one real check in pipeline.config.yaml.'}
    report, _ = output_exclusions(root, config)
    run_id = time.strftime('check-%Y%m%dT%H%M%SZ-', time.gmtime()) + uuid.uuid4().hex[:6]
    run_dir = safe_path(root, f'{report}/{run_id}')
    run_dir.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    results = [_execute(item, root, run_dir, profile=profile) for item in commands]
    failed = [item['id'] for item in results if item['status'] != 'PASS']
    status = 'FAIL' if failed else 'PASS'
    table = _table(results, missing)
    open_items = risk['protected_changes'] + (['the weakened checks'] if weakened else [])
    if failed:
        hint = 'Fix ' + ', '.join(failed) + ' and run check again. Do not commit a failing check.'
    elif tracked:
        hint = 'Checks pass, but the change touches T4 paths: move it to a tracked task (new ...) before release.'
    elif open_items:
        hint = ('Checks pass. Confirm the user decided ' + ', '.join(open_items)
                + '; ask once if not, then commit with the table and the decision.')
    else:
        hint = 'Checks pass: get one fresh-context review, then commit with the table.'
    summary = {**result, 'status': status, 'run_id': run_id, 'started_at': started, 'finished_at': utc_now(),
               'checks': results, 'commit_table': table, 'next': hint}
    atomic_json(run_dir / 'summary.json', summary)
    return {**summary, 'evidence': run_dir.relative_to(root).as_posix()}
