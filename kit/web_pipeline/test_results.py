"""Conclusive, run-bound test results; a zero exit alone is not test evidence."""
from __future__ import annotations
import json
import math
from .common import PipelineError, safe_path, validate_schema


def validate_report(root, run_dir, command, *, allow_failures=False):
    policy = command.get('test_report')
    if not policy:
        return None  # Legacy command, explicitly not structured test verification.
    path = safe_path(run_dir, policy['path'], must_exist=True)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise PipelineError('Test report missing or exceeds 16 MiB')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise PipelineError('Duplicate JSON key in test report')
            result[key] = value
        return result
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise PipelineError(f'Invalid test report JSON: {exc}') from exc
    validate_schema(root, 'test-results', data)
    if data['run_id'] != run_dir.name or data['check_id'] != command['id']:
        raise PipelineError('Test report run/check identity mismatch')
    if not data['completed'] or data['errors']:
        raise PipelineError('Test report incomplete or has runner errors')
    tests = data['tests']
    if len({t['id'] for t in tests}) != len(tests):
        raise PipelineError('Duplicate test ids')
    if any(not math.isfinite(t['duration_ms']) for t in tests):
        raise PipelineError('Test durations must be finite')
    executed = [t for t in tests if t['status'] != 'skipped']
    if len(executed) < policy['min_tests']:
        raise PipelineError('Insufficient executed tests (zero/skip-only is not PASS)')
    if len(tests) - len(executed) > policy['max_skipped']:
        raise PipelineError('Test skip allowance exceeded')
    if set(policy['required_groups']) - {t['group'] for t in executed}:
        raise PipelineError('Required test groups were not executed')
    failures = sum(t['status'] in {'failed', 'error'} for t in executed)
    if failures and not allow_failures:
        raise PipelineError('Test report contains failed/error cases')
    return {'executed':len(executed), 'skipped':len(tests)-len(executed), 'failures':failures}
