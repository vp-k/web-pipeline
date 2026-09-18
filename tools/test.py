"""Run the engine test suite against kit/, one process per test file, in parallel.

The suite is dominated by subprocess and Git fixtures, so file-level parallelism
cuts a ~30 minute serial run to a few minutes. No third-party runner is needed.

    python tools/test.py                 # everything
    python tools/test.py test_cli lock   # files whose name contains a term
    python tools/test.py -j 1            # serial
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'kit'
TESTS = ROOT / 'tests'


def run_file(path: Path) -> tuple[str, int, float, str]:
    environment = dict(os.environ)
    # Test modules import each other as `tests.<name>` and the engine as `web_pipeline`.
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, [str(KIT), str(ROOT), environment.get('PYTHONPATH')]))
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    started = time.monotonic()
    done = subprocess.run([sys.executable, '-B', '-m', 'unittest', f'tests.{path.stem}'], cwd=ROOT, env=environment,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    return path.name, done.returncode, time.monotonic() - started, done.stderr[-6000:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('terms', nargs='*', help='only files whose name contains one of these terms')
    parser.add_argument('-j', '--jobs', type=int, default=min(8, os.cpu_count() or 2))
    args = parser.parse_args()
    files = sorted(p for p in TESTS.glob('test_*.py') if not args.terms or any(t in p.name for t in args.terms))
    if not files:
        print('no matching test files', file=sys.stderr)
        return 2
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for name, code, seconds, tail in pool.map(run_file, files):
            summary = next((line for line in reversed(tail.splitlines()) if line.startswith('Ran ')), 'Ran ?')
            print(f'{"ok  " if code == 0 else "FAIL"} {name:<36} {seconds:7.1f}s  {summary}', flush=True)
            if code:
                failed.append((name, tail))
    for name, tail in failed:
        print(f'\n===== {name} =====\n{tail}')
    print(f'\n{len(files) - len(failed)}/{len(files)} files passed')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
