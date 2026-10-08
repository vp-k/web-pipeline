"""Lean check guards a script can decide: test reports, reruns, failure loops, weakened checks, test edits."""
import json
import sys
import unittest

from tests import test_lean
from web_pipeline import cli
from web_pipeline.lean import config_weakening

REPORTER = '''import json, os, sys
evidence = os.environ["PIPELINE_EVIDENCE_DIR"]
count = int(sys.argv[1])
tests = [{"id": f"t{i}", "group": "unit", "status": "passed", "duration_ms": 1} for i in range(count)]
os.makedirs(os.path.join(evidence, "artifacts"), exist_ok=True)
with open(os.path.join(evidence, "artifacts", "unit-tests.json"), "w") as out:
    json.dump({"schema_version": "1.0", "run_id": os.path.basename(evidence), "check_id": os.environ["PIPELINE_CHECK_ID"],
               "completed": True, "errors": [], "tests": tests}, out)
'''
REPORT = {'path': 'artifacts/unit-tests.json', 'min_tests': 1, 'max_skipped': 0, 'required_groups': ['unit']}


class LeanGuardTests(unittest.TestCase):
    setUp = test_lean.LeanTests.setUp
    adopted = test_lean.LeanTests.adopted
    save = test_lean.LeanTests.save
    command = test_lean.LeanTests.command
    run_check = test_lean.LeanTests.run_check

    def project(self, script='ok.py'):
        root, config = self.adopted()
        self.command(config, 'suite', script); self.save(root, config)
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'checks')
        return root, config

    def test_a_check_with_a_test_report_needs_real_executed_tests(self):
        root, config = self.adopted()
        (root / 'reporter.py').write_bytes(REPORTER.encode('utf-8'))
        self.command(config, 'suite', 'reporter.py')
        config['verification']['commands'][-1].update(argv=[sys.executable, 'reporter.py', '0'], test_report=REPORT)
        self.save(root, config)
        zero = self.run_check(root)
        self.assertEqual('FAIL', zero['status'], zero)
        self.assertIn('Insufficient executed tests', zero['checks'][0]['reason'])
        log = (root / zero['evidence'] / zero['checks'][0]['log']).read_text(encoding='utf-8', errors='replace')
        self.assertIn('Insufficient executed tests', log)
        config['verification']['commands'][-1]['argv'][-1] = '3'; self.save(root, config)
        self.assertEqual('PASS', self.run_check(root)['status'])
        config['verification']['commands'][-1]['argv'] = [sys.executable, 'ok.py']; self.save(root, config)
        missing = self.run_check(root)
        self.assertEqual('FAIL', missing['status'])
        self.assertIn('report', missing['checks'][0]['reason'].lower())

    def test_a_rerun_without_a_code_or_config_change_is_reported(self):
        root, config = self.project('bad.py')
        first = self.run_check(root)
        self.assertEqual('FAIL', first['status'])
        self.assertIsNone(first['repeat'])
        self.assertTrue(first['snapshot']['tree_digest'])
        again = self.run_check(root)
        self.assertEqual({'run_id': first['run_id'], 'status': 'FAIL'}, again['repeat'])
        self.assertIn('already failed', again['next'])
        (root / 'app.py').write_bytes(b'x = 2\n')
        self.assertIsNone(self.run_check(root)['repeat'])
        self.command(config, 'extra', 'ok.py'); self.save(root, config)  # a config change alone is a new input
        self.assertIsNone(self.run_check(root)['repeat'])

    def test_the_same_failure_across_edits_is_a_failure_loop(self):
        root, _ = self.project('bad.py')
        streaks = []
        for value in range(3):
            (root / 'app.py').write_bytes(f'x = {value}\n'.encode('utf-8'))
            result = self.run_check(root)
            streaks.append(result['same_failure'])
        self.assertEqual([1, 2, 3], streaks)
        self.assertIsNone(result['repeat'])
        self.assertIn('root cause', result['next'])

    def test_a_narrower_pass_does_not_end_a_failure_loop(self):
        from web_pipeline.guards import rerun_facts

        def run(profile, failure=None):
            return {'run_id': f'check-{profile}', 'profile': profile, 'status': 'FAIL' if failure else 'PASS',
                    'failure_fingerprint': failure, 'snapshot': {'tree_digest': 'tree'}}

        def streak(oldest_first, profile, failure='x'):
            facts = rerun_facts(list(reversed(oldest_first)), profile, {'tree_digest': 'other'}, 'c', None, failure)
            return facts['same_failure']
        self.assertEqual(2, streak([run('Full', 'x'), run('Fast')], 'Full'))
        self.assertEqual(2, streak([run('Full', 'x'), run('Fast')], 'Fast'))  # the pass came after a wider failure
        self.assertEqual(1, streak([run('Full', 'x'), run('Full')], 'Full'))
        self.assertEqual(1, streak([run('Fast', 'x'), run('Fast')], 'Full'))  # it covered the failure before it
        self.assertEqual(1, streak([run('Full', 'x'), run('Fast', 'y')], 'Full'))
        self.assertEqual(0, streak([run('Full', 'x')], 'Fast', None))

    def test_status_shows_the_last_check_and_whether_it_still_matches_the_tree(self):
        root, _ = self.project()
        self.assertIsNone(cli._status(root).get('last_check'))
        passed = self.run_check(root)
        last = cli._status(root)['last_check']
        self.assertEqual((passed['run_id'], 'PASS', True, 'HEAD'),
                         (last['run_id'], last['status'], last['current'], last['base_ref']))
        (root / 'app.py').write_bytes(b'x = 1\n')
        self.assertFalse(cli._status(root)['last_check']['current'])

    def test_loosened_test_reports_are_weakening_and_new_commands_are_notices(self):
        root, config = self.project()
        config['verification']['commands'][-1]['test_report'] = dict(REPORT, min_tests=50)
        before = json.loads(json.dumps(config))
        loose = json.loads(json.dumps(config))
        loose['verification']['commands'][-1]['test_report'].update(min_tests=0, max_skipped=9, required_groups=[])
        found = config_weakening(before, loose)
        self.assertTrue(any('min_tests' in item for item in found), found)
        self.assertTrue(any('max_skipped' in item for item in found), found)
        self.assertTrue(any('required_groups' in item for item in found), found)
        del loose['verification']['commands'][-1]['test_report']
        self.assertTrue(any('test report removed' in item for item in config_weakening(before, loose)))
        shorter = json.loads(json.dumps(config)); shorter['verification']['commands'][-1]['timeout_seconds'] = 1
        self.assertEqual([], config_weakening(before, shorter))  # a timeout fails the check; it cannot fake a pass
        config['verification']['commands'][-1]['argv'] = [sys.executable, '-c', 'pass']; self.save(root, config)
        result = self.run_check(root)
        self.assertTrue(any('suite: command changed' in item for item in result['notices']), result['notices'])

    def test_a_changed_package_script_behind_a_check_is_a_notice(self):
        root, config = self.adopted()
        (root / 'package.json').write_bytes(b'{"scripts": {"test": "vitest run"}}\n')
        config['verification']['commands'].append({
            'id': 'suite', 'enabled': True, 'profiles': ['Fast', 'Full', 'Release'],
            'argv': [sys.executable, 'ok.py', 'npm', 'test'], 'cwd': '.', 'timeout_seconds': 60,
            'artifacts': [], 'environment': 'test'})
        self.save(root, config)
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'npm')
        from web_pipeline.guards import script_changes
        npm = dict(config['verification']['commands'][-1], argv=['npm', 'test'])
        self.assertEqual([], script_changes(root, [npm], 'HEAD'))
        (root / 'package.json').write_bytes(b'{"scripts": {"test": "vitest run --passWithNoTests"}}\n')
        self.assertEqual(['suite: package.json script "test" changed'], script_changes(root, [npm], 'HEAD'))
        run = dict(npm, argv=['npm.cmd', 'run', 'test'])
        self.assertEqual(['suite: package.json script "test" changed'], script_changes(root, [run], 'HEAD'))

    def test_deleted_tests_and_added_skip_markers_are_listed(self):
        root, config = self.project()
        (root / 'tests').mkdir()
        (root / 'tests/test_cart.py').write_bytes(b'def test_total():\n    assert 1\n\ndef test_tax():\n    assert 1\n')
        (root / 'checkout.spec.ts').write_bytes(b"it('pays', () => {})\n")
        (root / 'tests/test_old.py').write_bytes(b'def test_legacy():\n    assert 1\n')
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'tests')
        self.assertEqual([], self.run_check(root)['test_changes'])
        (root / 'tests/test_old.py').unlink()
        (root / 'tests/test_cart.py').write_bytes(b'import pytest\n\n@pytest.mark.skip\ndef test_total():\n    assert 1\n')
        (root / 'checkout.spec.ts').write_bytes(b"it.skip('pays', () => {})\n")
        changes = self.run_check(root)['test_changes']
        self.assertIn('tests/test_old.py: test file deleted', changes)
        self.assertIn('tests/test_cart.py: 1 skip/only marker added', changes)
        self.assertIn('tests/test_cart.py: 1 test removed', changes)
        self.assertIn('checkout.spec.ts: 1 skip/only marker added', changes)

    def test_a_project_setting_change_makes_the_last_check_stale(self):
        root, config = self.project()
        self.run_check(root)
        self.assertTrue(cli._status(root)['last_check']['current'])
        config['project']['supported_domains'] = ['frontend', 'backend']; self.save(root, config)
        self.assertFalse(cli._status(root)['last_check']['current'])  # the domains decide which checks run
        self.run_check(root)
        self.assertTrue(cli._status(root)['last_check']['current'])

    def test_a_base_that_moved_on_is_compared_where_the_branch_left_it(self):
        root, config = self.project()
        (root / 'tests').mkdir()
        (root / 'tests/test_cart.py').write_bytes(b'def test_total():\n    assert 1\n')
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'tests')
        test_lean.git(root, 'branch', 'base'); test_lean.git(root, 'checkout', '-qb', 'work')
        test_lean.git(root, 'checkout', '-q', 'base')
        (root / 'tests/test_cart.py').write_bytes(b'def test_total():\n    assert 1\n\ndef test_tax():\n    assert 1\n')
        moved = json.loads(json.dumps(config)); self.command(moved, 'extra', 'ok.py'); self.save(root, moved)
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'base moves on')
        test_lean.git(root, 'checkout', '-q', 'work')
        (root / 'tests/test_cart.py').write_bytes(b'def test_total():\n    assert 1  # edited on work\n')
        result = self.run_check(root, '--base-ref', 'base')
        self.assertIn('tests/test_cart.py', result['changed_paths'])
        self.assertEqual([], result['test_changes'])  # base added test_tax; work removed nothing
        self.assertEqual([], result['weakened_checks'])  # base added extra; work removed nothing

    def test_a_base_config_of_another_shape_is_a_warning_not_a_crash(self):
        root, config = self.project()
        (root / 'pipeline.config.yaml').write_bytes(b'{"verification": {"commands": [{"profiles": []}]}}\n')
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'odd config')
        self.save(root, config)
        result = self.run_check(root)
        self.assertEqual('PASS', result['status'])
        self.assertEqual([], result['weakened_checks'])
        self.assertTrue(any('could not be compared' in item for item in result['warnings']), result['warnings'])

    def test_a_regex_test_call_is_not_a_test_definition(self):
        from web_pipeline.guards import TEST_DEFINITION
        source = ("it('pays', () => {})\ntest.each([1, 2])('adds %i', () => {})\nit(`tags`, () => {})\n"
                  "if (/x/.test(value)) {}\nconst ok = schema.test(value)\nsubmit(form)\n"
                  "def test_total():\n    pass\nfunc TestTotal(t *testing.T) {}\n")
        self.assertEqual(5, len(TEST_DEFINITION.findall(source)))

    def test_scripts_behind_a_workspace_selector_are_not_guessed(self):
        from web_pipeline.guards import script_name
        for argv in (['pnpm', '--filter', 'web', 'test'], ['pnpm', '-F', 'web', 'test'], ['npm', '-w', 'web', 'test'],
                     ['npm', '--workspace=web', 'test'], ['yarn', 'workspace', 'web', 'test'],
                     ['npm', '--prefix', 'web', 'test'], ['pnpm', '-C', 'web', 'test'], ['pnpm', '-r', 'test'],
                     ['yarn', '--cwd', 'web', 'test']):
            with self.subTest(argv=argv):
                self.assertIsNone(script_name(argv))
        self.assertEqual('test', script_name(['npm', 'test']))
        self.assertEqual('lint', script_name(['pnpm', 'lint']))

    def test_a_changed_pre_or_post_script_is_a_notice(self):
        root, _ = self.adopted()
        (root / 'web').mkdir()
        (root / 'web/package.json').write_bytes(b'{"scripts": {"test": "vitest run", "posttest": "node verify.js"}}\n')
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'web')
        from web_pipeline.guards import script_changes
        npm = {'id': 'suite', 'enabled': True, 'argv': ['npm', 'test'], 'cwd': '.\\web\\'}
        self.assertEqual([], script_changes(root, [npm], 'HEAD'))
        (root / 'web/package.json').write_bytes(b'{"scripts": {"test": "vitest run", "posttest": "exit 0"}}\n')
        self.assertEqual(['suite: package.json script "posttest" changed'], script_changes(root, [npm], 'HEAD'))

    def test_a_rerun_against_another_base_is_a_new_input(self):
        root, _ = self.project('bad.py')
        (root / 'app.py').write_bytes(b'x = 1\n')
        test_lean.git(root, 'add', '-A'); test_lean.git(root, 'commit', '-qm', 'app')
        first = self.run_check(root)
        self.assertEqual(first['run_id'], self.run_check(root)['repeat']['run_id'])
        self.assertIsNone(self.run_check(root, '--base-ref', 'HEAD~1')['repeat'])  # other changed paths

    def test_a_fast_pass_points_to_the_gate_check_not_to_the_review(self):
        # The review and feature done need a Task or Full check; a Fast pass is iteration.
        root, _ = self.project()
        fast = self.run_check(root, '--profile', 'Fast')
        self.assertEqual('PASS', fast['status'])
        self.assertNotIn('review', fast['next'])
        self.assertIn('run check before the commit', fast['next'])
        self.assertIn('review', self.run_check(root)['next'])

    def test_git_that_cannot_run_means_nothing_to_compare(self):
        from unittest.mock import patch
        from web_pipeline import guards, lean
        root, _ = self.project()
        for error in (OSError('git missing'), test_lean.subprocess.TimeoutExpired(['git'], 60)):
            with self.subTest(error=type(error).__name__), patch('subprocess.run', side_effect=error):
                self.assertIsNone(guards._show(root, 'HEAD', 'app.py'))
                self.assertIsNone(lean._base_config(root, 'HEAD'))


if __name__ == '__main__':
    unittest.main()
