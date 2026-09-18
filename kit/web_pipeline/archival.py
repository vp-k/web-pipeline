"""Archive validated task groups without losing queue or Phase evidence.

Renames are journaled and rolled back on failure. A process interruption leaves
the journal blocking engine mutations until explicit archive recovery.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import re

from .common import (PipelineError, atomic_json, hash_file, load_config, lock,
                     read_state, safe_path, utc_now, validate_schema)
from . import scopes

JOURNAL = 'Docs/Work/ARCHIVE_PENDING.json'
OUTPUTS = ('ARCHIVE.json', 'SOURCE.zip', 'SOURCE_MANIFEST.json')


def _group(root, config, task_id, include_members):
    state = read_state(root, task_id)
    scope = scopes.task_scope(root, config, state)
    phases = {}
    for directory in sorted((root / 'Docs/Work').iterdir()):
        if directory.is_dir() and (directory / 'STATE.md').is_file():
            other = read_state(root, directory.name)
            other_scope = scopes.task_scope(root, config, other)
            if other_scope['level'] == 'phase':
                phases[directory.name] = set(other_scope['members'])
    related = [name for name, members in phases.items() if task_id in members]
    if not include_members and (scope['members'] or related):
        phase = related[0] if related else task_id
        raise PipelineError(f'Phase evidence must be archived together: archive --task {phase} --include-members')
    if include_members and scope['level'] != 'phase':
        raise PipelineError('--include-members requires a Phase task')
    group = {task_id}
    if include_members:
        # Shared members connect phases. Keeping an active phase pointing to a
        # moved member would break both validation and its later archive.
        while True:
            expanded = group | {member for name, members in phases.items()
                                if name in group or members & group for member in {name, *members}}
            if expanded == group:
                break
            group = expanded
    return sorted(group)


def _rollback(root, journal):
    """Validate the complete recovery inventory before any move or removal."""
    entries = journal['entries']
    if not isinstance(entries, list) or not entries:
        raise PipelineError('Invalid archive recovery inventory')
    seen = set()
    for entry in entries:
        task = entry['task_id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,63}', task) or task in seen:
            raise PipelineError('Invalid archive recovery task')
        seen.add(task)
        if type(entry['revision']) is not int or entry['revision'] < 1:
            raise PipelineError('Invalid archive recovery revision')
        source = safe_path(root, f'Docs/Work/{task}')
        target = safe_path(root, f"Docs/Archive/{task}-r{entry['revision']}")
        if source.exists() == target.exists():
            raise PipelineError('Archive recovery requires exactly one state owner per task')
        folder = source if source.exists() else target
        if hash_file(safe_path(folder, 'STATE.md', True)) != entry['state_sha256']:
            raise PipelineError('Archive recovery state changed; refusing overwrite')
        if set(entry['outputs']) != set(OUTPUTS):
            raise PipelineError('Invalid archive recovery outputs')
        for name, digest in entry['outputs'].items():
            output = safe_path(folder, name)
            # Missing generated files can be from a previously interrupted rollback.
            if output.exists() and hash_file(output) != digest:
                raise PipelineError('Archive recovery output changed; refusing removal')
    queue = journal.get('queue')
    if queue:
        validate_schema(root, 'autopilot', queue)
        if not re.fullmatch('[a-f0-9]{32}', queue['queue_id']):
            raise PipelineError('Invalid archived queue ID')
        active = safe_path(root, 'Docs/Work/AUTOPILOT.json')
        history = safe_path(root, f"Docs/Work/AUTOPILOT-{queue['queue_id']}.json")
        for path in (active, history):
            if path.exists() and json.loads(path.read_text(encoding='utf-8-sig')) != queue:
                raise PipelineError('Archive recovery queue changed; refusing overwrite')
    for entry in reversed(entries):
        source = safe_path(root, f"Docs/Work/{entry['task_id']}")
        target = safe_path(root, f"Docs/Archive/{entry['task_id']}-r{entry['revision']}")
        if target.exists():
            target.rename(source)
        for name in OUTPUTS:
            safe_path(source, name).unlink(missing_ok=True)
    if queue:
        atomic_json(active, queue)
        history.unlink(missing_ok=True)
    safe_path(root, JOURNAL).unlink()


def recover_archive(root):
    root = Path(root).resolve()
    with lock(root, 'archive'):
        journal = json.loads(safe_path(root, JOURNAL, True).read_text(encoding='utf-8-sig'))
        _rollback(root, journal)
    return {'status': 'RECOVERED', 'reason': 'Interrupted archive rolled back; active task evidence restored'}


def archive(root, task_id, trust_path=None, *, include_members=False):
    from .state import policy_check, config_mode_is_kit
    from .runner import validate_completion
    from .source_bundle import capture_source_bundle
    from . import autopilot
    from .git_state import require_settled_checkout

    root = Path(root).resolve()
    with ExitStack() as stack:
        stack.enter_context(lock(root, 'archive'))
        if safe_path(root, JOURNAL).exists():
            raise PipelineError('Interrupted archive requires archive --recover before continuing')
        stack.enter_context(lock(root, 'autopilot'))
        config = load_config(root, kit=config_mode_is_kit(root))
        group = _group(root, config, task_id, include_members)
        for name in group:
            stack.enter_context(lock(root, f'task-{name}'))
        states = {name: read_state(root, name) for name in group}
        current, covered = {}, {}
        for name, state in states.items():
            if state['status'] != 'DONE':
                raise PipelineError(f'only a DONE task can be archived: {name}')
            result = policy_check(root, task_id=name, kit=config_mode_is_kit(root), trust_path=trust_path)
            if result['status'] != 'PASS':
                raise PipelineError('task is not currently valid for archive: ' + '; '.join(result['errors']))
            scope = scopes.task_scope(root, config, state)
            if scope['level'] == 'phase':
                summary = validate_completion(root, config, state, state['full_run'], trust_path=trust_path)
                current[name] = summary
                report = safe_path(root, f"{config['project']['report_root']}/{state['full_run']}", True)
                plan = json.loads(safe_path(report, scopes.ARTIFACT, True).read_text(encoding='utf-8-sig'))
                for member in plan['members']:
                    covered[member['task_id']] = {
                        'task_id': name, 'revision': state['revision'], 'run_id': state['full_run'],
                        'run_digest': hash_file(report / 'summary.json'),
                        'tree_digest': summary['snapshot']['tree_digest'], 'member': member}
        queue = None
        active = safe_path(root, autopilot.QUEUE)
        if active.exists():
            candidate = autopilot._load(root)
            if set(group) & {item['task_id'] for item in candidate['items']}:
                require_settled_checkout(root)
                if candidate['lease'] or autopilot._completion_result(root, candidate, trust_path)['status'] != 'COMPLETE':
                    raise PipelineError('Archive requires the referencing queue to complete all gates without a lease')
                history = safe_path(root, f"Docs/Work/AUTOPILOT-{candidate['queue_id']}.json")
                if history.exists():
                    raise PipelineError('Queue history already exists; refusing overwrite')
                queue = candidate

        # Preflight every destination and output before capturing any bytes.
        for name, state in states.items():
            target = safe_path(root, f"Docs/Archive/{name}-r{state['revision']}")
            if target.exists():
                raise PipelineError(f'archive target already exists: {target.relative_to(root).as_posix()}')
            if any(safe_path(root, f'Docs/Work/{name}/{output}').exists() for output in OUTPUTS):
                raise PipelineError('Archive output already exists; refusing to overwrite')

        prepared, entries, metadata = [], [], {}
        try:
            for name, state in states.items():
                folder = safe_path(root, f'Docs/Work/{name}', True)
                coverage = covered.get(name)
                summary = current.get(name) or validate_completion(
                    root, config, state, state['full_run'], require_current=coverage is None, trust_path=trust_path)
                digest = coverage['tree_digest'] if coverage else summary['snapshot']['tree_digest']
                bundle = capture_source_bundle(root, config, folder, digest)
                prepared.append(folder)
                data = {'schema_version': '3.0' if coverage else '2.0',
                        'task_id': name, 'revision': state['revision'], 'archived_utc': utc_now(),
                        'state_sha256': hash_file(folder / 'STATE.md'), 'source_bundle': bundle,
                        'runs': {'baseline': state['baseline_run'], 'full': state['full_run'], 'release': state['release_run']}}
                if coverage:
                    data.update(phase_coverage=coverage, completion_snapshot=summary['snapshot'])
                atomic_json(folder / 'ARCHIVE.json', data)
                metadata[name] = data
                entries.append({'task_id': name, 'revision': state['revision'],
                                'state_sha256': data['state_sha256'],
                                'outputs': {output: hash_file(folder / output) for output in OUTPUTS}})
        except BaseException:
            for folder in prepared:
                for output in OUTPUTS:
                    (folder / output).unlink(missing_ok=True)
            raise

        journal = {'schema_version': '1.0', 'entries': entries, 'queue': queue}
        try:
            atomic_json(safe_path(root, JOURNAL), journal)
        except BaseException:
            for folder in prepared:
                for output in OUTPUTS:
                    (folder / output).unlink(missing_ok=True)
            raise
        try:
            for name, state in states.items():
                target = safe_path(root, f"Docs/Archive/{name}-r{state['revision']}")
                target.parent.mkdir(parents=True, exist_ok=True)
                safe_path(root, f'Docs/Work/{name}', True).rename(target)
            if queue:
                atomic_json(history, queue)
                active.unlink()
            safe_path(root, JOURNAL).unlink()
        except BaseException as exc:
            try:
                _rollback(root, journal)
            except BaseException as recovery:
                raise PipelineError(f'Archive interrupted; archive --recover required: {recovery}') from exc
            if not isinstance(exc, OSError):
                raise
            raise PipelineError(f'archive rename failed; rolled back: {exc}') from exc
        path = f"Docs/Archive/{task_id}-r{states[task_id]['revision']}"
        return {'status': 'ARCHIVED', 'path': path, 'archived_tasks': group, **metadata[task_id]}
