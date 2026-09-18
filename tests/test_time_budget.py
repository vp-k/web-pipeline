"""Advisory cumulative time never changes check outcomes or protected gates."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_autopilot
from web_pipeline import autopilot
from web_pipeline.budget import (BudgetLimit, enforce_task, finish_run, grant,
                                new_accounting, time_warnings)
from web_pipeline.common import (PipelineError, atomic_json, atomic_text, load_config,
                                 read_state, validate_schema, write_state)
from web_pipeline.runner import run_profile, validate_run
from web_pipeline.state import prepare_task

ROOT = Path(__file__).resolve().parents[1] / 'kit'


class TimeBudgetAccountingTests(unittest.TestCase):
    def test_new_default_and_legacy_task_enforcement(self):
        config = load_config(ROOT, kit=True)
        self.assertEqual('warn', config['iteration_limits']['time_budget_mode'])
        state = {'iteration': {**new_accounting(task=True), 'active_seconds': 7200}}
        enforce_task(config, state)
        self.assertTrue(time_warnings(config['iteration_limits'], state['iteration'], 'Task'))
        for mode in ('enforce', None):
            legacy = copy.deepcopy(config)
            if mode is None:
                legacy['iteration_limits'].pop('time_budget_mode')
            else:
                legacy['iteration_limits']['time_budget_mode'] = mode
            with self.subTest(mode=mode), self.assertRaisesRegex(BudgetLimit, 'active-time'):
                enforce_task(legacy, state)

    def test_warning_respects_additive_grants_and_does_not_mutate_usage(self):
        limits = {'time_budget_mode': 'warn', 'elapsed_minutes': 1}
        accounting = {**new_accounting(), 'active_seconds': 60}
        self.assertTrue(time_warnings(limits, accounting, 'Queue'))
        accounting['renewals'].append(grant(ROOT, 'Fixture user extension', 1, 0))
        before = copy.deepcopy(accounting)
        self.assertEqual([], time_warnings(limits, accounting, 'Queue', 59))
        self.assertTrue(time_warnings(limits, accounting, 'Queue', 60))
        self.assertEqual(before, accounting)

    def test_warn_keeps_failure_and_pending_guards(self):
        config = load_config(ROOT, kit=True)
        for fields, message in [({'failed_attempts': 5}, 'failed-attempt'),
                                ({'same_failure': 3}, 'same-failure'),
                                ({'external_retries': 2}, 'external retry'),
                                ({'pending_run': {'run_id': 'unknown'}}, 'Interrupted')]:
            state = {'iteration': {**new_accounting(task=True), 'active_seconds': 8000, **fields}}
            with self.subTest(fields=fields), self.assertRaisesRegex(PipelineError, message):
                enforce_task(config, state)

    def test_only_conclusive_budget_only_summary_refunds_reservation(self):
        budget = {'status': 'BLOCKED', 'blocker_kind': 'budget'}
        scenarios = [([budget], 'BLOCKED', 0),
                     ([{'status': 'PASS'}, budget], 'BLOCKED', 0),
                     ([{'status': 'NOT_APPLICABLE'}, budget], 'BLOCKED', 0),
                     ([{'status': 'FAIL'}, budget], 'FAIL', 1),
                     ([{'status': 'BLOCKED', 'blocker_kind': 'external'}, budget], 'BLOCKED', 1),
                     ([{'status': 'NOT_RUN'}, budget], 'BLOCKED', 1),
                     ([{'status': 'INCONCLUSIVE'}, budget], 'BLOCKED', 1),
                     ([], 'BLOCKED', 1), ([budget], 'FAIL', 1)]
        for checks, status, charge in scenarios:
            with self.subTest(checks=checks, status=status):
                iteration = {**new_accounting(task=True), 'failed_attempts': 3,
                             'pending_run': {'run_id': 'run-001'}}
                finish_run(iteration, {'run_id': 'run-001', 'started_utc': '2030-01-01T00:00:00Z',
                                      'completed_utc': '2030-01-01T00:00:02Z',
                                      'status': status, 'checks': checks})
                self.assertEqual(2 + charge, iteration['failed_attempts'])
                self.assertEqual(2, iteration['active_seconds'])
                self.assertIsNone(iteration['pending_run'])

    def test_schemas_reject_invalid_modes_and_legacy_queue_stays_enforced(self):
        for invalid in ('off', '', None, True, 0):
            config = load_config(ROOT, kit=True)
            config['iteration_limits']['time_budget_mode'] = invalid
            plan = {'objective': 'Fixture', 'time_budget_mode': invalid,
                    'tasks': [{'task_id': 'TASK-001', 'depends_on': []}]}
            for schema, data in [('config', config), ('autopilot-plan', plan)]:
                with self.subTest(schema=schema, invalid=invalid), self.assertRaises(PipelineError):
                    validate_schema(ROOT, schema, data)
        queue = {**new_accounting(), 'active_seconds': 7200, 'steps': 0, 'plan': {}}
        self.assertIn('active-time', autopilot._limited(queue))
        queue['plan']['time_budget_mode'] = 'warn'
        self.assertIsNone(autopilot._limited(queue))
        queue['steps'] = 100
        self.assertIn('step limit', autopilot._limited(queue))


class TimeBudgetExecutionTests(unittest.TestCase):
    def setUp(self):
        self.f = test_autopilot.AutopilotTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root, self.task = self.f.root, self.f.f.task
        config = load_config(self.root)
        config['iteration_limits']['time_budget_mode'] = 'warn'
        next(c for c in config['verification']['commands'] if c['id'] == 'unit')['timeout_seconds'] = 1
        atomic_json(self.root / 'pipeline.config.yaml', config)
        self.f.f.git('add', '.')
        self.f.f.git('commit', '-qm', 'isolated advisory policy fixture')
        prepare_task(self.root, self.task)

    def exceed_task_time(self):
        state = read_state(self.root, self.task)
        state['iteration']['active_seconds'] = 7200
        write_state(self.root, state)

    def test_real_verification_continues_past_threshold_with_valid_evidence(self):
        self.f.f.baseline_and_start()
        self.exceed_task_time()
        # Any cumulative deadline lookup would incorrectly truncate this command.
        with patch('web_pipeline.runner.task_remaining', side_effect=AssertionError('warn used hard deadline')):
            result = run_profile(self.root, self.task, 'Full')
        self.assertEqual('PASS', result['status'], result)
        self.assertTrue(result['warnings'])
        state = read_state(self.root, self.task)
        self.assertEqual(0, state['iteration']['failed_attempts'])
        self.assertGreater(state['iteration']['active_seconds'], 7200)
        validate_run(self.root, load_config(self.root), state, result['run_id'], 'Full')

    def test_warning_emitted_when_successful_run_crosses_threshold(self):
        self.f.f.baseline_and_start()
        state = read_state(self.root, self.task)
        state['iteration']['active_seconds'] = 7199.99
        write_state(self.root, state)
        result = run_profile(self.root, self.task, 'Fast')
        self.assertEqual('PASS', result['status'])
        self.assertTrue(result['warnings'])
        self.assertGreater(read_state(self.root, self.task)['iteration']['active_seconds'], 7200)

    def test_real_command_timeout_still_fails_after_advisory_threshold(self):
        self.f.f.baseline_and_start()
        self.exceed_task_time()
        atomic_text(self.root / 'check.py', 'import time\ntime.sleep(10)\n')
        result = run_profile(self.root, self.task, 'Full')
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(result['warnings'])
        unit = next(c for c in result['checks'] if c['id'] == 'unit')
        self.assertEqual('timeout', unit['reason'])
        self.assertNotIn('blocker_kind', unit)
        state = read_state(self.root, self.task)
        self.assertEqual(1, state['iteration']['failed_attempts'])
        self.assertEqual(1, state['iteration']['same_failure'])
        self.assertIsNone(state['full_run'])

    def test_queue_inherits_warn_and_returns_warnings_without_hiding_lease(self):
        original_plan = copy.deepcopy(self.f.plan)
        self.f.begin()
        path = self.root / autopilot.QUEUE
        queue = json.loads(path.read_text())
        self.assertEqual('warn', queue['plan']['time_budget_mode'])
        self.assertEqual(original_plan, self.f.plan)
        queue['active_seconds'] = 7200
        atomic_json(path, queue)
        self.exceed_task_time()
        before = path.read_bytes()
        status = autopilot.status(self.root)
        self.assertEqual('IDLE', status['status'])
        self.assertEqual(2, len(status['warnings']))
        self.assertEqual(before, path.read_bytes())
        ticket = self.f.next()
        self.assertEqual('IMPLEMENT', ticket['action'])
        self.assertEqual(2, len(ticket['warnings']))
        busy = self.f.next()
        self.assertEqual('BUSY', busy['status'])
        self.assertTrue(busy['warnings'])
        self.f.complete(ticket)

    def test_explicit_queue_enforce_overrides_warn_project(self):
        self.f.begin(time_budget_mode='enforce')
        path = self.root / autopilot.QUEUE
        queue = json.loads(path.read_text())
        queue['active_seconds'] = 7200
        atomic_json(path, queue)
        self.assertEqual('PAUSED_LIMIT', self.f.next()['status'])
        self.assertEqual('PAUSED_LIMIT', autopilot.status(self.root)['status'])

    def test_busy_diagnostics_remain_available_during_readiness_repairs(self):
        self.f.begin()
        ticket = self.f.next()
        config = load_config(self.root)
        config['project']['ready'] = False
        atomic_json(self.root / 'pipeline.config.yaml', config)
        before = (self.root / autopilot.QUEUE).read_bytes()
        status = autopilot.status(self.root)
        self.assertEqual('BUSY', status['status'])
        self.assertEqual(ticket['token'], status['lease']['token'])
        self.assertEqual('BUSY', self.f.next()['status'])
        self.assertEqual(before, (self.root / autopilot.QUEUE).read_bytes())
        # Visibility of the lease must not permit new execution in NOT_READY.
        with self.assertRaisesRegex(PipelineError, 'NOT_READY'):
            self.f.complete(ticket)

    def test_budget_only_interrupted_summary_recovers_without_false_pass(self):
        config = load_config(self.root)
        config['iteration_limits']['time_budget_mode'] = 'enforce'
        atomic_json(self.root / 'pipeline.config.yaml', config)
        self.f.f.git('add', '.')
        self.f.f.git('commit', '-qm', 'isolated enforced recovery fixture')
        prepare_task(self.root, self.task)
        self.f.f.baseline_and_start()
        import web_pipeline.runner as runner
        original_write = runner.write_state
        def crash_after_summary(root, state):
            if state['iteration']['pending_run'] is None:
                raise RuntimeError('Crash after budget summary')
            original_write(root, state)
        with patch('web_pipeline.runner.task_remaining', return_value=0), \
                patch('web_pipeline.runner.write_state', side_effect=crash_after_summary):
            with self.assertRaisesRegex(RuntimeError, 'budget summary'):
                run_profile(self.root, self.task, 'Full', run_id='budget-recovery')
        state = read_state(self.root, self.task)
        self.assertEqual(1, state['iteration']['failed_attempts'])
        result = json.loads((self.root / 'Reports/Pipeline/budget-recovery/summary.json').read_text())
        self.assertEqual('BLOCKED', result['status'])
        autopilot.renew(self.root, task_id=self.task, reason='Fixture user resumes', extra_minutes=1)
        state = read_state(self.root, self.task)
        self.assertEqual(0, state['iteration']['failed_attempts'])
        self.assertEqual(1, state['iteration']['attempts'])
        self.assertIsNone(state['full_run'])
        autopilot.renew(self.root, task_id=self.task, reason='Fixture second grant', extra_minutes=1)
        self.assertEqual(0, read_state(self.root, self.task)['iteration']['failed_attempts'])


if __name__ == '__main__':
    unittest.main()
