"""Recover real retained Task/Phase reports after a simulated interrupted state write."""
import copy
import unittest

from tests import test_scopes as fixtures
from web_pipeline.budget import seconds_between, settle_interrupted
from web_pipeline.common import atomic_text, read_state, write_state
from web_pipeline.runner import run_profile
from web_pipeline.state import policy_check


class ScopedRecoveryTests(unittest.TestCase):
    def test_incomplete_phase_gates_cannot_cover_historical_member(self):
        fixture = fixtures.ScopeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.start()
        fixture.finish()
        atomic_text(fixture.root / 'a.py', 'value = 1\n# combined phase source\n')
        fixture.new('PHASE-001', ['a'], [fixture.task])
        fixture.start('PHASE-001')
        fixture.finish('PHASE-001')
        self.assertEqual('PASS', policy_check(fixture.root, task_id=fixture.task)['status'])
        phase = read_state(fixture.root, 'PHASE-001')
        phase['baseline_run'] = None  # adversarial metadata corruption in isolated fixture
        write_state(fixture.root, phase)
        self.assertEqual('FAIL', policy_check(fixture.root, task_id=fixture.task)['status'])

    def test_retained_task_and_phase_runs_settle_their_reserved_budget(self):
        fixture = fixtures.ScopeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.start()
        task = fixture.finish()
        fixture.new('PHASE-001', ['a', 'b'], [fixture.task])
        fixture.start('PHASE-001')
        phase = run_profile(fixture.root, 'PHASE-001', 'Phase')
        self.assertEqual('PASS', phase['status'], phase)
        for summary in [task, phase]:
            with self.subTest(profile=summary['profile']):
                state = copy.deepcopy(read_state(fixture.root, summary['task_id']))
                seconds = state['iteration']['active_seconds']
                # Model a crash after the real summary was persisted but before
                # its pending reservation was settled. No live task is mutated.
                state['iteration']['active_seconds'] -= seconds_between(summary['started_utc'], summary['completed_utc'])
                state['iteration']['failed_attempts'] += 1
                state['iteration']['pending_run'] = {'run_id': summary['run_id'], 'started_utc': summary['started_utc']}
                result = settle_interrupted(fixture.root, fixture.config, state)
                self.assertEqual('retained_summary', result['method'])
                self.assertIsNone(state['iteration']['pending_run'])
                self.assertEqual(0, state['iteration']['failed_attempts'])
                self.assertAlmostEqual(seconds, state['iteration']['active_seconds'])
