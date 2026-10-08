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

from .common import (PipelineError, atomic_json, canonical_hash, code_snapshot, load_config, missing_checks,
                     output_exclusions, safe_path, utc_now)

WORKFLOWS = ('lean', 'tracked')
CHECK_PROFILES = ('Fast', 'Task', 'Full')
TRACKED_TIER = 'T4'


def workflow(config: dict[str, Any]) -> str:
    """Configs written before 2.14 have no key and keep the tracked workflow."""
    return config.get('workflow', 'tracked')


def default_profile(config: dict[str, Any]) -> str:
    """With declared components a pre-commit check covers what changed; without them, everything."""
    from .scopes import enabled
    return 'Task' if enabled(config) else 'Full'


def _scoped(root: Path, config: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    """The tracked Task selection for the changed paths: affected components, their consumers,
    contracts and the dependency check. Broad, unowned or ambiguous paths and T4 select the project."""
    from .scopes import selection
    state = {'task_id': None, 'risk_tier': risk['risk_tier'], 'protected_changes': risk['protected_changes'],
             'change_domains': risk['change_domains']}
    return selection(root, config, state, 'Task', changed_paths=risk['changed_paths'],
                     scope={'level': 'task', 'components': [], 'members': []}, task_checks=())


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
    """Ways the new configuration runs or requires less than the old one.

    A shorter timeout is not weakening: a timed-out check fails, it never passes.
    """
    from .guards import report_loosening
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
        elif old.get('enabled'):
            found.extend(report_loosening(old, new))
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


def _base_config(root: Path, base_ref: str) -> dict[str, Any] | None:
    """The configuration at base_ref. No base file means nothing to compare."""
    from .policy import option_shaped
    if not base_ref or option_shaped(base_ref):
        return None
    try:
        shown = subprocess.run(['git', 'show', f'{base_ref}:./pipeline.config.yaml'], cwd=root,
                               capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if shown.returncode:
        return None
    try:
        before = json.loads(shown.stdout.decode('utf-8-sig'))
    except ValueError:
        return None
    return before if isinstance(before, dict) else None


def _merge_base(root: Path, base_ref: str) -> str | None:
    """The commit where HEAD left base_ref. The changed paths are measured from it, so the old
    test files and configuration are read there too, not at a base branch that has moved on."""
    from .policy import option_shaped
    if not base_ref or option_shaped(base_ref):
        return None
    try:
        shown = subprocess.run(['git', 'merge-base', base_ref, 'HEAD'], cwd=root, capture_output=True, text=True,
                               check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return shown.stdout.strip() or None if shown.returncode == 0 else None


def history(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Readable lean check summaries, newest first. An unreadable summary proves nothing and is skipped."""
    report = safe_path(root, config['project']['report_root'])
    runs = []
    for path in report.glob('check-*/summary.json') if report.is_dir() else []:
        try:
            run = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        if isinstance(run, dict) and isinstance(run.get('started_at'), str) and run.get('run_id') == path.parent.name:
            runs.append(run)
    return sorted(runs, key=lambda run: (run['started_at'], run['run_id']), reverse=True)


def current(root: Path, config: dict[str, Any], run: dict[str, Any]) -> bool:
    """Whether a check still describes the working tree and the whole configuration it ran under.
    A summary without a config digest predates this rule and is not current."""
    recorded = run.get('snapshot') or {}
    return (recorded.get('tree_digest') == code_snapshot(root, config)['tree_digest']
            and run.get('config_digest') == canonical_hash(config))


def last_check(root: Path, config: dict[str, Any]) -> dict[str, Any] | None:
    """The newest check for status: a session that lost its context reads this, not its memory."""
    runs = history(root, config)
    if not runs:
        return None
    run = runs[0]
    failing = [item['id'] for item in run.get('checks', []) if item.get('status') != 'PASS']
    return {'run_id': run['run_id'], 'profile': run.get('profile'), 'status': run.get('status'),
            'base_ref': run.get('base_ref'), 'failing': failing, 'current': current(root, config, run), 'repeat': run.get('repeat'),
            'same_failure': run.get('same_failure', 0), 'test_changes': run.get('test_changes', [])}


def _base(root: Path, config: dict[str, Any], base_ref: str | None) -> str:
    """An explicit base wins; otherwise the commit the active feature started from, then HEAD."""
    if base_ref:
        return base_ref
    if workflow(config) == 'lean':
        from .features import active_base
        commit = active_base(root)
        if commit:
            return commit
    return 'HEAD'


def _verify_report(root: Path, run_dir: Path, command: dict[str, Any], result: dict[str, Any]) -> None:
    """A zero exit is not test evidence when the check declares a structured report."""
    from .test_results import validate_report
    if not command.get('test_report') or result['status'] != 'PASS':
        return
    try:
        validate_report(root, run_dir, command)
    except (PipelineError, OSError, ValueError) as exc:
        reason = f'Test report invalid: {exc}'
        result.update(status='FAIL', reason=reason)
        with safe_path(run_dir, result['log']).open('ab') as log:
            log.write(f'pipeline: {reason}\n'.encode('utf-8', 'replace'))


def check(root: Path, profile: str | None = None, base_ref: str | None = None) -> dict[str, Any]:
    from .evidence import failure_fingerprint, policy_snapshot
    from .guards import command_changes, rerun_facts, script_changes, test_changes
    from .policy import _changed_paths, path_risk
    from .runner import _execute
    from .scopes import enabled
    config = load_config(root)
    base_ref = _base(root, config, base_ref)
    profile = profile or default_profile(config)
    if profile not in CHECK_PROFILES:
        raise PipelineError(f'check profile must be one of {", ".join(CHECK_PROFILES)}')
    if profile == 'Task' and not enabled(config):
        raise PipelineError('check --profile Task needs components in verification.scopes '
                            '(Docs/Runbooks/VERIFICATION_SCOPES.md); use Full without them')
    paths, diff_errors = _changed_paths(root, base_ref)
    risk = path_risk(root, config, paths)
    domains = set(config['project']['supported_domains']) | set(risk['change_domains'])
    scope = None
    if profile == 'Task':
        plan = _scoped(root, config, risk)
        scope = {'level': plan['level'], 'components': plan['components'], 'reasons': plan['reasons']}
    if scope and scope['level'] != 'project':
        wanted = set(plan['checks'])
        commands = [item for item in config['verification']['commands'] if item['enabled'] and item['id'] in wanted]
        missing = sorted(wanted - {item['id'] for item in commands})
    else:
        # A project-wide Task check is the Full check.
        selected = 'Full' if scope else profile
        commands = selected_commands(config, selected, domains)
        missing = missing_checks(config, sorted(domains), (selected,), risk['protected_changes'])
    base_commit = _merge_base(root, base_ref)
    compare = base_commit or base_ref
    before = _base_config(root, compare)
    weakened: list[str] = []
    notices = list(risk['notices'])
    warnings = diff_errors + risk['errors']
    if before:
        try:
            weakened, changed = config_weakening(before, config), command_changes(before, config)
        except (KeyError, TypeError, AttributeError, ValueError):
            weakened = []
            warnings.append(f'pipeline.config.yaml at {compare} could not be compared: '
                            'review the configuration changes by hand')
        else:
            notices += changed
    notices += script_changes(root, config['verification']['commands'], compare)
    tracked = risk['risk_tier'] == TRACKED_TIER
    result: dict[str, Any] = {
        'workflow': workflow(config), 'profile': profile, 'scope': scope, 'base_ref': base_ref,
        'base_commit': base_commit, 'changed_paths': risk['changed_paths'], 'risk_tier': risk['risk_tier'],
        'change_domains': risk['change_domains'], 'decisions': risk['protected_changes'],
        'tracked_required': tracked, 'notices': notices, 'weakened_checks': weakened,
        'test_changes': test_changes(root, compare, paths),
        'missing_checks': missing, 'warnings': warnings, 'checks': []}
    if not commands:
        return {**result, 'status': 'FAIL', 'commit_table': _table([], missing),
                'next': f'No enabled check runs in {profile}: enable at least one real check in pipeline.config.yaml.'}
    report, _ = output_exclusions(root, config)
    run_id = time.strftime('check-%Y%m%dT%H%M%SZ-', time.gmtime()) + uuid.uuid4().hex[:6]
    run_dir = safe_path(root, f'{report}/{run_id}')
    run_dir.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    snapshot, policy, digest = code_snapshot(root, config), policy_snapshot(config), canonical_hash(config)
    earlier = history(root, config)
    results = []
    for item in commands:
        outcome = _execute(item, root, run_dir, profile=profile)
        _verify_report(root, run_dir, item, outcome)
        results.append(outcome)
    failed = [item['id'] for item in results if item['status'] != 'PASS']
    status = 'FAIL' if failed else 'PASS'
    failure = failure_fingerprint(results, run_dir=run_dir, root=root)
    facts = rerun_facts(earlier, profile, snapshot, digest, base_commit, failure)
    table = _table(results, missing)
    open_items = risk['protected_changes'] + (['the weakened checks'] if weakened else [])
    repeat = facts['repeat']
    limit = int(config.get('iteration_limits', {}).get('same_failure', 3))
    if failed:
        hint = 'Fix ' + ', '.join(failed) + ' and run check again. Do not commit a failing check.'
        if repeat and repeat['status'] != 'PASS':
            hint = ('Fix ' + ', '.join(failed) + f". {repeat['run_id']} already failed on this exact tree, "
                    'configuration and base, so this run repeated it: read the log and change the code before the next check. '
                    'Rerun unchanged code only after naming the environment change. Do not commit a failing check.')
        if facts['same_failure'] >= limit:
            hint += (f" The same failure came back {facts['same_failure']} times with no wider pass between: stop trial edits, "
                     'find the root cause from the log, or ask the user.')
    elif tracked:
        hint = 'Checks pass, but the change touches T4 paths: move it to a tracked task (new ...) before release.'
    elif profile == 'Fast':
        # Only a Task or Full check opens the commit gate; a Fast pass is iteration.
        hint = 'Fast checks pass: run check before the commit. A Fast pass cannot finish a feature.'
    elif open_items:
        hint = ('Checks pass. Confirm the user decided ' + ', '.join(open_items)
                + '; ask once if not, then commit with the table and the decision.')
    else:
        hint = 'Checks pass: get one fresh-context review, then commit with the table.'
    if not failed and scope and scope['level'] != 'project':
        hint += (' This check covered ' + ', '.join(scope['components'])
                 + ' and their consumers; run check --profile Full before a release or merge.')
    if not failed and repeat and repeat['status'] == 'PASS':
        hint += f" Note: {repeat['run_id']} had already passed on this exact tree, configuration and base."
    if result['test_changes']:
        hint += ' The review must confirm each test change: ' + '; '.join(result['test_changes']) + '.'
    summary = {**result, 'status': status, 'run_id': run_id, 'started_at': started, 'finished_at': utc_now(),
               'snapshot': snapshot, 'policy_snapshot': policy, 'config_digest': digest,
               'failure_fingerprint': failure, **facts,
               'checks': results, 'commit_table': table, 'next': hint}
    atomic_json(run_dir / 'summary.json', summary)
    return {**summary, 'evidence': run_dir.relative_to(root).as_posix()}
