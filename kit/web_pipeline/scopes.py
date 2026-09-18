"""Explicit verification scope selection; absent configuration preserves legacy runs."""
from __future__ import annotations

import copy
import fnmatch
import json
from pathlib import Path

from .common import PipelineError, hash_file, read_state, safe_path, validate_schema
from .boundaries import affected_components

ARTIFACT = 'artifacts/verification-scope.json'
COMPLETION = {'Task', 'Phase', 'Full'}
BROAD_PATHS = ('pipeline.config.yaml', 'web_pipeline/*', 'Schemas/*', 'schemas/*',
               'Scripts/*', 'scripts/*', '.github/*', 'Docs/Governance/*',
               'Docs/Architecture/*', 'AGENTS.md', 'PIPELINE.md', 'CLAUDE.md', '*.lock', '*-lock.json',
               '*-lock.yaml', '*.lockb', '*npm-shrinkwrap.json', '*go.sum', '*go.mod', 'package.json',
               'pyproject.toml', 'requirements*.txt')


def enabled(config):
    return 'scopes' in config.get('verification', {})


def task_scope(root, config, state):
    path = safe_path(root, f"Docs/Work/{state['task_id']}/SCOPE.json")
    if not path.is_file():
        return {'level': 'task', 'components': [], 'members': []}
    if not enabled(config):
        raise PipelineError('SCOPE.json requires explicit verification.scopes configuration')
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    validate_schema(root, 'verification-scope', data)
    known = {c['id'] for c in config['verification']['scopes']['components']}
    if set(data['components']) - known:
        raise PipelineError('Scope references unknown components')
    if state['task_id'] in data['members']:
        raise PipelineError('A phase cannot contain itself')
    for member in data['members']:
        read_state(root, member)
        child_path = safe_path(root, f'Docs/Work/{member}/SCOPE.json')
        if child_path.is_file():
            child_scope = json.loads(child_path.read_text(encoding='utf-8-sig'))
            validate_schema(root, 'verification-scope', child_scope)
            if child_scope['level'] == 'phase':
                raise PipelineError('Nested phases are not supported; list ordinary tasks')
    return data


def completion_profile(root, config, state):
    if not enabled(config):
        return 'Full'
    return 'Phase' if task_scope(root, config, state)['level'] == 'phase' else 'Task'


def classification(root, config, state, paths):
    if not enabled(config):
        return set(), set(), 'T0'
    scope = task_scope(root, config, state)
    model = config['verification']['scopes']
    affected = affected_components(config, paths, scope['components'])
    domains = {d for c in model['components'] if c['id'] in affected for d in c['domains']}
    protected, tier = set(), 'T0'
    for task_id in scope['members']:
        member = read_state(root, task_id)
        domains.update(member['change_domains'])
        protected.update(member['protected_changes'])
        tier = max(tier, member['risk_tier'])
    return domains, protected, tier


def validate_config(root, config, kit=False):
    if not enabled(config):
        return
    model = config['verification']['scopes']
    validate_schema(root, 'verification-scopes', model)
    components = {c['id']: c for c in model['components']}
    if len(components) != len(model['components']):
        raise PipelineError('Duplicate verification component')
    commands = {c['id']: c for c in config['verification']['commands']}
    supported = set(config['project']['supported_domains'])
    for component in components.values():
        if set(component['depends_on']) - components.keys() or component['id'] in component['depends_on']:
            raise PipelineError('Verification component has invalid dependencies')
        if not set(component['domains']) <= supported:
            raise PipelineError('Verification component uses unsupported domains')
        for pattern in component['paths']:
            safe_path(root, pattern)
    for pattern in model['broad_paths']:
        safe_path(root, pattern)
    if 'boundaries' in config:
        boundary_components = {c['id']: c for c in config['boundaries']['components']}
        if boundary_components.keys() != components.keys() or any(
                set(c['paths']) != set(components[name]['paths']) for name, c in boundary_components.items()):
            raise PipelineError('Boundary and verification component IDs/paths must match')
    used = set(model['task_checks']) | set(model['phase_checks'])
    for component in components.values():
        used.update(component['checks']['Task'])
        used.update(component['checks']['Phase'])
    for check in used:
        command = commands.get(check)
        # Full eligibility ensures project-wide runs contain every scoped suite.
        if not command or 'Full' not in command['profiles'] or (not kit and not command['enabled']):
            raise PipelineError(f'Scoped check {check} must be enabled and executable in Full')


def _matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def historical_completion(root, config, member, trust_path=None, *, require_current=False):
    """Validate every completed-task gate, with source currency explicitly chosen."""
    from .runner import validate_completion, validate_run
    from .state import _review_gate, _roles
    from .approval import validate_approvals
    from .policy import document_errors
    if member['status'] != 'DONE' or not member['full_run'] or not member['baseline_run']:
        raise PipelineError(f"Phase member {member['task_id']} requires DONE with completion evidence and Baseline")
    errors = document_errors(root, member, for_done=True)
    if errors:
        raise PipelineError('; '.join(errors))
    validate_run(root, config, member, member['baseline_run'], 'Baseline',
                 require_current=False, trust_path=trust_path)
    validate_approvals(root, config, member, _roles(config, member, 'design'), 'design', trust_path)
    summary = validate_completion(root, config, member, member['full_run'],
                                  require_current=require_current, trust_path=trust_path)
    _review_gate(root, config, member, trust_path, summary['snapshot'])
    return summary


def _phase_members(root, config, scope, trust_path):
    from .evidence import acceptance_checks
    members, checks, components, domains = [], set(), set(), set()
    for task_id in scope['members']:
        member = read_state(root, task_id)
        if member['status'] != 'DONE' or not member['full_run']:
            raise PipelineError(f'Phase member {task_id} requires DONE with completion evidence')
        # Historical task evidence remains historical. Phase reruns the union of
        # member acceptance/regression checks against the current combined source.
        historical_completion(root, config, member, trust_path)
        summary_path = safe_path(root, f"{config['project']['report_root']}/{member['full_run']}/summary.json", True)
        artifact = safe_path(summary_path.parent, ARTIFACT, True)
        plan = json.loads(artifact.read_text(encoding='utf-8-sig'))
        components.update(plan['components'])
        domains.update(member['change_domains'])
        checks.update(acceptance_checks(root, member))
        checks.update(plan['checks'])
        members.append({'task_id': task_id, 'revision': member['revision'],
                        'fingerprint': member['fingerprint'], 'run_id': member['full_run'],
                        'run_digest': hash_file(summary_path)})
    return members, checks, components, domains


def selection(root, config, state, profile, *, changed_paths=None, trust_path=None):
    """Return the exact argv check IDs, scope and expansion reasons before running."""
    from .evidence import acceptance_checks, required_checks
    from .policy import classify
    if not enabled(config):
        if profile in {'Task', 'Phase'}:
            raise PipelineError('Task/Phase profiles require verification.scopes')
        return None
    model = config['verification']['scopes']
    scope = task_scope(root, config, state)
    if profile == 'Task' and scope['level'] == 'phase':
        raise PipelineError('A phase requires Phase verification')
    if profile == 'Phase' and scope['level'] != 'phase':
        raise PipelineError('Phase requires a tracked phase SCOPE.json')
    if changed_paths is None:
        classified = classify(root, config, state)
        if classified['errors']:
            raise PipelineError('; '.join(classified['errors']))
        changed_paths = classified['changed_paths']
    reasons, affected = [], set(scope['components'])
    project_wide = profile in {'Full', 'Release'}
    if project_wide:
        reasons.append('explicit project-wide profile')
    if state['risk_tier'] in {'T3', 'T4'} or state.get('protected_changes'):
        project_wide = True
        reasons.append('protected or high-risk change')
    for path in changed_paths:
        owners = {c['id'] for c in model['components'] if _matches(path, c['paths'])}
        if _matches(path, (*BROAD_PATHS, *model['broad_paths'])):
            project_wide = True
            reasons.append(f'broad input: {path}')
        if len(owners) != 1:
            project_wide = True
            reasons.append(f'unknown or ambiguous impact: {path}')
        affected.update(owners)
    members, member_checks, member_domains = [], set(), set()
    # Baseline and Fast need no completed members; completion runs do.
    if scope['level'] == 'phase' and profile in COMPLETION | {'Release'}:
        members, member_checks, member_components, member_domains = _phase_members(
            root, config, scope, trust_path)
        affected.update(member_components)
    boundary_model = config.get('boundaries')
    if boundary_model:
        # Map boundary inventory/contract participants by their actual paths;
        # mismatching models expand rather than omitting contract evidence.
        boundary_ids = {c['id'] for c in boundary_model['components']}
        if boundary_ids != {c['id'] for c in model['components']}:
            project_wide = True
            reasons.append('boundary and verification component IDs differ')
    affected = affected_components(config, changed_paths, affected)
    if not affected:
        project_wide = True
        reasons.append('no explicit or inferred component scope')
    if project_wide:
        affected = {c['id'] for c in model['components']}
    domains = set(state['change_domains']) | member_domains
    for component in model['components']:
        if component['id'] in affected:
            domains.update(component['domains'])
    effective = copy.deepcopy(state)
    effective['change_domains'] = sorted(domains)
    task_checks = acceptance_checks(root, state)
    if project_wide:
        effective['change_domains'] = sorted(set(config['project']['supported_domains']) | domains)
        checks = set(required_checks(config, effective, 'Release' if profile == 'Release' else 'Full', task_checks))
        checks.update(model['task_checks'])
        checks.update(model['phase_checks'])
        for component in model['components']:
            checks.update(component['checks']['Task'])
            checks.update(component['checks']['Phase'])
    else:
        checks = set(config['verification']['policy_checks']) | set(model['task_checks'])
        if profile != 'Policy':
            for component in model['components']:
                if component['id'] in affected:
                    checks.update(component['checks']['Task'])
                    if profile == 'Phase':
                        checks.update(component['checks']['Phase'])
            if profile == 'Phase':
                checks.update(model['phase_checks'])
            if profile in COMPLETION:
                checks.update(task_checks)
        if boundary_model:
            checks.add(boundary_model['dependency_check'])
            if profile in COMPLETION:
                for contract in boundary_model['contracts']:
                    if affected & {contract['provider'], *contract['consumers']}:
                        checks.update(contract['checks'].values())
    if profile == 'Policy':
        checks = set(config['verification']['policy_checks'])
        if boundary_model:
            checks.add(boundary_model['dependency_check'])
    checks.update(member_checks)
    return {'profile': profile, 'level': 'project' if project_wide else scope['level'],
            'components': sorted(affected), 'domains': effective['change_domains'],
            'changed_paths': sorted(changed_paths), 'checks': sorted(checks),
            'reasons': reasons or ['declared components plus transitive consumers'],
            'members': members}


def phase_coverage(root, config, trust_path=None):
    """Current verified phases may cover historical member runs at all-task gates."""
    if not enabled(config):
        return {}
    covered = {}
    work = Path(root) / 'Docs/Work'
    for directory in sorted(work.iterdir()) if work.is_dir() else []:
        if not directory.is_dir():
            continue
        try:
            phase = read_state(root, directory.name)
            if phase['status'] != 'DONE' or task_scope(root, config, phase)['level'] != 'phase':
                continue
            historical_completion(root, config, phase, trust_path, require_current=True)
            run_dir = safe_path(root, f"{config['project']['report_root']}/{phase['full_run']}", True)
            plan = json.loads(safe_path(run_dir, ARTIFACT, True).read_text(encoding='utf-8-sig'))
            for member in plan['members']:
                member_dir = safe_path(root, f"{config['project']['report_root']}/{member['run_id']}", True)
                member_plan = json.loads(safe_path(member_dir, ARTIFACT, True).read_text(encoding='utf-8-sig'))
                covered[member['task_id']] = member_plan['changed_paths']
        except (PipelineError, OSError, ValueError, KeyError):
            # Invalid phases confer no coverage and fail their own normal gate.
            continue
    return covered
