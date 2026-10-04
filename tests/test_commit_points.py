"""The loop offers a commit point when only DONE work is in the tree (D6); committing changes no evidence."""
import copy
import unittest

from tests import test_autopilot, test_done_history
from web_pipeline import autopilot
from web_pipeline.common import atomic_text, read_state
from web_pipeline.state import policy_check, transition


class CommitPointTests(unittest.TestCase):
    setUp = test_autopilot.AutopilotTests.setUp
    begin = test_autopilot.AutopilotTests.begin
    next = test_autopilot.AutopilotTests.next
    complete = test_autopilot.AutopilotTests.complete
    second_task = test_autopilot.AutopilotTests.second_task
    sign = test_done_history.QueueTests.sign
    review = test_done_history.QueueTests.review

    def first_done(self):
        first = self.f.task
        second = self.second_task(depends=True)
        self.begin()
        self.complete(self.next())
        self.review()
        self.sign(first)
        return first, second

    def test_the_next_ticket_after_done_offers_one_commit_point(self):
        first, second = self.first_done()
        implement = self.next()
        self.assertEqual((second, 'IMPLEMENT'), (implement['task_id'], implement['action']), implement)
        point = implement['commit_point']
        self.assertEqual([first], point['tasks'])
        self.assertIn(first, point['message'])
        self.assertIn(read_state(self.root, first)['title'], point['message'])
        # The agent commits the completed work; the pinned base_ref and the tree stay the same.
        self.f.git('add', 'app.py', 'check.py', 'Docs/Work')
        self.f.git('commit', '-qm', point['message'])
        self.assertEqual('PASS', policy_check(self.root, task_id=first, trust_path=self.f.trust)['status'])
        atomic_text(self.root / 'app.py', 'value = 4\nlabel = "notes"\n')
        self.complete(implement)
        review = self.next()
        self.assertEqual('REVIEW', review['action'], review)
        self.assertNotIn('commit_point', review)  # offered once
        self.complete(review, 'reviewed')
        self.assertEqual('WAITING', self.next()['status'])
        self.sign(second)
        result = self.next()
        self.assertEqual('COMPLETE', result['status'], result)
        self.assertEqual([second], result['commit_point']['tasks'])
        events = [event for event in autopilot.status(self.root)['events'] if event['kind'] == 'COMMIT_POINT']
        self.assertEqual([[first], [second]], [event['tasks'] for event in events])

    def test_no_commit_point_while_other_work_is_in_the_tree(self):
        first, second = self.first_done()
        transition(self.root, first, 'DONE', trust_path=self.f.trust)
        queue = autopilot._load(self.root)
        begun = copy.deepcopy(queue)
        next(item for item in begun['items'] if item['task_id'] == second)['cursor'] = 'FAST'
        self.assertIsNone(autopilot._commit_point(self.root, begun))
        self.assertEqual([first], autopilot._commit_point(self.root, queue)['tasks'])


if __name__ == '__main__':
    unittest.main()
