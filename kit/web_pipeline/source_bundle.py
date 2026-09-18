"""Preserve and verify the exact source bytes identified by a Full tree digest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile

from .common import (PipelineError, atomic_json, canonical_hash, code_snapshot,
                     hash_file, safe_path, source_files)


def verify_source_bundle(folder: Path, expected_digest: str) -> dict:
    folder = Path(folder)
    manifest = json.loads(safe_path(folder, 'SOURCE_MANIFEST.json', True).read_text(encoding='utf-8-sig'))
    if not isinstance(manifest, dict) or set(manifest) != {'tree_digest', 'files'}:
        raise PipelineError('Invalid source bundle manifest')
    files = manifest.get('files', [])
    if not isinstance(files, list) or not files:
        raise PipelineError('Source bundle requires a populated file manifest')
    by_path = {}
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {'path', 'size', 'sha256'}:
            raise PipelineError('Invalid source bundle manifest entry')
        if (not isinstance(entry['path'], str) or type(entry['size']) is not int or entry['size'] < 0
                or not isinstance(entry['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', entry['sha256'])):
            raise PipelineError('Invalid source bundle file metadata')
        normalized = safe_path(folder, entry['path']).relative_to(folder.resolve()).as_posix()
        if entry['path'] != normalized:
            raise PipelineError('Source bundle paths must be canonical relative paths')
        if entry['path'] in by_path:
            raise PipelineError('Duplicate source bundle member')
        by_path[entry['path']] = entry
    digest = canonical_hash({name: entry['sha256'] for name, entry in by_path.items()})
    if digest != expected_digest or manifest.get('tree_digest') != expected_digest:
        raise PipelineError('Source bundle does not match the approved Full tree')
    with zipfile.ZipFile(safe_path(folder, 'SOURCE.zip', True)) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or set(names) != set(by_path):
            raise PipelineError('Source bundle member inventory mismatch')
        for name, entry in by_path.items():
            info = bundle.getinfo(name)
            if info.is_dir() or info.file_size != entry['size']:
                raise PipelineError(f'Source bundle size mismatch: {name}')
            hashed = hashlib.sha256()
            with bundle.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    hashed.update(block)
            if hashed.hexdigest() != entry['sha256']:
                raise PipelineError(f'Source bundle integrity mismatch: {name}')
    return manifest


def capture_source_bundle(root: Path, config: dict, folder: Path, expected_digest: str) -> dict:
    folder = Path(folder)
    outputs = [safe_path(folder, name) for name in ('SOURCE.zip', 'SOURCE_MANIFEST.json')]
    if any(path.exists() for path in outputs):
        raise PipelineError('Source bundle output already exists; refusing to overwrite')
    members = source_files(root, config)
    for relative, _ in members:
        name = Path(relative).name.casefold()
        if ((name == '.env' or name.startswith('.env.')) and name not in {'.env.example', '.env.template', '.env.sample'}) or name in {'id_rsa', 'id_ed25519'} or Path(name).suffix in {'.pem', '.key', '.p12', '.pfx', '.keystore'}:
            raise PipelineError(f'Refusing to archive a potential local credential file: {relative}; isolate credentials before verification')
    created = []
    try:
        entries = []
        with zipfile.ZipFile(outputs[0], mode='x', compression=zipfile.ZIP_DEFLATED) as bundle:
            created.append(outputs[0])
            for relative, path in members:
                digest = hashlib.sha256()
                size = 0
                with path.open('rb') as source, bundle.open(relative, mode='w') as target:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        target.write(block)
                        digest.update(block)
                        size += len(block)
                entries.append({'path': relative, 'size': size, 'sha256': digest.hexdigest()})
        manifest = {'tree_digest': expected_digest, 'files': entries}
        atomic_json(outputs[1], manifest)
        created.append(outputs[1])
        verify_source_bundle(folder, expected_digest)
        if code_snapshot(root, config)['tree_digest'] != expected_digest:
            raise PipelineError('Source changed during archive capture')
        return {'tree_digest': expected_digest,
                'zip': {'path': 'SOURCE.zip', 'sha256': hash_file(outputs[0])},
                'manifest': {'path': 'SOURCE_MANIFEST.json', 'sha256': hash_file(outputs[1])}}
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)  # only this operation's newly created files
        raise
