"""Lean workflow: adopt defaults, status orientation and task-free checks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from web_pipeline import cli

KIT = Path(__file__).resolve().parents[1] / 'kit'


def git(root, *args):
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


class LeanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.work = Path(temp.name).resolve()

    def adopted(self, workflow='lean', ready=True):
        root = self.work / 'app'
        cli._init(KIT, root, workflow=workflow)
        config = json.loads((root / 'pipeline.config.yaml').read_text(encoding='utf-8'))
        config['project']['ready'] = ready
        config['project']['supported_domains'] = ['frontend']
        config['verification']['policy_checks'] = []
        config['verification']['requirements']['frontend'] = {name: [] for name in config['verification']['requirements']['frontend']}
        for command in config['verification']['commands']:
            command['enabled'] = False
        (root / 'ok.py').write_bytes(b'print("ok-ran")\n')
        (root / 'bad.py').write_bytes(b'import sys\nprint("bad-ran")\nsys.exit(3)\n')
        self.save(root, config)
        git(root, 'init', '-q'); git(root, 'config', 'user.email', 't@example.com'); git(root, 'config', 'user.name', 't')
        git(root, 'add', '-A'); git(root, 'commit', '-qm', 'init')
        return root, config

    def save(self, root, config):
        (root / 'pipeline.config.yaml').write_bytes((json.dumps(config, indent=2) + '\n').encode('utf-8'))

    def command(self, config, check_id, script, profiles=('Fast', 'Full', 'Release'), enabled=True):
        config['verification']['commands'].append({
            'id': check_id, 'enabled': enabled, 'profiles': list(profiles), 'argv': [sys.executable, script],
            'cwd': '.', 'timeout_seconds': 60, 'artifacts': [], 'environment': 'test'})

    def test_init_defaults_to_lean_and_can_choose_tracked(self):
        lean = self.work / 'lean'; cli._init(KIT, lean)
        tracked = self.work / 'tracked'; cli._init(KIT, tracked, workflow='tracked')
        read = lambda root: json.loads((root / 'pipeline.config.yaml').read_text(encoding='utf-8'))
        self.assertEqual('lean', read(lean)['workflow'])
        self.assertEqual('tracked', read(tracked)['workflow'])
        self.assertEqual('lean', cli._parser().parse_args(['init', '--target', 'x']).workflow)

    def test_status_reports_workflow_and_missing_means_tracked(self):
        root, config = self.adopted()
        status = cli._status(root)
        self.assertEqual('lean', status['workflow'])
        self.assertIn('check', status['next'])
        del config['workflow']; self.save(root, config)
        self.assertEqual('tracked', cli._status(root)['workflow'])

    def test_check_runs_enabled_profile_checks_without_a_task(self):
        root, config = self.adopted()
        self.command(config, 'unit-ok', 'ok.py')
        self.command(config, 'fast-only', 'bad.py', profiles=('Fast',))
        self.command(config, 'disabled', 'bad.py', enabled=False)
        self.save(root, config)
        result = cli.dispatch(cli._parser().parse_args(['--root', str(root), 'check']))
        self.assertEqual('PASS', result['status'], result)
        self.assertEqual(['unit-ok'], [item['id'] for item in result['checks']])
        self.assertIn('| unit-ok | PASS |', result['commit_table'])
        log = root / result['evidence'] / result['checks'][0]['log']
        self.assertIn('ok-ran', log.read_text(encoding='utf-8', errors='replace'))
        self.assertFalse((root / 'Docs/Work').exists() and any((root / 'Docs/Work').iterdir()))
        fast = cli.dispatch(cli._parser().parse_args(['--root', str(root), 'check', '--profile', 'Fast']))
        self.assertEqual('FAIL', fast['status'])
        self.assertEqual(['fast-only', 'unit-ok'], sorted(item['id'] for item in fast['checks']))

    def test_check_failure_returns_nonzero(self):
        root, config = self.adopted()
        self.command(config, 'unit-ok', 'ok.py'); self.command(config, 'unit-bad', 'bad.py')
        self.save(root, config)
        self.assertEqual(1, cli.main(['--root', str(root), 'check']))
        result = cli.dispatch(cli._parser().parse_args(['--root', str(root), 'check']))
        self.assertEqual('FAIL', result['status'])
        self.assertIn('| unit-bad | FAIL |', result['commit_table'])
        self.assertIn('unit-bad', result['next'])

    def test_check_without_enabled_checks_fails_clearly(self):
        root, _ = self.adopted()
        result = cli.dispatch(cli._parser().parse_args(['--root', str(root), 'check']))
        self.assertEqual('FAIL', result['status'])
        self.assertEqual([], result['checks'])
        self.assertIn('enable', result['next'])

    def test_check_flags_tracked_and_decision_paths(self):
        root, config = self.adopted()
        self.command(config, 'unit-ok', 'ok.py'); self.save(root, config)
        git(root, 'add', '-A'); git(root, 'commit', '-qm', 'checks')
        (root / 'auth_guard.py').write_bytes(b'x = 1\n')
        decision = cli.dispatch(cli._parser().parse_args(['--root', str(root), 'check']))
        self.assertEqual('PASS', decision['status'])
        self.assertFalse(decision['tracked_required'])
        self.assertIn('authentication', decision['decisions'])
        self.assertIn('auth_guard.py', decision['changed_paths'])
        (root / 'payment_api.py').write_bytes(b'x = 1\n')
        tracked = cli.dispatch(cli._parser().parse_args(['--root', str(root), 'check']))
        self.assertEqual('T4', tracked['risk_tier'])
        self.assertTrue(tracked['tracked_required'])
        self.assertIn('tracked task', tracked['next'])


if __name__ == '__main__': unittest.main()
