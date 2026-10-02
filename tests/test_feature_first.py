"""Feature-first lean defaults: partial checks, honest Fast, accurate path hints."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from web_pipeline import cli
from web_pipeline.common import PipelineError
from web_pipeline.policy import path_risk

KIT = Path(__file__).resolve().parents[1] / 'kit'


def git(root, *args):
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


class Project(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.work = Path(temp.name).resolve()

    def adopted(self, workflow='lean', enable=(), name='app'):
        """A frontend project with the default requirements and only `enable` turned on."""
        root = self.work / name
        cli._init(KIT, root, workflow=workflow, domains=['frontend'])
        config = self.read(root)
        config['project']['ready'] = True
        (root / 'ok.py').write_bytes(b'print("ok-ran")\n')
        for command in config['verification']['commands']:
            if command['id'] in enable:
                command.update(enabled=True, argv=[sys.executable, 'ok.py'])
        self.save(root, config)
        git(root, 'init', '-q'); git(root, 'config', 'user.email', 't@example.com'); git(root, 'config', 'user.name', 't')
        git(root, 'add', '-A'); git(root, 'commit', '-qm', 'init')
        return root, config

    def read(self, root):
        return json.loads((root / 'pipeline.config.yaml').read_text(encoding='utf-8'))

    def save(self, root, config):
        (root / 'pipeline.config.yaml').write_bytes((json.dumps(config, indent=2) + '\n').encode('utf-8'))

    def run_check(self, root, *extra):
        return cli.dispatch(cli._parser().parse_args(['--root', str(root), 'check', *extra]))


class LeanReadinessTests(Project):
    def test_lean_check_runs_the_enabled_checks_and_reports_the_rest(self):
        root, _ = self.adopted(enable=('lint', 'unit'))
        result = self.run_check(root)
        self.assertEqual('PASS', result['status'], result)
        self.assertEqual(['lint', 'unit'], sorted(item['id'] for item in result['checks']))
        self.assertIn('browser-e2e', result['missing_checks'])
        self.assertIn('secret-detection', result['missing_checks'])
        self.assertNotIn('lint', result['missing_checks'])
        self.assertIn('Not enabled', result['commit_table'])
        self.assertIn('browser-e2e', result['commit_table'])

    def test_status_and_check_agree_for_lean(self):
        root, _ = self.adopted()
        status = cli._status(root)
        self.assertIn('enable', status['next'])
        self.assertIn('lint', status['missing_checks'])
        self.assertEqual('FAIL', self.run_check(root)['status'])
        root, _ = self.adopted(enable=('lint',), name='second')
        status = cli._status(root)
        self.assertNotIn('ready_error', status)
        self.assertIn('unit', status['missing_checks'])
        self.assertIn('check', status['next'])
        self.assertEqual('PASS', self.run_check(root)['status'])

    def test_tracked_keeps_strict_readiness_and_status_reports_it(self):
        root, _ = self.adopted(workflow='tracked', enable=('lint',))
        with self.assertRaisesRegex(PipelineError, 'Required project commands are disabled') as raised:
            self.run_check(root)
        self.assertIn('unit', str(raised.exception))
        self.assertIn('browser-e2e', str(raised.exception))
        status = cli._status(root)
        self.assertEqual(str(raised.exception), status['ready_error'])
        self.assertIn('unit', status['next'])

    def test_tracked_status_points_existing_projects_to_lean(self):
        root, config = self.adopted(workflow='tracked', enable=('lint',))
        del config['workflow']
        for command in config['verification']['commands']:
            command['enabled'] = True
            command['argv'] = [sys.executable, 'ok.py']
        self.save(root, config)
        status = cli._status(root)
        self.assertEqual('tracked', status['workflow'])
        self.assertIn('LEAN.md', status['next'])


class FastProfileTests(Project):
    def test_fast_runs_domain_fast_checks_and_custom_fast_checks(self):
        root, config = self.adopted(enable=('lint', 'browser-e2e', 'build'))
        config['verification']['commands'].append({
            'id': 'quick-custom', 'enabled': True, 'profiles': ['Fast', 'Full'], 'argv': [sys.executable, 'ok.py'],
            'cwd': '.', 'timeout_seconds': 60, 'artifacts': [], 'environment': 'test'})
        self.save(root, config)
        fast = self.run_check(root, '--profile', 'Fast')
        self.assertEqual(['lint', 'quick-custom'], sorted(item['id'] for item in fast['checks']), fast)
        full = self.run_check(root)
        self.assertEqual(['browser-e2e', 'build', 'lint', 'quick-custom'], sorted(item['id'] for item in full['checks']))

    def test_policy_checks_run_in_every_lean_profile(self):
        root, config = self.adopted(enable=('lint',))
        config['verification']['commands'].append({
            'id': 'license-policy', 'enabled': True, 'profiles': ['Policy'], 'argv': [sys.executable, 'ok.py'],
            'cwd': '.', 'timeout_seconds': 60, 'artifacts': [], 'environment': 'test'})
        config['verification']['policy_checks'].append('license-policy')
        self.save(root, config)
        for profile in ('Fast', 'Full'):
            result = self.run_check(root, '--profile', profile)
            self.assertIn('license-policy', [item['id'] for item in result['checks']], profile)


class ConfigEditTests(Project):
    def test_config_edit_is_a_notice_and_weakened_checks_are_reported(self):
        root, config = self.adopted(enable=('lint', 'unit'))
        next(c for c in config['verification']['commands'] if c['id'] == 'unit')['enabled'] = False
        config['verification']['requirements']['frontend']['Fast'].remove('format')
        self.save(root, config)
        result = self.run_check(root)
        self.assertEqual('PASS', result['status'], result)
        self.assertNotIn('core_architecture', result['decisions'])
        self.assertEqual('T0', result['risk_tier'])
        self.assertTrue(any('pipeline.config.yaml' in item for item in result['notices']), result['notices'])
        weakened = ' '.join(result['weakened_checks'])
        self.assertIn('unit', weakened)
        self.assertIn('format', weakened)
        self.assertIn('user', result['next'])

    def test_adding_a_check_is_not_weakening(self):
        root, config = self.adopted(enable=('lint',))
        next(c for c in config['verification']['commands'] if c['id'] == 'unit').update(
            enabled=True, argv=[sys.executable, 'ok.py'])
        self.save(root, config)
        self.assertEqual([], self.run_check(root)['weakened_checks'])


class PathHintTests(Project):
    def risk(self, *paths, config=None):
        root = self.work / 'hints'
        if not root.exists():
            cli._init(KIT, root)
        config = config or self.read(root)
        return path_risk(root, config, list(paths))

    def test_word_rules_catch_camel_case_and_skip_lookalikes(self):
        for path in ('src/hooks/useOAuth.ts', 'src/features/SignIn.tsx', 'src/auth/guard.ts', 'auth_guard.py',
                     'src/api/login.ts', 'src/lib/Authentication.ts'):
            self.assertIn('authentication', self.risk(path)['protected_changes'], path)
        for path in ('src/components/AuthorCard.tsx', 'src/components/BlockList.tsx', 'src/unlock/page.tsx'):
            risk = self.risk(path)
            self.assertEqual([], risk['protected_changes'], path)
            self.assertEqual('T1', risk['risk_tier'], path)
        self.assertEqual('T4', self.risk('src/pages/PaymentHistory.tsx')['risk_tier'])
        self.assertIn('authorization_rbac', self.risk('src/server/permissions.ts')['protected_changes'])

    def test_schema_files_are_schema_decisions_and_seeds_are_notices(self):
        for path in ('prisma/schema.prisma', 'db/migrations/0001_init.sql', 'prisma/migrations/2024_x/migration.sql'):
            self.assertIn('database_schema', self.risk(path)['protected_changes'], path)
        for path in ('db/seed.sql', 'prisma/seed.ts', 'db/seeds/001_users.sql'):
            risk = self.risk(path)
            self.assertNotIn('database_schema', risk['protected_changes'], path)
            self.assertTrue(risk['notices'], path)

    def test_dependency_and_env_template_changes_are_notices_not_decisions(self):
        for path in ('package.json', 'pnpm-lock.yaml', 'web/package-lock.json', 'yarn.lock', 'go.sum',
                     'requirements.txt', '.env.example', 'pipeline.config.yaml'):
            risk = self.risk(path)
            self.assertEqual([], risk['protected_changes'], path)
            self.assertEqual('T0', risk['risk_tier'], path)
            self.assertTrue(risk['notices'], path)
        self.assertNotEqual('T4', self.risk('src/config/app.env.ts')['risk_tier'])
        for path in ('.env', '.env.local', 'config/.env.production'):
            self.assertIn('secrets_credentials', self.risk(path)['protected_changes'], path)

    def test_server_routes_and_component_files_get_domains(self):
        for path in ('src/app/api/users/route.ts', 'src/server/routes/notes.ts', 'pages/api/hello.js'):
            self.assertIn('backend', self.risk(path)['change_domains'], path)
        for path in ('src/App.jsx', 'src/lib/Button.svelte', 'src/styles/site.scss'):
            self.assertIn('frontend', self.risk(path)['change_domains'], path)

    def test_engine_files_stay_protected(self):
        self.assertIn('core_architecture', self.risk('web_pipeline/runner.py')['protected_changes'])

    def test_rules_without_match_keep_case_sensitive_globs(self):
        root = self.work / 'hints'; cli._init(KIT, root)
        config = self.read(root)
        config['risk']['path_rules'] = [{'pattern': '*auth*', 'domains': ['authentication'],
                                         'protected_changes': ['authentication'], 'tier': 'T3'}]
        self.assertEqual([], self.risk('src/useOAuth.ts', config=config)['protected_changes'])
        self.assertIn('authentication', self.risk('src/authGuard.ts', config=config)['protected_changes'])


if __name__ == '__main__': unittest.main()
