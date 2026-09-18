"""Read-only diagnosis and explicit, recoverable managed-engine transactions.

Receipts are local byte inventories, not signatures or approval records.
No project configuration, workflow state, budgets or product files are migrated.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from .common import PipelineError, atomic_json, hash_file, held_locks, load_config, lock, safe_path, utc_now

MANAGED = ('web_pipeline', 'Schemas', 'Scripts')
RECEIPT = '.pipeline-install.json'
HISTORY = '.pipeline-upgrades'
PROJECT_FOLDER = 'Scripts/'  # Projects keep their own check scripts here; the engine package and schemas stay exact.


def project_owned(actual, *receipts):
    """Files a project added beside managed scripts: preserved by upgrade/restore, never part of a receipt."""
    return sorted(p for p in actual if p.startswith(PROJECT_FOLDER) and not any(p in r['files'] for r in receipts))


def location(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise PipelineError('Maintenance paths must not traverse links')
    return path.resolve()


def inventory(root):
    # safe_path returns canonical paths (including expanded Windows 8.3 names).
    # Use the same root representation for relative_to, not the caller's alias.
    root = location(root)
    files = {}
    for folder in MANAGED:
        base = safe_path(root, folder, True)
        for path in sorted(base.rglob('*')):
            rel = path.relative_to(root).as_posix()
            safe_path(root, rel, True)
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                files[rel] = hash_file(path)
    return files


def version(root):
    text = safe_path(root, 'web_pipeline/__init__.py', True).read_text(encoding='utf-8-sig')
    match = re.search(r'^__version__ = ["\'](\d+\.\d+\.\d+)["\']$', text, re.M)
    if not match: raise PipelineError('Unknown engine version; explicit migration required')
    return match[1]


def receipt(root):
    return {'schema_version':1, 'engine_version':version(root), 'files':inventory(root)}


def diagnose(root):
    root = location(root)
    result = {'target':str(root), 'scope':'read-only diagnosis, not readiness or approval'}
    if not (root / 'pipeline.config.yaml').is_file():
        return {**result, 'adopted':False, 'next':'adopt --preview; preserve conflicting project files'}
    config = load_config(root, kit=True)
    commands = config['verification']['commands']
    return {**result, 'adopted':config['project']['mode'] == 'project', 'mode':config['project']['mode'], 'engine_version':version(root),
            'boundaries':'CONFIGURED' if config.get('boundaries') else 'NOT_CONFIGURED',
            'managed_receipt':safe_path(root, RECEIPT).is_file(),
            'enabled_checks':[c['id'] for c in commands if c['enabled']],
            'structured_test_checks':[c['id'] for c in commands if c['enabled'] and c.get('test_report')],
            'exit_code_only_checks':[c['id'] for c in commands if c['enabled'] and not c.get('test_report')],
            'next':'Configure real commands and boundaries; validate with the project-local engine'}


def _validate_receipt(data):
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('files'), dict) or not data['files']:
        raise PipelineError('Invalid managed-file receipt')
    if not re.fullmatch(r'2\.\d+\.\d+', str(data.get('engine_version'))):
        raise PipelineError('Unsupported receipt version')
    for rel, digest in data['files'].items():
        if (not isinstance(rel, str) or rel.split('/')[0] not in MANAGED or
                '\\' in rel or '..' in rel.split('/') or not re.fullmatch(r'[a-f0-9]{64}', str(digest))):
            raise PipelineError('Invalid managed-file inventory')


def preview(source, target, baseline=None):
    source, target = location(source), location(target)
    if source == target or source in target.parents or target in source.parents:
        raise PipelineError('Upgrade source and target must be separate trees')
    config = load_config(target, kit=True)  # New engine must understand retained configuration.
    if config['project']['mode'] != 'project':
        raise PipelineError('Upgrade target must be an adopted project, not a kit checkout')
    old_path = safe_path(target, RECEIPT)
    if old_path.is_file():
        old = json.loads(old_path.read_text(encoding='utf-8-sig'))
    elif baseline:
        old = receipt(location(baseline))
    else:
        raise PipelineError('Legacy install requires --baseline with its known original engine directory')
    _validate_receipt(old)
    new = receipt(source)
    old_version = tuple(map(int, old['engine_version'].split('.')))
    new_version = tuple(map(int, new['engine_version'].split('.')))
    if old_version < (2,6,0) or new_version[0] != 2 or new_version < old_version:
        raise PipelineError('Only compatible 2.6+ upgrades supported; no downgrade or implicit migration')
    actual = inventory(target)
    owned = project_owned(actual, old)
    collisions = sorted(set(owned) & new['files'].keys())
    if collisions: raise PipelineError('Project files collide with new engine files; rename them first: ' + ', '.join(collisions))
    conflicts = sorted(p for p in (actual.keys() | old['files'].keys()) - set(owned) if actual.get(p) != old['files'].get(p))
    if conflicts: raise PipelineError('Locally modified/missing managed files: ' + ', '.join(conflicts))
    if version(target) != old['engine_version']:
        raise PipelineError('Receipt engine version mismatch')
    changed = sorted(p for p in old['files'].keys() | new['files'].keys() if old['files'].get(p) != new['files'].get(p))
    return {'source':str(source), 'target':str(target), 'before':old, 'after':new, 'changed':changed, 'project_owned':owned,
            'preserved':'config, requirements, PIPELINE.md/CLAUDE.md, Docs, templates, CI, product, evidence, budgets and project scripts under Scripts/',
            'next':'Review retained runbooks/dependencies against new bundle; apply only when explicitly authorized'}


def _atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.upgrade-', dir=target.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _no_live_locks(target):
    locks, cleared = held_locks(target, clear_stale=True)  # Locks left by crashed runs must not block maintenance forever.
    others = [item['name'] for item in locks if item['name'] != 'upgrade' and item['name'] not in cleared]
    if others: raise PipelineError('Stop active pipeline operations before maintenance: ' + ', '.join(others))


def _idle(target):
    _no_live_locks(target)
    history = safe_path(target, HISTORY)
    for path in history.glob('*/transaction.json'):
        record = json.loads(safe_path(target, path.relative_to(target), True).read_text(encoding='utf-8-sig'))
        if record['status'] in {'PREPARED','RESTORING'}:
            raise PipelineError(f'Unfinished upgrade requires restore: {path.parent.name}')


def upgrade(source, target, baseline=None, apply=False):
    target = location(target)
    if not apply:
        plan = preview(source, target, baseline)
        return {**plan, 'mode':'PREVIEW', 'writes':False}
    with lock(target, 'upgrade'):
        _idle(target)
        plan = preview(source, target, baseline)  # Re-read immediately, never apply a stale preview.
        if not plan['changed']: return {'mode':'UNCHANGED', 'writes':False}
        transaction = uuid.uuid4().hex
        folder = safe_path(target, f'{HISTORY}/{transaction}')
        folder.mkdir(parents=True, exist_ok=False)
        receipt_path = safe_path(target, RECEIPT)
        record = {**plan, 'transaction':transaction, 'status':'PREPARED', 'started_utc':utc_now(),
                  'previous_receipt':json.loads(receipt_path.read_text(encoding='utf-8-sig')) if receipt_path.exists() else None}
        for rel in plan['changed']:
            if rel in plan['before']['files']:
                _atomic_copy(safe_path(target, rel, True), safe_path(folder, 'backup/' + rel))
        atomic_json(folder / 'transaction.json', record)  # Durable recovery before first engine mutation.
        for rel in plan['changed']:
            current = safe_path(target, rel)
            expected = plan['before']['files'].get(rel)
            if (hash_file(current) if current.is_file() else None) != expected:
                raise PipelineError('Project changed during upgrade; restore transaction ' + transaction)
            if rel in plan['after']['files']:
                origin = safe_path(source, rel, True)
                if hash_file(origin) != plan['after']['files'][rel]:
                    raise PipelineError('Upgrade source changed; restore transaction ' + transaction)
                _atomic_copy(origin, current)
            else:
                current.unlink()  # Exact validated managed file, backed up above.
        if {p:d for p, d in inventory(target).items() if p not in plan['project_owned']} != plan['after']['files']:
            raise PipelineError('Post-copy inventory mismatch; restore transaction ' + transaction)
        atomic_json(receipt_path, plan['after'])
        record.update(status='APPLIED', completed_utc=utc_now())
        atomic_json(folder / 'transaction.json', record)
        return {'mode':'APPLIED', 'transaction':transaction, 'changed':plan['changed'], 'preserved':plan['preserved'],
                'next':'Run project-local policy and new verification; old readiness is not renewed'}


def restore(target, transaction):
    target = location(target)
    if not re.fullmatch(r'[a-f0-9]{32}', transaction): raise PipelineError('Invalid transaction id')
    with lock(target, 'upgrade'):
        _no_live_locks(target)  # restore is how an unfinished upgrade gets resolved, so only locks matter here
        folder = safe_path(target, f'{HISTORY}/{transaction}', True)
        record = json.loads(safe_path(folder, 'transaction.json', True).read_text(encoding='utf-8-sig'))
        if record['target'] != str(target) or record['status'] not in {'PREPARED','APPLIED','RESTORING'}:
            raise PipelineError('Transaction cannot be restored')
        for key in ('before','after'): _validate_receipt(record[key])
        expected_changes = sorted(p for p in record['before']['files'].keys() | record['after']['files'].keys()
                                  if record['before']['files'].get(p) != record['after']['files'].get(p))
        if record['changed'] != expected_changes: raise PipelineError('Invalid transaction changes')
        actual = inventory(target)
        for rel in project_owned(actual, record['before'], record['after']): del actual[rel]
        for rel in actual.keys() | record['after']['files'].keys():
            if rel not in record['changed'] and actual.get(rel) != record['after']['files'].get(rel):
                raise PipelineError('Post-upgrade managed edit blocks restore: ' + rel)
        # Check all paths and backup hashes before touching any file.
        for rel in record['changed']:
            current = safe_path(target, rel)
            digest = hash_file(current) if current.is_file() else None
            old, new = record['before']['files'].get(rel), record['after']['files'].get(rel)
            allowed = {old, new} if record['status'] in {'PREPARED','RESTORING'} else {new}
            if digest not in allowed: raise PipelineError('Post-upgrade user edit blocks restore: ' + rel)
            if old and hash_file(safe_path(folder, 'backup/' + rel, True)) != old:
                raise PipelineError('Backup hash mismatch: ' + rel)
        receipt_path = safe_path(target, RECEIPT)
        current_receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig')) if receipt_path.exists() else None
        if current_receipt not in [record['after'],record['previous_receipt']]:
            raise PipelineError('Install receipt changed after transaction')
        record['status'] = 'RESTORING'
        atomic_json(folder / 'transaction.json', record)
        for rel in record['changed']:
            current = safe_path(target, rel)
            if rel in record['before']['files']: _atomic_copy(safe_path(folder, 'backup/' + rel, True), current)
            else: current.unlink(missing_ok=True)
        if record['previous_receipt'] is None: receipt_path.unlink(missing_ok=True)
        else: atomic_json(receipt_path, record['previous_receipt'])
        record.update(status='RESTORED', restored_utc=utc_now())
        atomic_json(folder / 'transaction.json', record)
        return {'mode':'RESTORED', 'transaction':transaction, 'backups_retained':True}
