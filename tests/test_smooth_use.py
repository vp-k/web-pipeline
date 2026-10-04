"""Smooth tracked use: the defaults and recoveries the end-to-end trial needed (docs/E2E_TRIAL.md)."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import test_autopilot, test_maintenance
from tests.planning_fixture import record_fixture_planning
from tests.test_feature_first import KIT, Project, git
from web_pipeline import cli
from web_pipeline import maintenance
from web_pipeline.common import PipelineError, atomic_json, atomic_text, read_state, write_state
from web_pipeline.state import revise_task

FRONTEND = ('secret-detection', 'dependency-policy', 'format', 'lint', 'typecheck', 'unit',
            'browser-e2e', 'accessibility', 'build', 'smoke')


class Tracked(Project):
    def cli(self, root, *args):
        return cli.dispatch(cli._parser().parse_args(['--root', str(root), *args]))

    def head(self, root):
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True, capture_output=True,
                              text=True).stdout.strip()

    def new(self, root, task='FEAT-1', *extra, domains='frontend', tier='T1'):
        return self.cli(root, 'new', '--task', task, '--title', 'Note list', '--tier', tier, '--domains', domains, *extra)

    def plan(self, root, task='FEAT-1', checks=('unit',)):
        directory = root / 'Docs/Work' / task
        atomic_text(directory / 'BRIEF.md', '# Note list\n\nShow saved notes.\n')
        atomic_text(directory / 'DOR.md', '# Ready\n\nScope and checks are defined.\n')
        atomic_json(directory / 'ACCEPTANCE.json', {'criteria': [
            {'id': 'AC-1', 'description': 'Saved notes are listed', 'checks': list(checks)}]})
        record_fixture_planning(root, task)


class BaseRefTests(Tracked):
    def test_new_defaults_base_ref_to_the_current_commit(self):
        root, _ = self.adopted(workflow='tracked', enable=FRONTEND)
        state = self.new(root)
        self.assertEqual(self.head(root), state['base_ref'])
        self.plan(root)
        self.assertEqual(self.head(root), self.cli(root, 'prepare', '--task', 'FEAT-1')['base_ref'])

    def test_explicit_base_ref_is_kept_as_written(self):
        root, _ = self.adopted(workflow='tracked', enable=FRONTEND)
        self.assertEqual('HEAD', self.new(root, 'FEAT-1', '--base-ref', 'HEAD')['base_ref'])

    def test_new_before_the_first_commit_says_how_to_continue(self):
        root = self.work / 'fresh'
        cli._init(KIT, root, workflow='tracked', domains=['frontend'])
        git(root, 'init', '-q')
        with self.assertRaisesRegex(PipelineError, 'commit') as raised:
            self.new(root)
        self.assertIn('--base-ref', str(raised.exception))

    def test_prepare_sets_a_missing_base_ref_instead_of_forcing_a_new_task(self):
        root, _ = self.adopted(workflow='tracked', enable=FRONTEND)
        self.new(root)
        state = read_state(root, 'FEAT-1')
        state['base_ref'] = None  # a task created before base_ref had a default
        write_state(root, state)
        self.plan(root)
        with self.assertRaisesRegex(PipelineError, '--base-ref'):
            self.cli(root, 'prepare', '--task', 'FEAT-1')
        head = self.head(root)
        self.assertEqual(head, self.cli(root, 'prepare', '--task', 'FEAT-1', '--base-ref', head)['base_ref'])

    def test_prepare_rejects_unusable_base_refs(self):
        root, _ = self.adopted(workflow='tracked', enable=FRONTEND)
        self.new(root)
        self.plan(root)
        with self.assertRaisesRegex(PipelineError, 'not an option'):
            self.cli(root, 'prepare', '--task', 'FEAT-1', '--base-ref=--output=x')
        with self.assertRaisesRegex(PipelineError, 'commit'):
            self.cli(root, 'prepare', '--task', 'FEAT-1', '--base-ref', 'no-such-branch')
        self.assertEqual(self.head(root), read_state(root, 'FEAT-1')['base_ref'])


class PrepareReadinessTests(Tracked):
    def test_prepare_names_the_disabled_checks_the_task_will_need(self):
        root, _ = self.adopted(enable=('lint', 'unit'))  # lean: the project starts with partial checks
        self.new(root)
        self.plan(root)
        with self.assertRaisesRegex(PipelineError, 'not enabled') as raised:
            self.cli(root, 'prepare', '--task', 'FEAT-1')
        for check in ('typecheck', 'build', 'browser-e2e', 'secret-detection'):
            self.assertIn(check, str(raised.exception))
        self.assertNotIn("'lint'", str(raised.exception))
        self.assertIsNone(read_state(root, 'FEAT-1')['fingerprint'])

    def test_t4_prepare_blocks_on_development_checks_and_warns_about_release_checks(self):
        root, _ = self.adopted(enable=FRONTEND)
        self.new(root, 'PAY-1', domains='frontend,payment', tier='T4')
        self.plan(root, 'PAY-1')
        with self.assertRaises(PipelineError) as raised:
            self.cli(root, 'prepare', '--task', 'PAY-1')
        self.assertIn('payment-tests', str(raised.exception))
        # Release setup (production builds, recovery drills) may wait until the work is DONE.
        self.assertNotIn('recovery-validation', str(raised.exception))
        config = self.read(root)
        for command in config['verification']['commands']:
            if command['id'] in {'payment-tests', 'integration', 'security', 'contract-provider'}:
                command.update(enabled=True, argv=[sys.executable, 'ok.py'])
        self.save(root, config)
        directory = root / 'Docs/Work/PAY-1'
        for name in ('PLAN.md', 'EXEC_PLAN.md', 'RELEASE.md'):
            atomic_text(directory / name, f'# {name}\n\nCharge the saved card, then roll back by disabling the flag.\n')
        atomic_json(directory / 'ADR-PAY.json', {
            'id': 'ADR-PAY', 'title': 'Card charge', 'status': 'ACCEPTED', 'task_id': 'PAY-1', 'revision': 1,
            'scope': ['payment'], 'context': 'Notes can be bought', 'decision': 'Charge through the provider',
            'risks': 'Double charge', 'recovery': 'Disable the flag and refund'})
        state = read_state(root, 'PAY-1')
        state['decision_records'] = ['Docs/Work/PAY-1/ADR-PAY.json']
        write_state(root, state)
        prepared = self.cli(root, 'prepare', '--task', 'PAY-1')
        self.assertTrue(prepared['fingerprint'])
        warning = ' '.join(prepared['warnings'])
        for check in ('production-build', 'recovery-validation'):
            self.assertIn(check, warning)
        self.assertNotIn('payment-tests', warning)
        self.assertNotIn('warnings', read_state(root, 'PAY-1'))

    def test_prepare_clears_the_revision_reason_from_blockers(self):
        root, _ = self.adopted(workflow='tracked', enable=FRONTEND)
        self.new(root)
        self.plan(root)
        self.cli(root, 'prepare', '--task', 'FEAT-1')
        revise_task(root, 'FEAT-1', 'Scope grew to include sorting')
        self.assertEqual(1, len(read_state(root, 'FEAT-1')['blockers']))
        self.plan(root)
        state = self.cli(root, 'prepare', '--task', 'FEAT-1')
        self.assertEqual([], state['blockers'])
        history = (root / 'Docs/Work/FEAT-1/REVISION_HISTORY.json').read_text(encoding='utf-8')
        self.assertIn('Scope grew to include sorting', history)


class RepairContextTests(unittest.TestCase):
    """REPAIR hands the worker the cause, not just the instruction to repair."""
    setUp = test_autopilot.AutopilotTests.setUp
    begin = test_autopilot.AutopilotTests.begin
    next = test_autopilot.AutopilotTests.next
    complete = test_autopilot.AutopilotTests.complete

    def test_repair_after_a_failed_run_names_the_failing_checks(self):
        self.begin()
        atomic_text(self.root / 'app.py', 'value = 40\n')
        self.complete(self.next())
        repair = self.next()
        self.assertEqual('REPAIR', repair['action'])
        cause = repair['repair']
        self.assertEqual('FAIL', cause['status'])
        self.assertTrue(cause['run_id'])
        failing = {check['id']: check for check in cause['checks']}
        self.assertEqual({'unit'}, set(failing))
        self.assertEqual('FAIL', failing['unit']['status'])
        self.assertTrue(failing['unit']['log'])

    def test_repair_after_review_carries_the_reviewer_decision(self):
        self.begin()
        self.complete(self.next())
        change = {**test_autopilot.DECISION, 'choice': 'Handle the empty list', 'rationale': 'Empty notes crash the page'}
        self.complete(self.next(), 'changes_required', change)
        cause = self.next()['repair']
        self.assertEqual('changes_required', cause['review']['outcome'])
        self.assertEqual('Empty notes crash the page', cause['review']['decision']['rationale'])

    def test_first_implementation_has_no_repair_context(self):
        self.begin()
        self.assertNotIn('repair', self.next())


def crlf(path):
    path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))


class LineEndingTests(unittest.TestCase):
    """A Windows clone with core.autocrlf=true checks the engine out with CRLF; that is not a local edit."""
    setUp = test_maintenance.MaintenanceTests.setUp
    hashes = test_maintenance.MaintenanceTests.hashes

    def crlf_checkout(self):
        for folder in maintenance.MANAGED:
            for path in (self.target / folder).rglob('*'):
                if path.is_file() and path.suffix in {'.py', '.json', '.ps1', '.psm1', '.cjs'}:
                    crlf(path)

    def test_upgrade_and_restore_accept_a_crlf_checkout(self):
        self.crlf_checkout()
        applied = maintenance.upgrade(self.new, self.target, apply=True)
        self.assertEqual('APPLIED', applied['mode'])
        self.assertEqual('RESTORED', maintenance.restore(self.target, applied['transaction'])['mode'])

    def test_a_real_edit_still_blocks_a_crlf_checkout(self):
        self.crlf_checkout()
        engine = self.target / 'web_pipeline/__init__.py'
        engine.write_bytes(engine.read_bytes() + b'# local\r\n')
        with self.assertRaisesRegex(PipelineError, 'modified/missing'):
            maintenance.upgrade(self.new, self.target, apply=True)

    def test_adopt_pins_engine_line_endings_and_keeps_project_rules(self):
        target = self.work / 'site'
        target.mkdir()
        (target / '.gitattributes').write_text('*.sh text eol=lf\n', encoding='utf-8')
        result = cli._init(KIT, target)
        self.assertIn('.gitattributes', result['merged'])
        lines = (target / '.gitattributes').read_text(encoding='utf-8').splitlines()
        self.assertEqual('*.sh text eol=lf', lines[0])
        for rule in ('web_pipeline/** text=auto eol=lf', 'Schemas/** text=auto eol=lf', 'Docs/** text=auto eol=lf'):
            self.assertIn(rule, lines)  # task fingerprints hash these records, so a CRLF checkout must not rewrite them
        self.assertFalse([line for line in lines if line.split()[:1] == ['*']], lines)  # never a rule for product files
        fresh = self.work / 'fresh'
        self.assertIn('.gitattributes', cli._init(KIT, fresh)['merged'])
        self.assertTrue((fresh / '.gitattributes').read_text(encoding='utf-8').startswith('# web-pipeline'))

    def test_doctor_accepts_a_crlf_install_of_the_plugin(self):
        repo = Path(__file__).resolve().parents[1]
        plugin = Path(tempfile.mkdtemp()) / 'plugin'
        self.addCleanup(shutil.rmtree, plugin.parent, True)
        for name in ('kit', 'scripts', '.claude-plugin'):
            shutil.copytree(repo / name, plugin / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(repo / 'kit-manifest.json', plugin / 'kit-manifest.json')
        for path in (plugin / 'kit/PIPELINE.md', plugin / 'kit/web_pipeline/cli.py'):
            crlf(path)
        result = subprocess.run([sys.executable, '-B', str(plugin / 'scripts/pipeline.py'), 'doctor'],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual('PASS', json.loads(result.stdout or '{}').get('status'), result.stdout + result.stderr)
        edited = plugin / 'kit/web_pipeline/cli.py'
        edited.write_bytes(edited.read_bytes() + b'# tampered\r\n')
        result = subprocess.run([sys.executable, '-B', str(plugin / 'scripts/pipeline.py'), 'doctor'],
                                capture_output=True, text=True, timeout=120)
        self.assertIn('mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
