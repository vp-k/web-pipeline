"""Lean feature backlog: a project's features in build order, each finished by a passing check.

The backlog lives under Docs/Work, which no check, classification or tree digest
reads, so updating it never widens a check or changes evidence. It records order
and progress; it grants no approval and replaces no review.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
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
            _save(root, data)
    return {'status': 'ACTIVE', 'feature': feature, 'next': _work_hint(feature)}


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _latest_gate_check(root: Path, config: dict[str, Any], since: str) -> dict[str, Any] | None:
    """The newest Task or Full lean check that started after the feature did. Fast is iteration, not a gate."""
    report = safe_path(root, config['project']['report_root'])
    latest = None
    for path in report.glob('check-*/summary.json') if report.is_dir() else []:
        try:
            run = json.loads(path.read_text(encoding='utf-8-sig'))
            started = _instant(run['started_at'])
        except (OSError, ValueError, KeyError, TypeError):
            continue  # an unreadable summary proves nothing
        if run.get('profile') in GATE_PROFILES and started >= _instant(since) and (
                latest is None or started > latest[0]):
            latest = (started, run)
    return latest[1] if latest else None


def done(root: Path) -> dict[str, Any]:
    """Finish the active feature. The newest gate check since it started must pass and need no tracked task."""
    config = _config(root)
    with lock(root, 'features'):
        data = _load(root)
        feature = _first(data['features'], 'ACTIVE')
        if feature is None:
            raise PipelineError('no active feature: run feature next first')
        run = _latest_gate_check(root, config, feature['started_utc'])
        if run is None:
            raise PipelineError(f"feature done needs a passing check run after {feature['id']} started: run check")
        if run['status'] != 'PASS':
            raise PipelineError(f"the latest check since {feature['id']} started failed; feature done needs a passing "
                                'check: fix it and run check again')
        if run.get('tracked_required'):
            raise PipelineError(f"the check for {feature['id']} touches T4 paths: move that work to a tracked task "
                                '(new ...) before finishing the feature')
        feature.update(status='DONE', done_utc=utc_now(), check_run=run['run_id'], check_profile=run['profile'])
        _save(root, data)
    upcoming = _first(data['features'], 'TODO')
    hint = (f"{feature['id']} is done: commit it with the check table and any decision, including {BACKLOG}. "
            + (f"Then run feature next for {upcoming['id']} {upcoming['title']!r}." if upcoming
               else 'The backlog is complete.'))
    return {'status': 'DONE', 'feature': feature,
            'remaining': sum(item['status'] == 'TODO' for item in data['features']), 'next': hint}
