"""Continuous-loop tests with executed checks and test-only human signatures."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_lifecycle
from web_pipeline import autopilot
from web_pipeline.common import PipelineError, atomic_json, atomic_text, read_state
from web_pipeline.state import create_task, prepare_task, revise_task

DECISION = {'choice': 'Use the scoped implementation', 'rationale': 'It satisfies the recorded acceptance check',
            'alternatives': ['Broader refactor deferred: outside this task'], 'risks': ['Fixture only; not a production approval']}


class AutopilotTests(unittest.TestCase):
    def setUp(self):
        self.f = test_lifecycle.LifecycleTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        config = copy.deepcopy(self.f.config)
        config['verification']['policy_checks'] = []
        for profile in ('Baseline', 'Fast', 'Full', 'Release'):
            config['verification']['requirements']['backend'][profile] = ['unit']
        atomic_json(self.root / 'pipeline.config.yaml', config)
        atomic_text(self.root / 'app.py', 'value = 4\n')
        atomic_text(self.root / 'check.py', 'from app import value\nassert value == 4, value\n')
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'isolated loop fixture')
        prepare_task(self.root, self.f.task, 'fixture-implementer')
        self.plan = {'objective': 'Complete the explicitly scoped fixture tasks',
                     'tasks': [{'task_id': self.f.task, 'depends_on': []}]}

    def begin(self, **limits):
        return autopilot.start(self.root, {**self.plan, **limits})

    def next(self):
        return autopilot.advance(self.root, 'test-worker', self.f.trust)

    def complete(self, ticket, outcome='implemented', decision=None):
        return autopilot.complete(self.root, ticket['token'], outcome, decision or DECISION, self.f.trust)

    def second_task(self, depends=False):
        name = 'TASK-002'
        create_task(self.root, name, 'Second authorized task', 'T1', ['backend'], base_ref='HEAD')
        directory = self.root / 'Docs/Work' / name
        atomic_text(directory / 'BRIEF.md', '# Scope\nVerify fixture arithmetic.\n')
        atomic_text(directory / 'DOR.md', '# Ready\nCheck configured.\n')
        atomic_json(directory / 'ACCEPTANCE.json', {'criteria': [{'id': 'AC-1', 'description': 'Fixture arithmetic', 'checks': ['unit']}]})
        from tests.planning_fixture import record_fixture_planning
        record_fixture_planning(self.root, name)
        prepare_task(self.root, name, 'fixture-implementer')
        self.plan['tasks'].append({'task_id': name, 'depends_on': [self.f.task] if depends else []})
        return name

    def test_loop_status_query_exits_zero_while_a_lease_is_busy(self):
        import contextlib
        import io
        from web_pipeline import cli
        self.begin()
        self.assertEqual('IMPLEMENT', self.next()['action'])
        self.assertEqual('BUSY', autopilot.status(self.root)['status'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, cli.main(['--root', str(self.root), 'loop', 'status']))
            # next still signals "no work handed out" through its exit code
            self.assertEqual(1, cli.main(['--root', str(self.root), 'loop', 'next', '--worker', 'w', '--trust', str(self.f.trust)]))

    def test_real_failure_repair_review_approval_and_completion(self):
        self.begin()
        implement = self.next()
        self.assertEqual('IMPLEMENT', implement['action'])
        atomic_text(self.root / 'app.py', 'value = 40\n')
        self.complete(implement)
        repair = self.next()
        self.assertEqual('REPAIR', repair['action'])
        atomic_text(self.root / 'app.py', 'value = 4\n')
        self.complete(repair)
        review = self.next()
        self.assertEqual('REVIEW', review['action'])
        self.complete(review, 'reviewed')
        self.assertEqual('WAITING', self.next()['status'])
        state = read_state(self.root, self.f.task)
        self.assertEqual('REVIEW', state['status'])
        summary = json.loads((self.root / 'Reports/Pipeline' / state['full_run'] / 'summary.json').read_text())
        self.f.sign_review(summary)  # ephemeral fixture key, never a real approval
        autopilot.retry(self.root, self.f.task, 'Fixture human signature attached')
        self.assertEqual('COMPLETE', self.next()['status'])
        self.assertEqual('DONE', read_state(self.root, self.f.task)['status'])
        events = autopilot.status(self.root)['events']
        decisions = [e for e in events if e['kind'] == 'DECISION']
        self.assertEqual(3, len(decisions))
        self.assertTrue(all(e['decision']['rationale'] and e['before']['tree_digest'] and e['after']['state_hash'] for e in decisions))
        self.assertTrue(any(e.get('outcome', {}).get('status') == 'FAIL' for e in events if e['kind'] == 'EXECUTED'))

    def test_review_changes_reopen_and_invalidate_previous_full(self):
        self.begin()
        self.complete(self.next())
        review = self.next()
        old_full = read_state(self.root, self.f.task)['full_run']
        self.complete(review, 'changes_required')
        self.assertIsNone(read_state(self.root, self.f.task)['full_run'])
        repair = self.next()
        self.assertEqual('REPAIR', repair['action'])
        self.complete(repair)
        self.assertEqual('REVIEW', self.next()['action'])
        self.assertNotEqual(old_full, read_state(self.root, self.f.task)['full_run'])

    def test_blocked_approval_allows_independent_task_with_selection_reason(self):
        second = self.second_task()
        self.begin()
        self.complete(self.next())
        self.complete(self.next(), 'reviewed')
        next_task = self.next()
        self.assertEqual(second, next_task['task_id'])
        selected = [e for e in autopilot.status(self.root)['events'] if e['kind'] == 'SELECT'][-1]
        self.assertTrue(selected['reason'])
        self.assertTrue(any(self.f.task in other for other in selected['alternatives']))

    def test_dependencies_do_not_skip_missing_approval(self):
        self.second_task(depends=True)
        self.begin()
        self.complete(self.next())
        self.complete(self.next(), 'reviewed')
        result = self.next()
        self.assertEqual('WAITING', result['status'])
        self.assertTrue(any('dependencies' in t['reason'] for t in result['tasks']))

    def test_claim_prevents_duplicate_worker_and_stale_acknowledgement(self):
        self.begin()
        ticket = self.next()
        self.assertEqual('BUSY', self.next()['status'])
        with self.assertRaises(PipelineError):
            autopilot.complete(self.root, 'incorrect', 'implemented', DECISION)
        self.complete(ticket)
        with self.assertRaises(PipelineError):
            self.complete(ticket)

    def test_unfinished_integration_blocks_all_tasks_and_cannot_be_retried_away(self):
        self.second_task()
        self.begin()
        # Test-only Git operation marker, including the staged-but-not-committed case.
        marker = Path(self.f.git('rev-parse', '--absolute-git-dir')) / 'MERGE_HEAD'
        atomic_text(marker, self.f.git('rev-parse', 'HEAD') + '\n')
        from web_pipeline.state import policy_check
        gate = policy_check(self.root, gate='merge', trust_path=self.f.trust)
        self.assertEqual('FAIL', gate['status'])
        self.assertTrue(any('Unfinished Git integration' in error for error in gate['errors']))
        steps = autopilot.status(self.root)['steps']
        for _ in range(2):
            result = self.next()
            self.assertEqual(('WAITING', 'workspace'), (result['status'], result['scope']))
            self.assertIn('MERGE_HEAD', result['reason'])
            autopilot.retry(self.root, self.f.task, 'Recheck integration state')
        self.assertEqual(steps, autopilot.status(self.root)['steps'])
        self.assertIsNone(autopilot.status(self.root)['lease'])
        with self.assertRaisesRegex(PipelineError, 'Unfinished Git integration'):
            self.begin()
        marker.unlink()  # clear only the synthetic fixture marker
        self.assertEqual('IMPLEMENT', self.next()['action'])

    def test_integration_started_during_action_cannot_be_acknowledged_as_success(self):
        self.begin()
        ticket = self.next()
        marker = Path(self.f.git('rev-parse', '--absolute-git-dir')) / 'CHERRY_PICK_HEAD'
        atomic_text(marker, self.f.git('rev-parse', 'HEAD') + '\n')
        with self.assertRaisesRegex(PipelineError, 'Unfinished Git integration'):
            self.complete(ticket)
        self.assertEqual(ticket['token'], autopilot.status(self.root)['lease']['token'])
        self.complete(ticket, 'blocked', {**DECISION, 'rationale': 'Unfinished cherry-pick needs inspection'})
        self.assertEqual('WAITING', self.next()['status'])

    def test_status_is_read_only_and_recovery_does_not_reset_budget(self):
        self.begin()
        ticket = self.next()
        path = self.root / autopilot.QUEUE
        before = path.read_bytes()
        status = autopilot.status(self.root)
        self.assertEqual(before, path.read_bytes())
        autopilot.recover(self.root, ticket['token'], 'Inspected interrupted action; no product edits occurred')
        self.assertEqual(status['steps'], autopilot.status(self.root)['steps'])
        with self.assertRaises(PipelineError):
            self.complete(ticket)
        self.assertEqual('WAITING', self.next()['status'])
        autopilot.retry(self.root, self.f.task, 'No unfinished external process')
        self.assertEqual('IMPLEMENT', self.next()['action'])

    def test_queue_limit_persists_across_retries_and_start_rejected(self):
        self.begin(max_steps=1)
        result = self.next()
        self.assertEqual('PAUSED_LIMIT', result['status'])
        autopilot.retry(self.root, self.f.task, 'No new budget authorization')
        self.assertEqual('PAUSED_LIMIT', self.next()['status'])
        with self.assertRaises(PipelineError):
            self.begin(max_steps=100)

    def test_review_source_mutation_cannot_be_acknowledged(self):
        self.begin()
        self.complete(self.next())
        review = self.next()
        atomic_text(self.root / 'app.py', 'value = 4\n# changed during review\n')
        with self.assertRaisesRegex(PipelineError, 'Review changed source'):
            self.complete(review, 'reviewed')
        self.assertEqual('BUSY', self.next()['status'])

    def test_decision_requires_alternatives_and_rationale(self):
        self.begin()
        ticket = self.next()
        for decision in ({}, {**DECISION, 'alternatives': []}, {**DECISION, 'rationale': '  '}):
            with self.assertRaises(PipelineError):
                self.complete(ticket, decision=decision or {'choice': 'missing fields'})
        self.assertEqual('BUSY', self.next()['status'])

    def test_cycle_and_out_of_scope_dependencies_rejected(self):
        for dependencies in ([self.f.task], ['NOT-IN-QUEUE']):
            with self.assertRaises(PipelineError):
                autopilot.start(self.root, {'objective': 'Invalid plan', 'tasks': [{'task_id': self.f.task, 'depends_on': dependencies}]})
        self.assertFalse((self.root / autopilot.QUEUE).exists())

    def test_scope_revision_requires_explicit_reconciliation(self):
        self.begin()
        revise_task(self.root, self.f.task, 'Fixture user requested scope change')
        self.assertEqual('WAITING', self.next()['status'])
        autopilot.reconcile(self.root, self.f.task, 'User-authorized revised fixture scope')
        self.assertEqual('PLAN', self.next()['action'])

    def test_repeated_failure_limit_is_not_bypassed_by_queue(self):
        self.begin()
        ticket = self.next()
        atomic_text(self.root / 'app.py', 'value = 100\n')
        for attempt in range(3):
            self.complete(ticket)
            result = self.next()
            if attempt < 2:
                self.assertEqual('REPAIR', result['action'])
                ticket = result
        self.assertEqual('WAITING', result['status'])
        self.assertTrue(any('same-failure limit' in t['reason'] for t in result['tasks']))
        autopilot.retry(self.root, self.f.task, 'Retry cannot manufacture a reset')
        self.assertEqual('WAITING', self.next()['status'])
        self.assertEqual(3, read_state(self.root, self.f.task)['iteration']['attempts'])

    def test_elapsed_limit_and_invalid_checkpoint_fail_closed(self):
        self.begin()
        path = self.root / autopilot.QUEUE
        queue = json.loads(path.read_text())
        queue['started_utc'] = '2000-01-01T00:00:00Z'
        # Creation age no longer consumes execution budget. Exhaust the active
        # time counter instead; its hard stop and schema safety remain required.
        queue['active_seconds'] = queue['plan'].get('elapsed_minutes', 120) * 60
        atomic_json(path, queue)  # isolated fault injection
        self.assertEqual('PAUSED_LIMIT', self.next()['status'])
        queue['steps'] = -1
        atomic_json(path, queue)
        with self.assertRaises(PipelineError):
            self.next()

    def test_interrupted_machine_action_retains_lease_before_execution(self):
        self.begin()
        with patch('web_pipeline.autopilot.run_profile', side_effect=RuntimeError('Injected process interruption')):
            with self.assertRaises(RuntimeError):
                self.next()
        status = autopilot.status(self.root)
        self.assertEqual('Baseline', status['lease']['action'])
        self.assertEqual('BUSY', self.next()['status'])
        self.assertEqual(1, status['steps'])
        autopilot.recover(self.root, status['lease']['token'], 'Confirmed injected failure before verification started')
        self.assertEqual(1, autopilot.status(self.root)['steps'])


if __name__ == '__main__':
    unittest.main()
