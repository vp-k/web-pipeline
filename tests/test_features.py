"""Lean feature backlog: plan a whole project as features, finish each with a passing check (D1)."""
import json
import unittest

from tests import test_lean
from web_pipeline import cli
from web_pipeline.common import PipelineError


class FeatureTests(unittest.TestCase):
    setUp = test_lean.LeanTests.setUp
    adopted = test_lean.LeanTests.adopted
    save = test_lean.LeanTests.save
    command = test_lean.LeanTests.command
    run_check = test_lean.LeanTests.run_check

    def feature(self, root, *args):
        return cli.dispatch(cli._parser().parse_args(['--root', str(root), 'feature', *args]))

    def project(self):
        root, config = self.adopted()
        self.command(config, 'unit-ok', 'ok.py'); self.save(root, config)
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'checks')
        return root, config

    def test_backlog_keeps_order_and_status_points_to_the_next_feature(self):
        root, _ = self.project()
        self.assertNotIn('features', cli._status(root))
        self.assertEqual('F-001', self.feature(root, 'add', 'Sign-up form')['feature']['id'])
        self.assertEqual('F-002', self.feature(root, 'add', 'Search')['feature']['id'])
        status = cli._status(root)
        self.assertEqual((None, 'F-001', 2), (status['features']['active'], status['features']['next']['id'],
                                               status['features']['todo']))
        self.assertIn('feature next', status['next'])
        started = self.feature(root, 'next')
        self.assertEqual(('ACTIVE', 'F-001', 'Sign-up form'), (started['status'], started['feature']['id'],
                                                              started['feature']['title']))
        self.assertEqual(started['feature'], self.feature(root, 'next')['feature'])  # resuming keeps the same one
        status = cli._status(root)
        self.assertEqual('F-001', status['features']['active']['id'])
        self.assertIn('F-001', status['next'])
        listed = self.feature(root, 'list')
        self.assertEqual([('F-001', 'ACTIVE'), ('F-002', 'TODO')],
                         [(item['id'], item['status']) for item in listed['features']])
        # The backlog is pipeline bookkeeping, not a product change: it never widens a check.
        self.assertNotIn('Docs/Work/FEATURES.json', self.run_check(root)['changed_paths'])

    def test_done_needs_a_passing_check_run_after_the_feature_started(self):
        root, config = self.project()
        self.feature(root, 'add', 'Sign-up form'); self.feature(root, 'add', 'Search')
        self.assertEqual('PASS', self.run_check(root)['status'])
        self.feature(root, 'next')
        with self.assertRaisesRegex(PipelineError, 'passing check'):
            self.feature(root, 'done')  # the earlier pass predates the feature
        self.command(config, 'unit-bad', 'bad.py'); self.save(root, config)
        self.assertEqual('FAIL', self.run_check(root)['status'])
        with self.assertRaisesRegex(PipelineError, 'passing check'):
            self.feature(root, 'done')
        config['verification']['commands'][-1]['argv'][-1] = 'ok.py'; self.save(root, config)
        passed = self.run_check(root)
        self.assertEqual('PASS', passed['status'])
        done = self.feature(root, 'done')
        self.assertEqual(('DONE', passed['run_id']), (done['feature']['status'], done['feature']['check_run']))
        self.assertIn('commit', done['next'])
        self.assertIn('F-002', done['next'])
        stored = json.loads((root / 'Docs/Work/FEATURES.json').read_text(encoding='utf-8'))
        self.assertEqual(['DONE', 'TODO'], [item['status'] for item in stored['features']])
        with self.assertRaisesRegex(PipelineError, 'no active feature'):
            self.feature(root, 'done')

    def test_a_check_that_requires_a_tracked_task_cannot_finish_a_feature(self):
        root, _ = self.project()
        self.feature(root, 'add', 'Checkout'); self.feature(root, 'next')
        (root / 'payment_api.py').write_bytes(b'x = 1\n')
        self.assertTrue(self.run_check(root)['tracked_required'])
        with self.assertRaisesRegex(PipelineError, 'tracked task'):
            self.feature(root, 'done')

    def test_next_on_an_empty_backlog_says_what_to_do(self):
        root, _ = self.project()
        empty = self.feature(root, 'next')
        self.assertEqual('EMPTY', empty['status'])
        self.assertIn('feature add', empty['next'])
        with self.assertRaises(PipelineError):
            self.feature(root, 'add', '   ')

    def test_tracked_projects_plan_with_tasks_and_the_loop_instead(self):
        root, _ = self.adopted(workflow='tracked')
        with self.assertRaisesRegex(PipelineError, 'lean'):
            self.feature(root, 'add', 'Sign-up form')


if __name__ == '__main__':
    unittest.main()
