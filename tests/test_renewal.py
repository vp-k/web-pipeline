"""Renewal is additive accounting, never a retry-guard or approval bypass."""
import copy
import json
import unittest
from unittest.mock import patch

from tests import test_autopilot
from web_pipeline import autopilot
from web_pipeline.budget import BudgetLimit, enforce_task, seconds_between
from web_pipeline.cli import _parser, dispatch
from web_pipeline.common import (PipelineError, atomic_json, atomic_text, load_config,
                                 read_state, source_fingerprint, write_state)
from web_pipeline.runner import run_profile
from web_pipeline.state import create_task, prepare_task, revise_task, transition

DECISION = test_autopilot.DECISION
NEW_FIELDS = ('budget_version', 'failed_attempts', 'active_seconds', 'renewals', 'pending_run')


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.f = test_autopilot.AutopilotTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root, self.task = self.f.root, self.f.f.task

    def config(self):
        return load_config(self.root)

    def start_task(self):
        self.f.f.baseline_and_start()

    def renew_task(self, **kwargs):
        return autopilot.renew(self.root, task_id=self.task, reason='User requested one more bounded work interval', **kwargs)

    def configure(self, change):
        config = self.config()
        change(config)
        atomic_json(self.root / 'pipeline.config.yaml', config)
        self.f.f.git('add', '.')
        self.f.f.git('commit', '-qm', 'isolated budget configuration')
        prepare_task(self.root, self.task)

    def test_six_successful_runs_preserve_history_without_exhausting_failures(self):
        self.start_task()
        seconds = 0
        for i in range(6):
            summary = run_profile(self.root, self.task, 'Fast', run_id=f'success-{i}')
            self.assertEqual('PASS', summary['status'])
            seconds += seconds_between(summary['started_utc'], summary['completed_utc'])
        state = read_state(self.root, self.task)
        self.assertEqual(6, state['iteration']['attempts'])
        self.assertEqual(0, state['iteration']['failed_attempts'])
        self.assertAlmostEqual(seconds, state['iteration']['active_seconds'])
        enforce_task(self.config(), state)

    def test_failed_attempt_limit_renews_and_normal_pass_recovers_sequence(self):
        self.configure(lambda c: c['iteration_limits'].update(total_attempts=1))
        self.start_task()
        atomic_text(self.root / 'app.py', 'value = 100\n')
        self.assertEqual('FAIL', run_profile(self.root, self.task, 'Fast')['status'])
        with self.assertRaisesRegex(BudgetLimit, 'failed-attempt'):
            run_profile(self.root, self.task, 'Fast')
        before = read_state(self.root, self.task)
        self.renew_task(extra_attempts=1)
        renewed = read_state(self.root, self.task)
        for key in ('attempts', 'same_failure', 'external_retries', 'started_utc', 'failed_attempts', 'active_seconds'):
            self.assertEqual(before['iteration'][key], renewed['iteration'][key])
        atomic_text(self.root / 'app.py', 'value = 4\n')
        self.assertEqual('PASS', run_profile(self.root, self.task, 'Fast')['status'])
        final = read_state(self.root, self.task)['iteration']
        self.assertEqual(2, final['attempts'])
        self.assertEqual(1, final['failed_attempts'])
        self.assertEqual(0, final['same_failure'])

    def test_old_creation_time_does_not_spend_queue_or_task_active_budget(self):
        self.f.begin()
        path = self.root / autopilot.QUEUE
        queue = json.loads(path.read_text())
        queue['started_utc'] = '2000-01-01T00:00:00Z'
        atomic_json(path, queue)
        ticket = self.f.next()
        self.assertEqual('IMPLEMENT', ticket['action'])
        state = read_state(self.root, self.task)
        state['iteration']['started_utc'] = '2000-01-01T00:00:00Z'
        write_state(self.root, state)
        enforce_task(self.config(), state)
        # Identity change must still be reconciled through lease recovery, not ignored.
        with self.assertRaises(PipelineError):
            self.f.complete(ticket)

    def test_queue_counts_lease_intervals_not_idle_time(self):
        self.f.begin()
        with patch('web_pipeline.autopilot.utc_now', return_value='2030-01-01T00:00:00Z'):
            ticket = self.f.next()
        with patch('web_pipeline.autopilot.utc_now', return_value='2030-01-01T00:00:12Z'):
            self.f.complete(ticket)
        queue = json.loads((self.root / autopilot.QUEUE).read_text())
        self.assertEqual(12, queue['active_seconds'])
        with patch('web_pipeline.autopilot.utc_now', return_value='2040-01-01T00:00:00Z'):
            self.assertIsNone(autopilot._limited(queue))
            before = (self.root / autopilot.QUEUE).read_bytes()
            self.assertEqual(12, autopilot.status(self.root)['budget']['active_seconds'])
            self.assertEqual(before, (self.root / autopilot.QUEUE).read_bytes())

    def test_queue_renew_preserves_plan_steps_and_event_prefix(self):
        self.f.begin(max_steps=1)
        self.assertEqual('PAUSED_LIMIT', self.f.next()['status'])
        before = json.loads((self.root / autopilot.QUEUE).read_text())
        result = autopilot.renew(self.root, queue_target=True, reason='User requested continuation', extra_minutes=30, extra_attempts=10)
        after = json.loads((self.root / autopilot.QUEUE).read_text())
        self.assertEqual('RENEWED', result['status'])
        for key in ('plan', 'steps', 'started_utc', 'active_seconds', 'queue_id'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(before['events'], after['events'][:-1])
        self.assertEqual('RENEW', after['events'][-1]['kind'])
        self.assertEqual('IMPLEMENT', self.f.next()['action'])

    def test_task_and_queue_time_limits_are_independent_and_additive(self):
        self.f.begin()
        queue = json.loads((self.root / autopilot.QUEUE).read_text())
        queue['active_seconds'] = 7200
        atomic_json(self.root / autopilot.QUEUE, queue)
        state = read_state(self.root, self.task)
        state['iteration']['active_seconds'] = 7200
        write_state(self.root, state)
        self.assertEqual('PAUSED_LIMIT', self.f.next()['status'])
        autopilot.renew(self.root, queue_target=True, reason='User requested queue interval', extra_minutes=30)
        self.assertEqual('PAUSED_LIMIT', self.f.next()['status'])
        self.renew_task(extra_minutes=30)
        self.assertEqual('IMPLEMENT', self.f.next()['action'])

    def test_renew_never_resets_same_failure_external_or_approval_state(self):
        state = read_state(self.root, self.task)
        state['iteration'].update(same_failure=3, external_retries=2)
        write_state(self.root, state)
        before_fingerprint = source_fingerprint(self.root, self.config(), state)
        self.renew_task(extra_minutes=30, extra_attempts=5)
        after = read_state(self.root, self.task)
        for key in ('same_failure', 'external_retries'):
            self.assertEqual(state['iteration'][key], after['iteration'][key])
        for key in ('approvals', 'exceptions', 'status', 'revision', 'fingerprint', 'baseline_run', 'full_run', 'release_run'):
            self.assertEqual(state[key], after[key])
        self.assertEqual(before_fingerprint, source_fingerprint(self.root, self.config(), after))
        with self.assertRaisesRegex(PipelineError, 'same-failure'):
            enforce_task(self.config(), after)
        after['iteration']['same_failure'] = 0  # isolated check of the other unchanged guard
        with self.assertRaisesRegex(PipelineError, 'external retry'):
            enforce_task(self.config(), after)

    def test_revise_preserves_new_usage_and_renewal_history(self):
        self.start_task()
        run_profile(self.root, self.task, 'Fast')
        self.renew_task(extra_minutes=10, extra_attempts=1)
        before = read_state(self.root, self.task)
        after = revise_task(self.root, self.task, 'User changed acceptance scope')
        self.assertEqual(before['iteration'], after['iteration'])
        self.assertEqual(before['revision'] + 1, after['revision'])

    def test_time_budget_block_does_not_spend_external_or_reset_same_failure(self):
        self.configure(lambda c: next(x for x in c['verification']['commands'] if x['id'] == 'unit').update(timeout_seconds=5))
        self.start_task()
        atomic_text(self.root / 'check.py', 'import time\ntime.sleep(2)\n')
        state = read_state(self.root, self.task)
        state['iteration'].update(same_failure=1, last_failure='a' * 64, external_retries=1)
        write_state(self.root, state)
        with patch('web_pipeline.runner.task_remaining', return_value=0.05):
            result = run_profile(self.root, self.task, 'Fast')
        self.assertEqual('BLOCKED', result['status'])
        self.assertTrue(any(c.get('blocker_kind') == 'budget' for c in result['checks']))
        final = read_state(self.root, self.task)['iteration']
        self.assertEqual(1, final['external_retries'])
        self.assertEqual(1, final['same_failure'])
        self.assertEqual('a' * 64, final['last_failure'])
        self.assertEqual(1, final['failed_attempts'])

    def test_real_spawn_failure_still_spends_external_budget(self):
        self.configure(lambda c: next(x for x in c['verification']['commands'] if x['id'] == 'unit').update(argv=['missing-budget-test-executable']))
        # Establishing Baseline with missing executable correctly fails. Restore a
        # working adapter for Baseline, then use a real spawn fault during Fast.
        self.configure(lambda c: next(x for x in c['verification']['commands'] if x['id'] == 'unit').update(argv=[__import__('sys').executable, 'check.py']))
        self.start_task()
        import web_pipeline.runner as runner
        original = runner._execute
        def missing(command, *args, **kwargs):
            return original({**command, 'argv': ['missing-budget-test-executable']}, *args, **kwargs)
        with patch('web_pipeline.runner._execute', side_effect=missing):
            result = run_profile(self.root, self.task, 'Fast')
        self.assertEqual('BLOCKED', result['status'])
        self.assertEqual(1, read_state(self.root, self.task)['iteration']['external_retries'])

    def test_legacy_task_migration_uses_retained_summaries_not_age(self):
        self.start_task()
        first = run_profile(self.root, self.task, 'Fast', run_id='legacy-pass')
        self.assertEqual('PASS', first['status'])
        atomic_text(self.root / 'app.py', 'value = 8\n')
        second = run_profile(self.root, self.task, 'Fast', run_id='legacy-fail')
        self.assertEqual('FAIL', second['status'])
        state = read_state(self.root, self.task)
        for key in NEW_FIELDS:
            state['iteration'].pop(key)
        state['iteration']['started_utc'] = '2000-01-01T00:00:00Z'
        write_state(self.root, state)
        result = self.renew_task(extra_minutes=10)
        after = read_state(self.root, self.task)['iteration']
        self.assertEqual(2, after['attempts'])
        self.assertEqual(1, after['failed_attempts'])
        self.assertEqual(state['iteration']['same_failure'], after['same_failure'])
        expected = sum(seconds_between(s['started_utc'], s['completed_utc']) for s in (first, second))
        self.assertAlmostEqual(expected, after['active_seconds'])
        self.assertEqual('retained_summaries', result['grant']['migration']['method'])
        self.assertEqual(state['iteration'], result['grant']['migration']['before'])

    def test_legacy_queue_reconstructs_claims_preserving_old_events(self):
        self.f.begin()
        self.f.complete(self.f.next())
        path = self.root / autopilot.QUEUE
        queue = json.loads(path.read_text())
        for key in ('budget_version', 'active_seconds', 'renewals'):
            queue.pop(key)
        queue['events'] = [e for e in queue['events'] if e['kind'] != 'LEASE_END']
        for number, event in enumerate(queue['events'], 1):
            event['sequence'] = number
        queue['started_utc'] = '2000-01-01T00:00:00Z'
        atomic_json(path, queue)
        self.assertEqual('PAUSED_LIMIT', self.f.next()['status'])
        autopilot.renew(self.root, queue_target=True, reason='User resumed legacy queue', extra_minutes=10)
        after = json.loads(path.read_text())
        self.assertEqual(queue['events'], after['events'][:-1])
        self.assertLess(after['active_seconds'], 120)
        self.assertEqual(queue['steps'], after['steps'])
        self.assertEqual('REVIEW', self.f.next()['action'])

    def test_invalid_grants_or_live_lease_cannot_mutate_history(self):
        path = self.root / 'Docs/Work' / self.task / 'STATE.md'
        before = path.read_bytes()
        for args in ({}, {'extra_minutes': -1}, {'extra_minutes': 1441}, {'extra_attempts': 0.5}):
            with self.assertRaises(PipelineError):
                self.renew_task(**args)
        with self.assertRaises(PipelineError):
            autopilot.renew(self.root, task_id=self.task, reason=' ', extra_minutes=1)
        self.assertEqual(before, path.read_bytes())
        self.f.begin()
        self.f.next()
        before_queue = (self.root / autopilot.QUEUE).read_bytes()
        with self.assertRaises(PipelineError):
            self.renew_task(extra_minutes=1)
        with self.assertRaises(PipelineError):
            autopilot.renew(self.root, queue_target=True, reason='Still busy', extra_minutes=1)
        self.assertEqual(before_queue, (self.root / autopilot.QUEUE).read_bytes())

    def test_cli_renew_does_not_accept_trust_and_requires_a_single_target(self):
        args = _parser().parse_args(['--root', str(self.root), 'loop', 'renew', '--task', self.task,
                                    '--reason', 'User requested resume', '--extra-attempts', '2'])
        self.assertEqual('RENEWED', dispatch(args)['status'])
        with self.assertRaises(SystemExit):
            _parser().parse_args(['loop', 'renew', '--queue', '--task', self.task, '--reason', 'x', '--extra-minutes', '1'])
        with self.assertRaises(SystemExit):
            _parser().parse_args(['loop', 'renew', '--queue', '--reason', 'x', '--extra-minutes', '1', '--trust', 'x'])

    def test_schema_rejects_partial_accounting_and_negative_usage(self):
        state = read_state(self.root, self.task)
        for invalid in (-1, float('nan'), float('inf')):
            state['iteration']['active_seconds'] = invalid
            with self.assertRaises(PipelineError):
                write_state(self.root, state)
        state['iteration']['active_seconds'] = 0
        state['iteration'].pop('failed_attempts')
        with self.assertRaises(PipelineError):
            write_state(self.root, state)

    def test_recover_accounts_abandoned_lease_and_never_resets_steps(self):
        self.f.begin()
        with patch('web_pipeline.autopilot.utc_now', return_value='2030-01-01T00:00:00Z'):
            ticket = self.f.next()
        before = autopilot.status(self.root)
        with patch('web_pipeline.autopilot.utc_now', return_value='2030-01-01T00:01:00Z'):
            autopilot.recover(self.root, ticket['token'], 'User inspected no surviving process')
        after = autopilot.status(self.root)
        self.assertEqual(60, after['budget']['active_seconds'])
        self.assertEqual(before['steps'], after['steps'])
        self.assertEqual('WAITING', self.f.next()['status'])

    def test_interrupted_run_reservation_is_settled_without_false_pass(self):
        self.start_task()
        with patch('web_pipeline.runner.atomic_json', side_effect=RuntimeError('crash before summary commit')):
            with self.assertRaises(RuntimeError):
                run_profile(self.root, self.task, 'Full', run_id='interrupted-full')
        state = read_state(self.root, self.task)
        self.assertIsNotNone(state['iteration']['pending_run'])
        with self.assertRaises(BudgetLimit):
            run_profile(self.root, self.task, 'Fast')
        self.renew_task(extra_minutes=10)
        after = read_state(self.root, self.task)
        self.assertEqual(1, after['iteration']['attempts'])
        self.assertEqual(1, after['iteration']['failed_attempts'])
        self.assertIsNone(after['iteration']['pending_run'])
        self.assertIsNone(after['full_run'])
        self.assertEqual(state['iteration']['same_failure'], after['iteration']['same_failure'])
        self.assertEqual(state['iteration']['external_retries'], after['iteration']['external_retries'])

    def test_committed_summary_recovers_budget_once_without_restoring_full(self):
        self.start_task()
        import web_pipeline.runner as runner
        original_write = runner.write_state
        def crash_after_execution(root, state):
            if state['iteration']['pending_run'] is None:
                raise RuntimeError('Crash after summary before final STATE commit')
            original_write(root, state)
        with patch('web_pipeline.runner.write_state', side_effect=crash_after_execution):
            with self.assertRaises(RuntimeError):
                run_profile(self.root, self.task, 'Full', run_id='summary-survives')
        self.assertEqual(1, read_state(self.root, self.task)['iteration']['failed_attempts'])
        result = self.renew_task(extra_minutes=5)
        first = read_state(self.root, self.task)
        self.assertEqual('retained_summary', result['grant']['settlement']['method'])
        self.assertEqual(0, first['iteration']['failed_attempts'])
        self.assertIsNone(first['full_run'])
        self.renew_task(extra_minutes=5)
        second = read_state(self.root, self.task)
        for key in ('attempts', 'failed_attempts', 'active_seconds'):
            self.assertEqual(first['iteration'][key], second['iteration'][key])
        self.assertEqual(2, len(second['iteration']['renewals']))

    def test_incomplete_legacy_task_evidence_never_becomes_zero_usage(self):
        state = read_state(self.root, self.task)
        for key in NEW_FIELDS:
            state['iteration'].pop(key)
        state['iteration'].update(attempts=2, same_failure=1, started_utc='2030-01-01T00:00:00Z')
        write_state(self.root, state)
        with patch('web_pipeline.budget.utc_now', return_value='2030-01-01T00:02:00Z'):
            result = self.renew_task(extra_minutes=5)
        after = read_state(self.root, self.task)['iteration']
        self.assertEqual('conservative_legacy_usage', result['grant']['migration']['method'])
        self.assertEqual(120, after['active_seconds'])
        self.assertEqual(2, after['failed_attempts'])
        self.assertEqual(2, after['attempts'])
        self.assertEqual(1, after['same_failure'])

    def test_protected_task_renewal_does_not_supply_design_approval(self):
        create_task(self.root, 'AUTH-002', 'Protected auth scope', 'T1', ['authentication'], base_ref='HEAD')
        state = read_state(self.root, 'AUTH-002')
        result = autopilot.renew(self.root, task_id='AUTH-002', reason='User added execution time only', extra_minutes=30)
        self.assertEqual('RENEWED', result['status'])
        after = read_state(self.root, 'AUTH-002')
        self.assertEqual('T3', after['risk_tier'])
        self.assertEqual(state['approvals'], after['approvals'])
        self.assertEqual('DRAFT', after['status'])
        with self.assertRaises(PipelineError):
            transition(self.root, 'AUTH-002', 'READY')

    def test_new_renewal_record_cannot_hide_extra_fields_or_duplicate_ids(self):
        self.renew_task(extra_minutes=1)
        state = read_state(self.root, self.task)
        record = state['iteration']['renewals'][0]
        record['reset_same_failure'] = True
        with self.assertRaises(PipelineError):
            write_state(self.root, state)
        del record['reset_same_failure']
        state['iteration']['renewals'].append(copy.deepcopy(record))
        with self.assertRaises(PipelineError):
            write_state(self.root, state)


if __name__ == '__main__':
    unittest.main()
