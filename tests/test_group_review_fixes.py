"""Actual scheduling regressions for group prerequisite and peer gates."""
import json
import unittest

from tests import test_scopes
from web_pipeline import autopilot
from web_pipeline.common import atomic_text, read_state
from web_pipeline.state import transition

DECISION = test_scopes.DECISION


class GroupReviewFixes(unittest.TestCase):
    def fixture(self, external=False):
        f = test_scopes.ScopeTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.new('TASK-002', ['b'])
        f.new('PHASE-001', ['a', 'b'], [f.task, 'TASK-002'])
        tasks = [{'task_id': f.task, 'depends_on': []},
                 {'task_id': 'TASK-002', 'depends_on': []},
                 {'task_id': 'PHASE-001', 'depends_on': [f.task, 'TASK-002']}]
        if external:
            f.new('TASK-EXT', ['a'])
            tasks.insert(1, {'task_id': 'TASK-EXT', 'depends_on': []})
        plan = {'objective': 'Review group gate regressions', 'tasks': tasks,
                'implementation_groups': [{'phase': 'PHASE-001', 'order': [f.task, 'TASK-002']}]}
        return f, plan

    def test_peer_scope_block_and_repair_gates_remain_current(self):
        f, plan = self.fixture()
        autopilot.start(f.root, plan)
        ticket = autopilot.advance(f.root)
        self.assertEqual(f.task, ticket['task_id'])
        before = {name: read_state(f.root, name)['baseline_run'] for name in (f.task, 'TASK-002')}
        atomic_text(f.root / 'a.py', 'value = 1\n# Initial implementation.\n')
        autopilot.complete(f.root, ticket['token'], 'implemented', DECISION)
        doc = f.root / f'Docs/Work/{f.task}/DOR.md'
        original = doc.read_text(encoding='utf-8')
        atomic_text(doc, original + '\nChanged provider requirements.\n')
        self.assertEqual('WAITING', autopilot.advance(f.root)['status'])
        self.assertIsNone(autopilot.status(f.root)['lease'])
        atomic_text(doc, original)
        transition(f.root, f.task, 'BLOCKED')
        self.assertEqual('WAITING', autopilot.advance(f.root)['status'])
        transition(f.root, f.task, 'IN_PROGRESS')
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', 'TASK-002'), (ticket['action'], ticket['task_id']))
        self.assertEqual(before, {name: read_state(f.root, name)['baseline_run'] for name in before})
        autopilot.complete(f.root, ticket['token'], 'implemented', DECISION)
        atomic_text(f.root / 'a.py', 'value = 9\n')
        ticket = autopilot.advance(f.root)
        self.assertEqual(('REPAIR', f.task), (ticket['action'], ticket['task_id']))
        autopilot.recover(f.root, ticket['token'], 'Inspect repair after another member became blocked')
        transition(f.root, 'TASK-002', 'BLOCKED')
        autopilot.retry(f.root, f.task, 'Retry inspected repair')
        self.assertEqual('WAITING', autopilot.advance(f.root)['status'])
        transition(f.root, 'TASK-002', 'IN_PROGRESS')
        ticket = autopilot.advance(f.root)
        self.assertEqual(('REPAIR', f.task), (ticket['action'], ticket['task_id']))

    def test_external_prerequisite_finishes_before_any_group_baseline(self):
        f, plan = self.fixture(external=True)
        plan['tasks'][2]['depends_on'] = ['TASK-EXT']
        autopilot.start(f.root, plan)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', 'TASK-EXT'), (ticket['action'], ticket['task_id']))
        self.assertIsNone(read_state(f.root, f.task)['baseline_run'])
        self.assertIsNone(read_state(f.root, 'TASK-002')['baseline_run'])
        atomic_text(f.root / 'a.py', 'value = 1\n# External prerequisite.\n')
        autopilot.complete(f.root, ticket['token'], 'implemented', DECISION)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('REVIEW', 'TASK-EXT'), (ticket['action'], ticket['task_id']))
        autopilot.complete(f.root, ticket['token'], 'reviewed', DECISION)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', f.task), (ticket['action'], ticket['task_id']))
        self.assertEqual('DONE', read_state(f.root, 'TASK-EXT')['status'])
        snapshots = []
        for name in (f.task, 'TASK-002'):
            run_id = read_state(f.root, name)['baseline_run']
            snapshots.append(json.loads((f.root / f'Reports/Pipeline/{run_id}/summary.json').read_text())['snapshot']['tree_digest'])
        self.assertEqual(*snapshots)

    def test_unrelated_task_cannot_interleave_group_setup_or_implementation(self):
        f, plan = self.fixture(external=True)
        autopilot.start(f.root, plan)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', f.task), (ticket['action'], ticket['task_id']))
        self.assertIsNone(read_state(f.root, 'TASK-EXT')['baseline_run'])
        atomic_text(f.root / 'a.py', 'value = 1\n# Group implementation.\n')
        autopilot.complete(f.root, ticket['token'], 'implemented', DECISION)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', 'TASK-002'), (ticket['action'], ticket['task_id']))
        self.assertIsNone(read_state(f.root, 'TASK-EXT')['baseline_run'])


if __name__ == '__main__':
    unittest.main()
