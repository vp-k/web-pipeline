"""Lean feature backlog: a project's features in build order, each finished by a passing check.

The backlog lives under Docs/Work, which no check, classification or tree digest
reads, so updating it never widens a check or changes evidence. It records order
and progress; it grants no approval and replaces no review.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Any

from .common import PipelineError, atomic_json, load_config, lock, safe_path, utc_now, validate_schema

BACKLOG = 'Docs/Work/FEATURES.json'
GATE_PROFILES = ('Task', 'Full')


def _config(root: Path) -> dict[str, Any]:
    from .lean import workflow
    config = load_config(root, kit=True)
    if workflow(config) != 'lean':
        raise PipelineError('feature is for the lean workflow; a tracked project plans work as tasks and a loop queue')
    return config


def _load(root: Path) -> dict[str, Any]:
    path = safe_path(root, BACKLOG)
    if not path.is_file():
        return {'schema_version': '1.0', 'features': []}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    validate_schema(root, 'features', data)
    ids = [item['id'] for item in data['features']]
    if len(ids) != len(set(ids)):
        raise PipelineError(f'{BACKLOG}: duplicate feature IDs')
    if sum(item['status'] == 'ACTIVE' for item in data['features']) > 1:
        raise PipelineError(f'{BACKLOG}: more than one ACTIVE feature')
    return data


def _save(root: Path, data: dict[str, Any]) -> None:
    validate_schema(root, 'features', data)
    path = safe_path(root, BACKLOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, data)


def _first(features: list[dict[str, Any]], status: str) -> dict[str, Any] | None:
    return next((item for item in features if item['status'] == status), None)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """A read-only Git call; None when Git cannot run here."""
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None


def _head(root: Path) -> str | None:
    shown = _git(root, 'rev-parse', '--verify', 'HEAD')
    return shown.stdout.strip() if shown and shown.returncode == 0 else None


def _start_commit(root: Path, feature: dict[str, Any] | None) -> str | None:
    """The commit a feature started from, when Git still has it."""
    commit = feature.get('base_commit') if feature else None
    if not commit:
        return None
    known = _git(root, 'cat-file', '-e', f'{commit}^{{commit}}')
    return commit if known and known.returncode == 0 else None


def active_base(root: Path) -> str | None:
    """The commit the active feature started from, when it still exists. Check diffs against it by default,
    so commits inside a feature cannot hide earlier changes from the check or the review."""
    try:
        feature = _first(_load(root)['features'], 'ACTIVE') if safe_path(root, BACKLOG).is_file() else None
    except (PipelineError, ValueError, OSError):
        return None
    return _start_commit(root, feature)


def _covers(root: Path, base: str | None, start: str) -> bool:
    """Whether a check measured from base saw every change since start: base is start or an ancestor of it."""
    if not base or base.startswith('-'):
        return False
    if base == start:
        return True
    known = _git(root, 'merge-base', '--is-ancestor', base, start)
    return bool(known and known.returncode == 0)


def _work_hint(feature: dict[str, Any]) -> str:
    return (f"Build {feature['id']} {feature['title']!r} with its tests. Run check before the commit, "
            'get one review, then feature done and commit with the check table.')


def summary(root: Path) -> dict[str, Any] | None:
    """Read-only orientation for status; None when the project keeps no backlog."""
    if not safe_path(root, BACKLOG).is_file():
        return None
    features = _load(root)['features']
    return {'active': _first(features, 'ACTIVE'), 'next': _first(features, 'TODO'),
            'todo': sum(item['status'] == 'TODO' for item in features),
            'done': sum(item['status'] == 'DONE' for item in features)}


def add(root: Path, title: str) -> dict[str, Any]:
    title = ' '.join(title.split())
    if not title or len(title) > 200:
        raise PipelineError('feature add needs a title of 1 to 200 characters')
    _config(root)
    with lock(root, 'features'):
        data = _load(root)
        number = max((int(item['id'][2:]) for item in data['features']), default=0) + 1
        feature = {'id': f'F-{number:03d}', 'title': title, 'status': 'TODO', 'added_utc': utc_now()}
        data['features'].append(feature)
        _save(root, data)
    active = _first(data['features'], 'ACTIVE')
    hint = _work_hint(active) if active else 'Add the remaining features in build order, then run feature next.'
    return {'status': 'ADDED', 'feature': feature, 'next': hint}


def listing(root: Path) -> dict[str, Any]:
    _config(root)
    features = _load(root)['features']
    active, upcoming = _first(features, 'ACTIVE'), _first(features, 'TODO')
    if active:
        hint = _work_hint(active)
    elif upcoming:
        hint = f"Run feature next to start {upcoming['id']} {upcoming['title']!r}."
    else:
        hint = 'No feature waiting: add the planned features in build order with feature add "<title>".'
    return {'features': features, 'active': active['id'] if active else None, 'next': hint}


def start(root: Path) -> dict[str, Any]:
    """Start the first TODO feature, or return the one already active (resume)."""
    _config(root)
    with lock(root, 'features'):
        data = _load(root)
        feature = _first(data['features'], 'ACTIVE')
        if feature is None:
            feature = _first(data['features'], 'TODO')
            if feature is None:
                return {'status': 'EMPTY',
                        'next': 'No feature waiting: add the planned features in build order with feature add "<title>".'}
            feature.update(status='ACTIVE', started_utc=utc_now())
            head = _head(root)
            if head:
                feature['base_commit'] = head
            _save(root, data)
    return {'status': 'ACTIVE', 'feature': feature, 'next': _work_hint(feature)}


def _instant(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError(f'{value!r} has no time zone')
    return moment


def _latest_gate_check(root: Path, config: dict[str, Any], since: str | None) -> dict[str, Any] | None:
    """The newest Task or Full lean check that started after the feature did, or at all without a feature.
    Fast is iteration, not a gate."""
    from .lean import history
    try:
        start = _instant(since) if since else None
    except ValueError as exc:
        raise PipelineError(f'{BACKLOG}: started_utc {since!r} is not an ISO time with a zone; correct it') from exc
    for run in history(root, config):
        try:
            started = _instant(run['started_at'])
        except ValueError:
            continue  # an unreadable summary proves nothing
        if run.get('profile') in GATE_PROFILES and (start is None or started >= start):
            return run
    return None


def _gate(root: Path, config: dict[str, Any],
          feature: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """The check that finishes the work now, and why it cannot. feature done enforces this and status shows it,
    so a review never approves what feature done refuses, or the reverse."""
    from .lean import current
    run = _latest_gate_check(root, config, feature['started_utc'] if feature else None)
    if run is None:
        return None, (f"feature done needs a passing check run after {feature['id']} started: run check" if feature
                      else 'no Task or Full check has run: run check')
    since = f" since {feature['id']} started" if feature else ''
    if run['status'] != 'PASS':
        return run, f'the latest check{since} failed; finishing needs a passing check: fix it and run check again'
    if run.get('tracked_required'):
        return run, f"{run['run_id']} touches T4 paths: move that work to a tracked task (new ...) before finishing it"
    if not current(root, config, run):
        return run, (f"the code or pipeline.config.yaml changed after {run['run_id']}, or an older "
                     'engine recorded it: run check again')
    start = _start_commit(root, feature)
    if feature and start and not _covers(root, run.get('base_commit'), start):
        return run, (f"{run['run_id']} compared against a later commit than {feature['id']} started "
                     'from, so it missed earlier changes: run check without --base-ref, then feature done')
    return run, None


def commit_gate(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """For status and the review: what feature done would decide now, also in a project without a backlog."""
    feature = _first(_load(root)['features'], 'ACTIVE') if safe_path(root, BACKLOG).is_file() else None
    run, reason = _gate(root, config, feature)
    base = (run.get('base_commit') or run.get('base_ref')) if run else None
    return {'ready': reason is None, 'run_id': run['run_id'] if run else None,
            'profile': run.get('profile') if run else None, 'base': base, 'reason': reason}


def done(root: Path) -> dict[str, Any]:
    """Finish the active feature when its gate check passes, is current and needs no tracked task."""
    config = _config(root)
    with lock(root, 'features'):
        data = _load(root)
        feature = _first(data['features'], 'ACTIVE')
        if feature is None:
            raise PipelineError('no active feature: run feature next first')
        run, reason = _gate(root, config, feature)
        if reason or run is None:
            raise PipelineError(reason or 'feature done needs a passing check: run check')
        feature.update(status='DONE', done_utc=utc_now(), check_run=run['run_id'], check_profile=run['profile'])
        _save(root, data)
    upcoming = _first(data['features'], 'TODO')
    hint = (f"{feature['id']} is done: commit it with the check table and any decision, including {BACKLOG}. "
            + (f"Then run feature next for {upcoming['id']} {upcoming['title']!r}." if upcoming
               else 'The backlog is complete.'))
    return {'status': 'DONE', 'feature': feature,
            'remaining': sum(item['status'] == 'TODO' for item in data['features']), 'next': hint}
