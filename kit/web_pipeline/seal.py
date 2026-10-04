"""DONE is history: record what a completed task was judged on, so later project work cannot reopen it.

The seal is not authority. The signed or recorded review still decides; the seal only fixes the moment
and the bytes that review covered. Editing the task's own records after DONE needs a revision.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .common import (TASK_FILES, PipelineError, external_inputs, hash_file, parse_time, safe_path,
                     source_fingerprint, text_digest, utc_now)


def records(root: Path, state: dict[str, Any]) -> dict[str, str]:
    """The task's own records: its folder except STATE.md, plus its decision records."""
    root = Path(root).resolve()
    folder = safe_path(root, f"Docs/Work/{state['task_id']}", True)
    found = {path.relative_to(root).as_posix(): text_digest(path)
             for path in sorted(folder.rglob('*'))
             if path.is_file() and path != folder / 'STATE.md'}
    for relative in state.get('decision_records', []):
        found[relative] = text_digest(safe_path(root, relative, True))
    return found


def _summary(root: Path, config: dict[str, Any], run_id: str) -> Path:
    return safe_path(root, f"{config['project']['report_root']}/{run_id}/summary.json", True)


def make(root: Path, config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    root = Path(root).resolve()
    full = json.loads(_summary(root, config, state['full_run']).read_text(encoding='utf-8-sig'))
    return {'fingerprint': state['fingerprint'], 'revision': state['revision'], 'sealed_utc': utc_now(),
            'records': records(root, state),
            'runs': {run: hash_file(_summary(root, config, run)) for run in (state['baseline_run'], state['full_run'])},
            'snapshot': full['snapshot'], 'external': external_inputs(root, config, state)}


def governed(config: dict[str, Any], seal: dict[str, Any]) -> dict[str, Any]:
    """The configuration as the task's approval rules stood at DONE."""
    rules = seal['external']['governance']
    view = copy.deepcopy(config)
    view['approval_policy'] = rules['approval_policy']
    protected = view.setdefault('risk', {}).setdefault('protected_rules', {})
    for change, rule in rules['protected'].items():
        protected[change] = {**protected.get(change, {}), **{k: v for k, v in rule.items() if v is not None}}
    return view


def verify(root: Path, config: dict[str, Any], state: dict[str, Any], trust_path=None) -> dict[str, Any]:
    """Validate a sealed DONE as of its completion and return its completion summary."""
    from .approval import as_of, validate_approvals
    from .runner import validate_completion, validate_run
    from .state import _review_gate, _roles, _validate_acceptance
    root = Path(root).resolve()
    seal = state['completion_seal']
    if state['status'] != 'DONE' or seal['revision'] != state['revision'] or seal['fingerprint'] != state['fingerprint']:
        raise PipelineError('completion seal does not match this task revision; revise the task')
    if parse_time(seal['sealed_utc']) > parse_time(utc_now()):
        raise PipelineError('completion seal is dated in the future')
    current = records(root, state)
    changed = [path for path, digest in seal['records'].items() if current.get(path) != digest]
    changed += [path for path in current if path not in seal['records'] and PurePosixPath(path).name in TASK_FILES]
    if changed:
        raise PipelineError(f"{', '.join(sorted(changed))} changed since DONE; "
                            "revise the task to change completed work")
    if source_fingerprint(root, config, state) != state['fingerprint']:
        raise PipelineError('task scope no longer matches its DONE record; revise the task')
    if set(seal['runs']) != {state['baseline_run'], state['full_run']}:
        raise PipelineError('completion seal does not bind this task\'s runs')
    for run, digest in seal['runs'].items():
        if hash_file(_summary(root, config, run)) != digest:
            raise PipelineError(f'run {run} changed since DONE')
    rules = governed(config, seal)
    with as_of(seal['sealed_utc']):
        validate_run(root, rules, state, state['baseline_run'], 'Baseline', require_current=False,
                     trust_path=trust_path, historical=True)
        summary = validate_completion(root, rules, state, state['full_run'], require_current=False,
                                      trust_path=trust_path, historical=True)
        if summary['snapshot'] != seal['snapshot']:
            raise PipelineError('completion seal does not match its completion run')
        _validate_acceptance(root, state['task_id'], summary)
        validate_approvals(root, rules, state, _roles(rules, state, 'design'), 'design', trust_path)
        _review_gate(root, rules, state, trust_path, seal['snapshot'])
    return summary


def verify_release(root: Path, config: dict[str, Any], state: dict[str, Any], trust_path=None) -> dict[str, Any]:
    """Release readiness recorded after DONE, judged as of the release run."""
    from .approval import as_of, validate_approvals
    from .runner import validate_run
    from .state import _roles, _validate_acceptance
    seal = state['completion_seal']
    release = seal.get('release')
    if not release or release['run'] != state['release_run']:
        raise PipelineError('release readiness is not recorded for this Release run; rerun Release')
    if hash_file(_summary(Path(root), config, release['run'])) != release['digest']:
        raise PipelineError(f"run {release['run']} changed since release readiness was recorded")
    rules = governed(config, seal)
    with as_of(release['recorded_utc']):
        summary = validate_run(root, rules, state, release['run'], 'Release', require_current=False,
                               trust_path=trust_path, historical=True)
        if summary['snapshot']['tree_digest'] != seal['snapshot']['tree_digest']:
            raise PipelineError('Release run did not verify the completed tree')
        _validate_acceptance(Path(root), state['task_id'], summary)
        validate_approvals(root, rules, state, _roles(rules, state, 'release'), 'release',
                           trust_path, seal['snapshot'], state['full_run'])
    return summary
