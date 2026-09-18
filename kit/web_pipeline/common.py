"""Shared validation, filesystem safety, locking and content identities."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from datetime import datetime, timezone

from jsonschema import Draft202012Validator, FormatChecker


class PipelineError(Exception):
    """An expected policy or execution failure."""


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError('timezone missing')
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise PipelineError('Invalid timezone-aware timestamp') from exc


def canonical_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root, relative, must_exist=False):
    root = Path(root).resolve()
    value = str(relative).replace('\\', '/')
    part = PurePosixPath(value)
    if not value or part.is_absolute() or re.match(r'^[A-Za-z]:', value) or '..' in part.parts or ':' in value:
        raise PipelineError(f'Unsafe relative path: {relative}')
    candidate = root
    for piece in part.parts:
        candidate = candidate / piece
        if candidate.is_symlink() or (hasattr(candidate, 'is_junction') and candidate.is_junction()):
            raise PipelineError(f'Link paths are forbidden: {relative}')
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise PipelineError(f'Path escapes repository: {relative}')
    if must_exist and not resolved.exists():
        raise PipelineError(f'Missing path: {relative}')
    return resolved


def atomic_text(path, text):
    path = Path(path)
    if path.is_symlink():
        raise PipelineError('Refusing to replace a symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def process_alive(pid):
    """Conservative liveness: anything not provably gone counts as alive."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such process
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _lock_owner(path):
    try:
        owner = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return owner if isinstance(owner, dict) else {}
    except (OSError, ValueError):
        return {}


def held_locks(root, clear_stale=False):
    """List lock files with owner liveness; optionally remove those whose owner is provably gone."""
    folder = safe_path(root, '.pipeline-locks')
    locks, cleared = [], []
    for path in sorted(folder.glob('*.lock')) if folder.is_dir() else []:
        owner = _lock_owner(path)
        alive = process_alive(owner.get('pid'))
        locks.append({'name': path.stem, 'pid': owner.get('pid'), 'started_utc': owner.get('started_utc'), 'alive': alive})
        if clear_stale and not alive and _lock_owner(path) == owner:
            path.unlink(missing_ok=True)
            cleared.append(path.stem)
    return locks, cleared


@contextlib.contextmanager
def lock(root, name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', name):
        raise PipelineError('Invalid lock name')
    folder = safe_path(root, '.pipeline-locks')
    folder.mkdir(exist_ok=True)
    path = safe_path(root, f'.pipeline-locks/{name}.lock')
    try:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # A crashed run leaves its lock behind. Reclaim only when the recorded owner is provably gone.
            owner = _lock_owner(path)
            if process_alive(owner.get('pid')) or _lock_owner(path) != owner:
                raise
            path.unlink(missing_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        owner = _lock_owner(path)
        raise PipelineError(f'Another operation holds lock {name} (pid {owner.get("pid", "unknown")}, since '
                            f'{owner.get("started_utc", "unknown")}); run `locks` to inspect it') from exc
    try:
        os.write(fd, json.dumps({'pid': os.getpid(), 'started_utc': utc_now()}).encode())
        os.close(fd)
        if name != 'upgrade' and safe_path(root, '.pipeline-locks/upgrade.lock').exists():
            raise PipelineError('Engine maintenance is active; retry after it completes')
        if name != 'archive' and safe_path(root, 'Docs/Work/ARCHIVE_PENDING.json').exists():
            raise PipelineError('Interrupted archive requires archive --recover before continuing')
        yield
    finally:
        path.unlink(missing_ok=True)


def validate_schema(root, name, data):
    filename = name if name.endswith('.schema.json') else name + '.schema.json'
    # The installed engine's schemas are authoritative, not a caller-controlled alternate root.
    schema_path = Path(__file__).resolve().parent.parent / 'Schemas' / filename
    if not schema_path.is_file():
        raise PipelineError(f'Unknown schema: {name}')
    try:
        schema = json.loads(schema_path.read_text(encoding='utf-8-sig'))
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data), key=lambda e: str(e.path))
    except (ValueError, TypeError) as exc:
        raise PipelineError(f'Invalid schema {name}') from exc
    if errors:
        error = errors[0]
        raise PipelineError(f'{name}: {".".join(map(str, error.path)) or "$"}: {error.message}')
    if name == 'config' and 'boundaries' in data:
        validate_schema(root, 'boundaries', data['boundaries'])
    if name in {'state', 'autopilot'}:
        accounting = data['iteration'] if name == 'state' else data
        from .budget import additions
        additions(root, accounting)
        if accounting.get('budget_version') == 1:
            import math
            if not math.isfinite(accounting['active_seconds']):
                raise PipelineError('Active time must be finite')
        if name == 'state' and accounting.get('budget_version') == 1:
            if accounting['failed_attempts'] > accounting['attempts']:
                raise PipelineError('Failed attempts cannot exceed cumulative attempts')
            if accounting['pending_run'] and not accounting['failed_attempts']:
                raise PipelineError('Pending verification needs a reserved non-PASS attempt')


_CACHE_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', '.pipeline-locks', '.pipeline-upgrades'}


def output_exclusions(root, config):
    """Validate every configurable exclusion, not just generated_paths."""
    root = Path(root).resolve()
    report = safe_path(root, config['project']['report_root']).relative_to(root).as_posix()
    generated = [safe_path(root, item).relative_to(root).as_posix()
                 for item in config['project'].get('generated_paths', [])]
    governed = ['pipeline.config.yaml', 'web_pipeline', 'Scripts', 'Schemas', 'Docs', 'Templates',
                '.github', 'AGENTS.md', 'PIPELINE.md', 'CLAUDE.md', 'requirements.txt', 'requirements-pipeline.txt'] + list(config.get('sources', {}).values())
    for value in [report, *generated]:
        lower = value.casefold()
        if value == '.' or value.split('/')[0] in _CACHE_DIRS or any(
                lower == p.casefold() or lower.startswith(p.casefold().rstrip('/') + '/')
                or p.casefold().startswith(lower + '/') for p in governed):
            raise PipelineError('Output exclusions cannot hide governance or source documents')
    return report, generated


def validate_tracked_exclusions(root, config):
    report, generated = output_exclusions(root, config)
    try:
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError('Cannot inspect tracked output exclusions') from exc
    if result.returncode:
        if config['project']['mode'] == 'project' and config['project']['ready']:
            raise PipelineError('A ready project requires Git history to inspect output exclusions')
        return report, generated
    outputs = [item.casefold().rstrip('/') for item in [report, *generated]]
    for raw in result.stdout.split(b'\0'):
        name = raw.decode('utf-8', errors='surrogateescape')
        if not name:
            continue
        lower = name.casefold()
        hidden = any(lower == item or lower.startswith(item + '/') for item in outputs)
        hidden = hidden or bool(set(lower.split('/')[:-1]) & _CACHE_DIRS)
        if hidden and Path(name).name != '.gitkeep':
            raise PipelineError(f'Output exclusion contains tracked source: {name}')
    return report, generated


def load_config(root, kit=False):
    path = safe_path(root, 'pipeline.config.yaml', True)
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise PipelineError('Configuration must be JSON-compatible YAML') from exc
    if config.get('schema_version') != '2.0':
        raise PipelineError('Version 1 configuration requires explicit migration; approvals cannot be carried forward')
    validate_schema(root, 'config', config)
    commands = config['verification']['commands']
    ids = [entry['id'] for entry in commands]
    if len(ids) != len(set(ids)):
        raise PipelineError('Duplicate command ID')
    definitions = {entry['id']: entry for entry in commands}
    domains = set(config['risk']['domain_floor'])
    protected = config['risk']['protected_rules']
    required_protected = {'authentication','authorization_rbac','session_cookie','csrf_cors_csp','encryption','secrets_credentials','personal_data_pii','payment','wallet_balance','database_schema','destructive_migration','production_data','public_api_contract','webhook_contract','external_integration_contract','core_architecture','major_framework_sdk','infrastructure','production_deployment','dns_cdn_waf'}
    if not required_protected.issubset(protected):
        raise PipelineError('Missing protected rule coverage')
    required_domains = {'frontend','backend','database','api','authentication','authorization','security','privacy','payment','external_integration','infrastructure','deployment'}
    if domains != required_domains:
        raise PipelineError('Domain floors must cover the supported web domain vocabulary')
    if not set(config['project']['supported_domains']).issubset(domains):
        raise PipelineError('Unknown supported domain')
    output_exclusions(root, config)
    for source in config['sources'].values():
        safe_path(root, source, must_exist=not kit)
    for domain, flags in config['risk']['domain_protected_map'].items():
        if domain not in domains or not set(flags).issubset(protected):
            raise PipelineError('Invalid domain protected mapping')
    for rule in config['risk']['path_rules']:
        if not set(rule['domains']).issubset(domains) or not set(rule['protected_changes']).issubset(protected):
            raise PipelineError('Invalid path classification rule')
    for rule in protected.values():
        if not rule['roles'] or not set(rule['domains']).issubset(domains):
            raise PipelineError('Protected rule requires known domains and approver roles')
    for command in commands:
        safe_path(root, command['cwd'], must_exist=command['enabled'])
        if command['enabled'] and not command['argv']:
            raise PipelineError(f'Enabled check {command["id"]} has no argv')
        for pattern in command['artifacts']:
            safe_path(root, pattern)
    requirements = config['verification']['requirements']
    if set(requirements) != domains:
        raise PipelineError('Verification requirements must cover every domain')
    for label, checks in list(requirements.items()) + [(f'protected:{name}', rule['checks']) for name, rule in protected.items()]:
        for profile, required_ids in checks.items():
            for check_id in required_ids:
                if check_id not in definitions or profile not in definitions[check_id]['profiles']:
                    raise PipelineError(f'{label}/{profile}: {check_id} cannot execute in required profile')
    for check_id in config['verification']['policy_checks']:
        if check_id not in definitions or 'Policy' not in definitions[check_id]['profiles']:
            raise PipelineError(f'Invalid Policy check {check_id}')
    if not kit:
        if config['project']['mode'] != 'project' or not config['project']['ready']:
            raise PipelineError('Project is NOT_READY; configure sources, commands and Git baseline')
        needed = set(config['verification']['policy_checks'])
        for domain in config['project']['supported_domains']:
            for profile in ('Baseline', 'Fast', 'Full', 'Release'):
                needed.update(requirements[domain][profile])
        for check_id in needed:
            if not definitions[check_id]['enabled']:
                raise PipelineError(f'Required project command {check_id} is disabled')
        validate_tracked_exclusions(root, config)
    from .boundaries import validate_config as validate_boundaries
    validate_boundaries(root, config, kit=kit)
    from .scopes import validate_config as validate_scopes
    validate_scopes(root, config, kit=kit)
    return config


_STATE = re.compile(r'<!-- PIPELINE_STATE_BEGIN -->\s*(?:```|~~~)json\s*(.*?)\s*(?:```|~~~)\s*<!-- PIPELINE_STATE_END -->', re.S)


def read_state(root, task_id):
    if safe_path(root, 'Docs/Work/ARCHIVE_PENDING.json').exists():
        raise PipelineError('Interrupted archive requires archive --recover before reading current state')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,63}', task_id):
        raise PipelineError('Invalid TaskId')
    path = safe_path(root, f'Docs/Work/{task_id}/STATE.md', True)
    matches = list(_STATE.finditer(path.read_text(encoding='utf-8-sig')))
    if len(matches) != 1:
        raise PipelineError('STATE.md must contain exactly one state block')
    try:
        state = json.loads(matches[0].group(1))
    except ValueError as exc:
        raise PipelineError('Invalid state JSON') from exc
    validate_schema(root, 'state', state)
    if state['task_id'] != task_id:
        raise PipelineError('Task ID does not match directory')
    return state


def write_state(root, state):
    validate_schema(root, 'state', state)
    path = safe_path(root, f'Docs/Work/{state["task_id"]}/STATE.md')
    block = '<!-- PIPELINE_STATE_BEGIN -->\n~~~json\n' + json.dumps(state, ensure_ascii=False, indent=2) + '\n~~~\n<!-- PIPELINE_STATE_END -->'
    if path.exists():
        content = path.read_text(encoding='utf-8-sig')
        matches = list(_STATE.finditer(content))
        if len(matches) != 1:
            raise PipelineError('Cannot replace ambiguous state block')
        match = matches[0]
        text = content[:match.start()] + block + content[match.end():]
    else:
        text = f'# Task State: {state["task_id"]}\n\n{block}\n'
    atomic_text(path, text)


def source_fingerprint(root, config, state):
    sources = {}
    for name, relative in config['sources'].items():
        sources[name] = hash_file(safe_path(root, relative, True))
    task_files = {}
    for name in ('BRIEF.md','DOR.md','DOD.md','PLAN.md','EXEC_PLAN.md','RELEASE.md','ACCEPTANCE.json','SCOPE.json','CLARIFICATIONS.json'):
        path = safe_path(root, f'Docs/Work/{state["task_id"]}/{name}')
        if path.is_file():
            task_files[name] = hash_file(path)
    decisions = {relative: hash_file(safe_path(root, relative, True)) for relative in state.get('decision_records', [])}
    scope = {key: state.get(key) for key in ('task_id','revision','requested_tier','risk_tier','change_domains','protected_changes','migration_class','base_ref','implementer')}
    inputs = {'config':config,'sources':sources,'task_files':task_files,'decisions':decisions,'scope':scope}
    if 'planning_version' in state:
        inputs['planning_version'] = state['planning_version']
    if 'CLARIFICATIONS.json' in task_files:
        from .clarifications import source_hashes
        inputs['planning_sources'] = source_hashes(root, state)
    if 'boundaries' in config:
        from .boundaries import matches
        patterns = [p for c in config['boundaries']['contracts'] for p in c['paths']]
        inputs['boundary_contracts'] = {rel: hash_file(path) for rel, path in source_files(root, config)
                                       if matches(rel, patterns)}
    return canonical_hash(inputs)


def _files(root, excluded=()):
    root = Path(root).resolve()
    exclusions = set(excluded)
    for folder, dirs, files in os.walk(root, followlinks=False):
        relative_folder = Path(folder).relative_to(root).as_posix()
        keep = []
        for name in sorted(dirs):
            relative = name if relative_folder == '.' else relative_folder + '/' + name
            if relative in exclusions or name in _CACHE_DIRS:
                continue
            safe_path(root, relative, True)
            keep.append(name)
        dirs[:] = keep
        for name in sorted(files):
            relative = name if relative_folder == '.' else relative_folder + '/' + name
            if relative in exclusions:
                continue
            yield relative, safe_path(root, relative, True)


def _git_ignored(root):
    """Untracked paths Git ignores. Tracked files never appear here, so an ignore rule cannot hide tracked source."""
    try:
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--others', '--ignored', '--exclude-standard',
                                 '--directory'], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError('Cannot inspect Git-ignored paths') from exc
    if result.returncode:
        return set()  # No repository yet; validate_tracked_exclusions already requires Git for a ready project.
    return {raw.decode('utf-8', errors='surrogateescape').rstrip('/') for raw in result.stdout.split(b'\0') if raw}


def source_files(root, config):
    report, generated = validate_tracked_exclusions(root, config)
    # Absent in configs written before the key existed; the documented default is true.
    ignored = _git_ignored(root) if config['project'].get('respect_gitignore', True) else ()
    return list(_files(root, (report, 'Docs/Work', 'Docs/Archive', *generated, *ignored)))


def code_snapshot(root, config):
    root = Path(root).resolve()
    files = {relative: hash_file(path) for relative,path in source_files(root, config)}
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, encoding='utf-8', timeout=30)
    try:
        head = git('rev-parse', '--verify', 'HEAD')
        commit = head.stdout.strip() if head.returncode == 0 else None
        status = git('status', '--porcelain') if commit else None
        dirty = bool(status.stdout.strip()) if status and status.returncode == 0 else True
    except (OSError, subprocess.TimeoutExpired):
        commit, dirty = None, True
    return {'commit':commit,'tree_digest':canonical_hash(files),'dirty':dirty}


def artifact_manifest(root):
    return [{'path':relative,'size':path.stat().st_size,'sha256':hash_file(path)} for relative,path in _files(root)]
