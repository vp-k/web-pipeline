"""Single release step: sync the version and regenerate the kit hash manifest.

The engine version in kit/web_pipeline/__init__.py is the only source of truth.

    python tools/release.py            # write plugin.json version + kit-manifest.json
    python tools/release.py --check    # fail when either is stale (used by tests/CI)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'kit'
MANIFEST = ROOT / 'kit-manifest.json'
PLUGIN = ROOT / '.claude-plugin' / 'plugin.json'


def engine_version() -> str:
    text = (KIT / 'web_pipeline' / '__init__.py').read_text(encoding='utf-8-sig')
    match = re.search(r'^__version__ = ["\'](\d+\.\d+\.\d+)["\']$', text, re.M)
    if not match:
        raise SystemExit('kit/web_pipeline/__init__.py has no __version__')
    return match[1]


def inventory() -> dict[str, str]:
    files = {}
    for path in sorted(KIT.rglob('*')):
        if path.is_symlink():
            raise SystemExit(f'kit must not contain links: {path}')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files[path.relative_to(KIT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def expected() -> tuple[str, str]:
    version = engine_version()
    manifest = json.dumps({'schema_version': 1, 'engine_version': version, 'files': inventory()}, indent=2) + '\n'
    plugin = json.loads(PLUGIN.read_text(encoding='utf-8-sig'))
    plugin['version'] = version
    return manifest, json.dumps(plugin, indent=2, ensure_ascii=False) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    manifest, plugin = expected()
    stale = [path.name for path, text in ((MANIFEST, manifest), (PLUGIN, plugin))
             if not path.is_file() or path.read_text(encoding='utf-8-sig') != text]
    if args.check:
        if stale:
            print('stale: ' + ', '.join(stale) + ' - run python tools/release.py', file=sys.stderr)
            return 1
        print(f'release files are current for {engine_version()}')
        return 0
    for path, text in ((MANIFEST, manifest), (PLUGIN, plugin)):
        path.write_text(text, encoding='utf-8', newline='\n')
    print(f'{engine_version()}: wrote {MANIFEST.name} ({len(json.loads(manifest)["files"])} files) and {PLUGIN.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
