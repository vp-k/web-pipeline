"""Relocatable bootstrap; adopted projects always execute their own engine."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]
BUNDLE = SKILL / 'assets' / 'pipeline'


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
    manifest = json.loads((SKILL / 'assets' / 'pipeline-manifest.json').read_text(encoding='utf-8'))
    if not BUNDLE.is_dir() or not manifest.get('files') or inventory(BUNDLE) != manifest['files']:
        raise ValueError('Bundled pipeline inventory/hash mismatch; rebuild or reinstall the package')
    return manifest


def execute(engine: Path, arguments: list[str]) -> int:
    # cwd pins module resolution; do not import bundled modules into a project run.
    return subprocess.run([sys.executable, '-B', '-m', 'web_pipeline', *arguments], cwd=engine).returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    modes.add_parser('doctor')
    adopt = modes.add_parser('adopt')
    adopt.add_argument('--target', required=True)
    adopt.add_argument('--preview', action='store_true')
    inspect = modes.add_parser('inspect')
    inspect.add_argument('--target', required=True)
    upgrade = modes.add_parser('upgrade')
    upgrade.add_argument('--target', required=True)
    upgrade.add_argument('--baseline')
    upgrade.add_argument('--apply', action='store_true')
    restore = modes.add_parser('restore')
    restore.add_argument('--target', required=True)
    restore.add_argument('--transaction', required=True)
    project = modes.add_parser('project')
    project.add_argument('--root', required=True)
    project.add_argument('arguments', nargs=argparse.REMAINDER)
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
                              'scope': 'package prerequisites and integrity, not project readiness'}))
            return 1 if missing else 0
        if args.mode in {'adopt','inspect','upgrade','restore'}:
            verify_bundle()
            target = Path(args.target).absolute()
            for parent in [target, *target.parents]:
                if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
                    raise ValueError('Adoption target must not traverse a link')
            resolved = target.resolve()
            if resolved == SKILL or SKILL in resolved.parents:
                raise ValueError('Adoption target must be outside the installed skill')
            forwarded = ['init' if args.mode == 'adopt' else args.mode, '--target', str(target)]
            if args.mode == 'adopt' and args.preview: forwarded.append('--preview')
            if args.mode == 'upgrade':
                if args.baseline: forwarded += ['--baseline', str(Path(args.baseline).absolute())]
                if args.apply: forwarded.append('--apply')
            if args.mode == 'restore': forwarded += ['--transaction', args.transaction]
            return execute(BUNDLE, forwarded)
        root = Path(args.root).resolve(strict=True)
        if root == SKILL or SKILL in root.parents:
            raise ValueError('Project operations cannot mutate installed skill assets')
        for relative in ('pipeline.config.yaml', 'web_pipeline/__main__.py', 'web_pipeline/cli.py'):
            if not (root / relative).is_file():
                raise ValueError('Target has no complete project-local pipeline; adopt explicitly first')
        forwarded = args.arguments
        if forwarded[:1] == ['--']:
            forwarded = forwarded[1:]
        if not forwarded or forwarded[0] in {'init','upgrade','restore','inspect'}:
            raise ValueError('Use project with a project command; use adopt for installation')
        return execute(root, ['--root', str(root), *forwarded])
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
