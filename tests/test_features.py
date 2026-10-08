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

    def test_done_needs_the_check_to_match_the_current_tree_and_config(self):
        root, config = self.project()
        self.feature(root, 'add', 'Sign-up form'); self.feature(root, 'next')
        (root / 'signup.py').write_bytes(b'value = 1\n')
        self.assertEqual('PASS', self.run_check(root)['status'])
        (root / 'signup.py').write_bytes(b'value = 2\n')  # edited after the check
        with self.assertRaisesRegex(PipelineError, 'changed after'):
            self.feature(root, 'done')
        self.assertEqual('PASS', self.run_check(root)['status'])
        self.command(config, 'extra', 'ok.py', enabled=False); self.save(root, config)
        with self.assertRaisesRegex(PipelineError, 'changed after'):
            self.feature(root, 'done')  # the configuration is part of what the check proved
        self.run_check(root)
        self.assertEqual('DONE', self.feature(root, 'done')['status'])

    def test_a_feature_checks_everything_since_it_started(self):
        root, _ = self.project()
        head = test_lean.subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True,
                                        text=True, check=True).stdout.strip()
        self.feature(root, 'add', 'Checkout')
        started = self.feature(root, 'next')['feature']
        self.assertEqual(head, started['base_commit'])
        (root / 'cart.py').write_bytes(b'x = 1\n')
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'mid-feature commit')
        result = self.run_check(root)
        self.assertEqual(head, result['base_ref'])
        self.assertIn('cart.py', result['changed_paths'])
        self.assertEqual('HEAD', self.run_check(root, '--base-ref', 'HEAD')['base_ref'])

    def test_done_needs_a_check_that_covers_the_whole_feature(self):
        root, _ = self.project()
        self.feature(root, 'add', 'Checkout'); self.feature(root, 'next')
        (root / 'cart.py').write_bytes(b'x = 1\n')
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'mid-feature commit')
        self.assertEqual('PASS', self.run_check(root, '--base-ref', 'HEAD')['status'])  # misses cart.py
        with self.assertRaisesRegex(PipelineError, 'without --base-ref'):
            self.feature(root, 'done')
        self.assertEqual('PASS', self.run_check(root)['status'])
        self.assertEqual('DONE', self.feature(root, 'done')['status'])

    def test_a_project_setting_change_after_the_check_needs_a_new_check(self):
        root, config = self.project()
        self.feature(root, 'add', 'Sign-up form'); self.feature(root, 'next')
        self.assertEqual('PASS', self.run_check(root)['status'])
        config['project']['supported_domains'] = ['frontend', 'backend']; self.save(root, config)
        with self.assertRaisesRegex(PipelineError, 'changed after'):
            self.feature(root, 'done')
        self.assertEqual('PASS', self.run_check(root)['status'])
        self.assertEqual('DONE', self.feature(root, 'done')['status'])

    def test_status_shows_the_gate_that_feature_done_applies(self):
        # The review reads this gate, so it cannot refuse what feature done accepts or accept what it refuses.
        root, _ = self.project()
        self.assertEqual((False, None), (cli._status(root)['commit_gate']['ready'],
                                         cli._status(root)['commit_gate']['run_id']))
        self.assertEqual('PASS', self.run_check(root)['status'])
        self.assertTrue(cli._status(root)['commit_gate']['ready'])  # no backlog: the newest gate check decides
        self.feature(root, 'add', 'Sign-up form'); self.feature(root, 'next')
        self.assertFalse(cli._status(root)['commit_gate']['ready'])  # that check predates the feature
        (root / 'signup.py').write_bytes(b'value = 1\n')
        full = self.run_check(root)
        self.assertEqual('PASS', self.run_check(root, '--profile', 'Fast')['status'])  # iteration after the gate
        status = cli._status(root)
        gate = status['commit_gate']
        self.assertEqual('Fast', status['last_check']['profile'])
        self.assertEqual((True, full['run_id'], 'Full', full['base_commit'], None),
                         (gate['ready'], gate['run_id'], gate['profile'], gate['base'], gate['reason']))
        (root / 'signup.py').write_bytes(b'value = 2\n')
        gate = cli._status(root)['commit_gate']
        self.assertFalse(gate['ready'])
        with self.assertRaises(PipelineError) as refused:
            self.feature(root, 'done')
        self.assertEqual(gate['reason'], str(refused.exception))
        (root / 'signup.py').write_bytes(b'value = 1\n')
        self.assertEqual(full['run_id'], self.feature(root, 'done')['feature']['check_run'])

    def test_a_backlog_or_git_it_cannot_read_is_a_clear_error(self):
        from unittest.mock import patch
        from web_pipeline import features
        root, _ = self.project()
        for error in (OSError('git missing'), test_lean.subprocess.TimeoutExpired(['git'], 30)):
            with self.subTest(error=type(error).__name__), patch('subprocess.run', side_effect=error):
                self.assertIsNone(features._head(root))
        self.feature(root, 'add', 'Checkout'); self.feature(root, 'next')
        with patch('subprocess.run', side_effect=OSError('git missing')):
            self.assertIsNone(features.active_base(root))
        backlog = root / features.BACKLOG
        data = json.loads(backlog.read_text(encoding='utf-8'))
        data['features'][0]['started_utc'] = 'yesterday'
        backlog.write_bytes((json.dumps(data) + '\n').encode('utf-8'))
        self.run_check(root)
        with self.assertRaisesRegex(PipelineError, 'started_utc'):
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
