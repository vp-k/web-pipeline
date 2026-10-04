"""revise carries the task's planning and decisions forward; their content, not a number, forces reanalysis (D4)."""
import json
import unittest

from tests import test_lifecycle
from web_pipeline.common import PipelineError, atomic_json, atomic_text
from web_pipeline.state import attach_record, prepare_task, revise_task


class ReviseCarryTests(unittest.TestCase):
    setUp = test_lifecycle.LifecycleTests.setUp
    git = test_lifecycle.LifecycleTests.git

    def read(self, relative):
        return json.loads((self.root / relative).read_text(encoding='utf-8'))

    def decision(self):
        """An accepted decision attached to revision 2, then prepared."""
        revise_task(self.root, self.task, 'Record the storage decision')
        relative = f'Docs/Work/{self.task}/ADR-NOTES.json'
        atomic_json(self.root / relative, {
            'id': 'ADR-NOTES', 'title': 'Notes storage', 'status': 'ACCEPTED', 'task_id': self.task,
            'revision': 2, 'scope': [], 'context': 'Notes need durable storage.',
            'decision': 'Keep notes in one table.', 'risks': 'The table grows.', 'recovery': 'Drop the table.'})
        attach_record(self.root, self.task, 'adr', relative)
        planning = f'Docs/Work/{self.task}/CLARIFICATIONS.json'
        atomic_json(self.root / planning, {**self.read(planning), 'revision': 2})
        prepare_task(self.root, self.task, 'fixture-implementer')
        return relative, planning

    def test_revise_carries_planning_and_decisions_to_the_new_revision(self):
        adr, planning = self.decision()
        state = revise_task(self.root, self.task, 'Clarify the notes limit')
        self.assertEqual(3, state['revision'])
        self.assertEqual(3, self.read(adr)['revision'])
        self.assertEqual(3, self.read(planning)['revision'])
        history = self.read(f'Docs/Work/{self.task}/REVISION_HISTORY.json')
        self.assertEqual(sorted([adr, planning]), sorted(history[-1]['carried']))
        prepared = prepare_task(self.root, self.task, 'fixture-implementer')
        self.assertEqual((3, 'DRAFT'), (prepared['revision'], prepared['status']))
        self.assertTrue(prepared['fingerprint'])

    def test_a_changed_brief_still_forces_reanalysis(self):
        revise_task(self.root, self.task, 'Broaden the brief')
        atomic_text(self.root / f'Docs/Work/{self.task}/BRIEF.md',
                    '# Fixture\n\nVerify the explicit fixture check and keep its log.\n')
        with self.assertRaisesRegex(PipelineError, 'excerpt no longer matches'):
            prepare_task(self.root, self.task, 'fixture-implementer')

    def test_a_record_owned_elsewhere_is_not_rewritten(self):
        adr, planning = self.decision()
        foreign = {**self.read(adr), 'task_id': 'OTHER-1'}
        atomic_json(self.root / adr, foreign)
        revise_task(self.root, self.task, 'Clarify the notes limit')
        self.assertEqual(foreign, self.read(adr))
        self.assertEqual([planning], self.read(f'Docs/Work/{self.task}/REVISION_HISTORY.json')[-1]['carried'])
        with self.assertRaisesRegex(PipelineError, 'stale or mismatched ADR'):
            prepare_task(self.root, self.task, 'fixture-implementer')


if __name__ == '__main__':
    unittest.main()
