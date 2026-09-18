"""Explicit queue barriers; no check, review, approval or task state is bypassed."""
from .common import PipelineError, read_state, source_fingerprint
from .scopes import enabled, task_scope


def validate_groups(root, config, plan, *, starting=False):
    groups = plan.get('implementation_groups', [])
    if not groups:
        return groups
    if not enabled(config):
        raise PipelineError('Implementation groups require verification.scopes')
    graph = {item['task_id']: set(item['depends_on']) for item in plan['tasks']}
    assigned, phases = {}, set()
    for group in groups:
        phase, order = group['phase'], group['order']
        if phase not in graph or not set(order) <= graph.keys() or phase in phases:
            raise PipelineError('Implementation group requires a unique queued Phase and queued members')
        phases.add(phase)
        state = read_state(root, phase)
        scope = task_scope(root, config, state)
        if scope['level'] != 'phase' or set(scope['members']) != set(order):
            raise PipelineError('Implementation group order must contain every Phase member exactly once')
        if not set(order) <= graph[phase]:
            raise PipelineError('Group Phase requires completion dependencies on every member')
        if not state['fingerprint'] or source_fingerprint(root, config, state) != state['fingerprint']:
            raise PipelineError('Prepare the group Phase with the final contract and scope before starting/resuming')
        for name in order:
            if name in assigned:
                raise PipelineError('Implementation groups cannot overlap')
            assigned[name] = phase
            if graph[name] & set(order):
                raise PipelineError('No completion dependencies inside an implementation group; use its explicit order')
        if starting and any(read_state(root, name)['status'] != 'DRAFT' for name in [phase, *order]):
            raise PipelineError('Start an implementation group only with DRAFT Phase and members')
        if starting:
            for name in order:
                member = read_state(root, name)
                if not member['fingerprint'] or source_fingerprint(root, config, member) != member['fingerprint']:
                    raise PipelineError('Prepare every group member with its final contract and scope before starting')
    # Contract each group into one node to expose cycles caused by its barrier,
    # such as member -> outside task -> another member of the same group.
    def node(name):
        return ('group', assigned[name]) if name in assigned else ('task', name)
    collapsed = {}
    for name, dependencies in graph.items():
        collapsed.setdefault(node(name), set()).update(node(dep) for dep in dependencies)
    visited = set()
    def visit(name, stack):
        if name in stack:
            raise PipelineError('Implementation group barrier creates a completion dependency cycle')
        if name in visited:
            return
        for dep in collapsed.get(name, set()):
            visit(dep, stack | {name})
        visited.add(name)
    for name in collapsed:
        visit(name, set())
    return groups


def waits(root, config, queue, trust=None):
    groups = validate_groups(root, config, queue['plan'])
    result = {}
    items = {item['task_id']: item for item in queue['items']}
    positions = {name: index for index, name in enumerate(items)}
    groups = sorted(groups, key=lambda g: min(positions[name] for name in g['order']))
    dependencies = {entry['task_id']: entry['depends_on'] for entry in queue['plan']['tasks']}
    active, eligible = [], []
    for group in groups:
        order = group['order']
        states = {name: read_state(root, name) for name in [group['phase'], *order]}
        if any(state['revision'] != items[name]['revision'] for name, state in states.items()):
            raise PipelineError('Group revision changed; explicitly reconcile the affected Phase/members')
        started = any(event['kind'] == 'SELECT' and event.get('action') == 'IMPLEMENT'
                      and event['task_id'] in order and
                      event.get('identity', {}).get('revision') == states[event['task_id']]['revision']
                      for event in queue['events'])
        pending = [name for name in order if items[name]['cursor'] == 'IMPLEMENT']
        if not pending:
            continue  # Ordinary verification and Phase completion keep their gates.
        begun = started or any(states[name]['status'] != 'DRAFT' or states[name]['baseline_run']
                               for name in order)
        if begun:
            active.append(group)
        # Entry prerequisites belong to the whole group, even when only its last
        # member declares one. Otherwise early Baselines predate prerequisite edits.
        from .autopilot import _dependency_valid
        unmet = sorted({dep for name in order for dep in dependencies[name]
                        if not _dependency_valid(root, config, queue, dep, trust, name)})
        if unmet:
            result.update({name: 'Waiting for group prerequisites: ' + ', '.join(unmet)
                           for name in order})
            continue
        eligible.append(group)
        setup = [name for name in order if states[name]['status'] in {'DRAFT', 'READY'}]
        if setup:
            if started:
                raise PipelineError('Group setup changed after implementation; revise and reconcile the entire group')
            for name in set(order) - set(setup):
                result[name] = 'Waiting for all group Baselines and entry gates: ' + ', '.join(setup)
            continue
        if pending:
            for name in order:
                if name != pending[0]:
                    result[name] = 'Waiting for ordered group implementation: ' + ', '.join(pending)
            if not started:
                # The first implementation must see the exact common pre-change
                # tree. A retained SELECT permits recovery of an interrupted edit
                # without pretending a post-edit Baseline was pre-change evidence.
                from .runner import validate_run
                for name in order:
                    state = states[name]
                    if state['status'] != 'IN_PROGRESS' or items[name]['waiting']:
                        result[pending[0]] = f'Group member is not ready to implement: {name}'
                        break
                    validate_run(root, config, state, state['baseline_run'], 'Baseline',
                                 require_current=True, trust_path=trust)
    reserved = (active or eligible)
    if reserved:
        group = reserved[0]
        anchor = min(positions[name] for name in group['order'])
        for name in items:
            if name not in group['order'] and (active or positions[name] >= anchor):
                result[name] = 'Waiting for group setup/initial implementation: ' + group['phase']
    return result


def validate_action(root, config, queue, task_id, trust=None):
    """Check current entry authority without replacing historical Baselines."""
    from .approval import validate_approvals
    from .policy import classify, document_errors
    from .runner import validate_run
    from .scopes import historical_completion
    from .state import _roles
    items = {item['task_id']: item for item in queue['items']}
    for group in queue['plan'].get('implementation_groups', []):
        if task_id not in group['order']:
            continue
        for name in group['order']:
            state = read_state(root, name)
            if state['status'] not in {'IN_PROGRESS', 'VERIFYING', 'REVIEW', 'DONE'} or items[name]['waiting']:
                raise PipelineError(f'Group member is blocked or not ready: {name}')
            if (not state['fingerprint'] or not state['implementer'] or
                    source_fingerprint(root, config, state) != state['fingerprint']):
                raise PipelineError(f'Group member prepared scope is stale: {name}')
            classified = classify(root, config, state)
            errors = classified['errors'] + document_errors(root, state, for_done=state['status'] == 'DONE')
            if errors or any(state[key] != classified[key] for key in
                             ('risk_tier', 'change_domains', 'protected_changes')):
                raise PipelineError(f'Group member policy/classification is stale: {name}: ' + '; '.join(errors))
            if state['status'] == 'DONE':
                historical_completion(root, config, state, trust)
            else:
                validate_run(root, config, state, state['baseline_run'], 'Baseline',
                             require_current=False, trust_path=trust)
                validate_approvals(root, config, state, _roles(config, state, 'design'), 'design', trust)
