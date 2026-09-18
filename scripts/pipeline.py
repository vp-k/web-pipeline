"""Relocatable plugin bootstrap; adopted projects always execute their own engine.

    python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" doctor
    python "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline.py" adopt --target <project> --preview

Inside an adopted project use `python -m web_pipeline <command>` directly.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

PLUGIN = Path(__file__).resolve().parents[1]
BUNDLE = PLUGIN / 'kit'
MANIFEST = PLUGIN / 'kit-manifest.json'


def inventory(folder: Path) -> dict[str, str]:
    result = {}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Package assets must not contain links')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            result[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def verify_bundle() -> dict:
    if BUNDLE.is_symlink() or (hasattr(BUNDLE, 'is_junction') and BUNDLE.is_junction()):
        raise ValueError('Bundled pipeline must not be a link')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8-sig'))
    if not BUNDLE.is_dir() or not manifest.get('files'):
        raise ValueError('Bundled pipeline is missing; reinstall the plugin')
    actual = inventory(BUNDLE)
    if actual != manifest['files']:
        changed = sorted(p for p in actual.keys() | manifest['files'].keys() if actual.get(p) != manifest['files'].get(p))
        raise ValueError('Bundled pipeline inventory/hash mismatch; reinstall the plugin: ' + ', '.join(changed[:10]))
    return manifest


def execute(engine: Path, arguments: list[str]) -> int:
    # cwd pins module resolution; do not import bundled modules into a project run.
    return subprocess.run([sys.executable, '-B', '-m', 'web_pipeline', *arguments], cwd=engine).returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_subparsers(dest='mode', required=True)
    modes.add_parser('doctor', help='plugin prerequisites and bundle integrity; not project readiness')
    adopt = modes.add_parser('adopt', help='copy the engine into a project without overwriting anything')
    adopt.add_argument('--target', required=True)
    adopt.add_argument('--preview', action='store_true')
    adopt.add_argument('--domains', help='comma-separated project.supported_domains')
    adopt.add_argument('--ci', action='store_true', help='also copy the optional CI workflow')
    inspect = modes.add_parser('inspect', help='read-only diagnosis of a target')
    inspect.add_argument('--target', required=True)
    upgrade = modes.add_parser('upgrade', help='managed engine preview; --apply writes with backup')
    upgrade.add_argument('--target', required=True)
    upgrade.add_argument('--baseline')
    upgrade.add_argument('--apply', action='store_true')
    restore = modes.add_parser('restore', help='restore an engine upgrade transaction')
    restore.add_argument('--target', required=True)
    restore.add_argument('--transaction', required=True)
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 11):
            raise ValueError('Python 3.11+ is required')
        if args.mode == 'doctor':
            manifest = verify_bundle()
            missing = [name for name in ('jsonschema', 'cryptography', 'PIL') if importlib.util.find_spec(name) is None]
            if shutil.which('git') is None:
                missing.append('git')
            print(json.dumps({'status': 'BLOCKED' if missing else 'PASS', 'missing': missing,
                              'engine_version': manifest['engine_version'], 'bundle_files': len(manifest['files']),
                              'python': '.'.join(map(str, sys.version_info[:3])),
                              'scope': 'plugin prerequisites and integrity, not project readiness'}))
            return 1 if missing else 0
        verify_bundle()
        target = Path(args.target).absolute()
        for parent in [target, *target.parents]:
            if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
                raise ValueError('Target must not traverse a link')
        resolved = target.resolve()
        if resolved == PLUGIN or PLUGIN in resolved.parents:
            raise ValueError('Target must be outside the installed plugin')
        forwarded = ['init' if args.mode == 'adopt' else args.mode, '--target', str(target)]
        if args.mode == 'adopt':
            if args.preview: forwarded.append('--preview')
            if args.domains: forwarded += ['--domains', args.domains]
            if args.ci: forwarded.append('--ci')
        if args.mode == 'upgrade':
            if args.baseline: forwarded += ['--baseline', str(Path(args.baseline).absolute())]
            if args.apply: forwarded.append('--apply')
        if args.mode == 'restore': forwarded += ['--transaction', args.transaction]
        return execute(BUNDLE, forwarded)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
