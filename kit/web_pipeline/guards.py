"""Facts a script can decide about a change, so a reviewer reads them instead of rediscovering them.

Every function here is read-only and advisory: it reports, the caller decides whether a
finding blocks. Git failures mean "nothing to compare", never an exception.
"""
from __future__ import annotations

import json
import posixpath
import re
import subprocess
from pathlib import Path
from typing import Any

TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|spec|e2e)/|\.(test|spec)\.[cm]?[jt]sx?$|(^|/)test_[^/]*\.py$'
                       r'|_test\.(py|go)$')
# Markers that run fewer tests than are written: skip/only/todo, x- and f- prefixes, pytest and Go skips.
SKIP_MARKER = re.compile(r'\b(?:it|test|describe|context|suite)\.(?:skip|only|todo)\b'
                         r'|\b(?:xit|xtest|xdescribe|xcontext|fit|fdescribe)\s*\('
                         r'|@pytest\.mark\.(?:skip|skipif|xfail)\b|\bpytest\.skip\(|@unittest\.skip'
                         r'|\bskipTest\(|\bt\.Skip(?:Now|f)?\(')
# it('name' / test.each([...]) / def test_x( / func TestX(. A method call such as /x/.test(s) is not a test.
TEST_DEFINITION = re.compile(r'(?<![\w.$])(?:it|test)(?:\.\w+)*\s*\(\s*[\'"`\[]'
                             r'|^\s*(?:async\s+)?def\s+test\w*\s*\(|^func\s+Test\w*\(', re.MULTILINE)
SCRIPT_RUNNERS = {'npm', 'pnpm', 'yarn', 'bun'}
# Options and words that run a script in another package or in several: not the check's own package.json.
PACKAGE_SELECTORS = {'--filter', '-F', '--workspace', '-w', '--workspaces', '-ws', '--prefix', '-C', '--dir',
                     '--cwd', '-r', '--recursive', 'workspace', 'workspaces'}


def _show(root: Path, base_ref: str, path: str) -> str | None:
    """The file at base_ref, or None when it did not exist there or Git cannot say."""
    from .policy import option_shaped
    if not base_ref or option_shaped(base_ref):
        return None
    try:
        shown = subprocess.run(['git', 'show', f'{base_ref}:./{path}'], cwd=root, capture_output=True,
                               check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return shown.stdout.decode('utf-8-sig', 'replace') if shown.returncode == 0 else None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8-sig', errors='replace')
    except OSError:
        return None


def _plural(count: int, word: str) -> str:
    return f'{count} {word}' + ('' if count == 1 else 's')


def test_changes(root: Path, base_ref: str, paths: list[str]) -> list[str]:
    """Test files deleted, tests removed and skip/only markers added since base_ref."""
    found: list[str] = []
    for path in sorted(paths):
        if not TEST_PATH.search(path):
            continue
        before = _show(root, base_ref, path)
        after = _read(root / path)
        if after is None:
            if before is not None:
                found.append(f'{path}: test file deleted')
            continue
        before = before or ''
        markers = len(SKIP_MARKER.findall(after)) - len(SKIP_MARKER.findall(before))
        removed = len(TEST_DEFINITION.findall(before)) - len(TEST_DEFINITION.findall(after))
        if markers > 0:
            found.append(f"{path}: {markers} skip/only marker{'' if markers == 1 else 's'} added")
        if removed > 0:
            found.append(f"{path}: {_plural(removed, 'test')} removed")
    return found


def script_name(argv: list[str]) -> str | None:
    """The package.json script an npm-style argv runs, or None for any other command."""
    executable = argv[0].replace('\\', '/').rsplit('/', 1)[-1].lower()
    for suffix in ('.cmd', '.exe', '.ps1'):
        if executable.endswith(suffix):
            executable = executable[:-len(suffix)]
    args = argv[1:argv.index('--')] if '--' in argv else argv[1:]  # what follows -- belongs to the script
    if executable not in SCRIPT_RUNNERS or any(arg.split('=', 1)[0] in PACKAGE_SELECTORS for arg in args):
        return None
    words = [arg for arg in args if not arg.startswith('-')]
    if not words:
        return None
    if words[0] in {'run', 'run-script'}:
        return words[1] if len(words) > 1 else None
    if words[0] in {'test', 't', 'tst'}:
        return 'test'
    if executable != 'npm' and words[0] not in {'install', 'add', 'remove', 'exec', 'dlx', 'x'}:
        return words[0]  # yarn lint, pnpm build, bun typecheck
    return None


def _scripts(text: str | None) -> dict[str, Any]:
    try:
        scripts = json.loads(text).get('scripts', {}) if text else {}
    except (ValueError, AttributeError):
        return {}
    return scripts if isinstance(scripts, dict) else {}


def script_changes(root: Path, commands: list[dict[str, Any]], base_ref: str) -> list[str]:
    """Enabled checks whose package.json script, or its pre/post hook, differs from base_ref:
    the check id stays, the command does not."""
    found: list[str] = []
    for command in commands:
        name = script_name(command['argv']) if command.get('enabled') else None
        if name is None:
            continue
        cwd = posixpath.normpath(str(command.get('cwd', '.')).replace('\\', '/')).strip('/')
        package = 'package.json' if cwd in {'', '.'} else f'{cwd}/package.json'
        before = _show(root, base_ref, package)
        if before is None:
            continue
        old, new = _scripts(before), _scripts(_read(root / package))
        for script in (name, f'pre{name}', f'post{name}'):
            if old.get(script) != new.get(script):
                found.append(f'{command["id"]}: package.json script "{script}" changed')
    return found


def command_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Checks that keep their id but run something else. A rewrite and a weakening look alike to a script."""
    old = {item['id']: item for item in before.get('verification', {}).get('commands', [])}
    found = []
    for item in after['verification']['commands']:
        prior = old.get(item['id'])
        if not prior or not item['enabled'] or not prior.get('enabled'):
            continue
        changed = [key for key in ('argv', 'cwd') if prior.get(key) != item.get(key)]
        if changed:
            found.append(f"{item['id']}: command changed ({', '.join(changed)}); confirm it still runs the same tests")
    return found


def report_loosening(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """How a check's structured test report demands less than before."""
    before, after = old.get('test_report'), new.get('test_report')
    if not before:
        return []
    if not after:
        return [f"{new['id']}: test report removed"]
    found = []
    if after['min_tests'] < before['min_tests']:
        found.append(f"{new['id']}: test report min_tests lowered from {before['min_tests']} to {after['min_tests']}")
    if after['max_skipped'] > before['max_skipped']:
        found.append(f"{new['id']}: test report max_skipped raised from {before['max_skipped']} to {after['max_skipped']}")
    dropped = sorted(set(before['required_groups']) - set(after['required_groups']))
    if dropped:
        found.append(f"{new['id']}: test report required_groups {', '.join(dropped)} dropped")
    return found


def rerun_facts(history: list[dict[str, Any]], profile: str, snapshot: dict[str, Any], config_digest: str,
                base_commit: str | None, failure: str | None) -> dict[str, Any]:
    """Compare a run with earlier ones, newest first.

    repeat: the newest earlier run of the same profile on the same tree, configuration and base.
    same_failure: runs ending with this one that failed the same way; 0 for a pass. Only a pass at
    least as wide as those failures ends the sequence, as in a tracked task: a Fast pass after a
    failed Full did not run what failed.
    """
    from .budget import covers, wider
    repeat = next(({'run_id': run['run_id'], 'status': run['status']} for run in history
                   if run.get('profile') == profile and run.get('config_digest') == config_digest
                   and run.get('base_commit') == base_commit
                   and (run.get('snapshot') or {}).get('tree_digest') == snapshot['tree_digest']), None)
    streak, last, widest = 0, None, None
    for run in [*reversed(history), {'profile': profile, 'status': 'FAIL' if failure else 'PASS',
                                      'failure_fingerprint': failure}]:
        found = run.get('failure_fingerprint')
        if found:
            streak = streak + 1 if found == last else 1
            widest = wider(widest if found == last else None, run.get('profile'))
            last = found
        elif run.get('status') == 'PASS' and covers(run.get('profile'), widest):
            streak, last, widest = 0, None, None
    return {'repeat': repeat, 'same_failure': streak if failure else 0}
