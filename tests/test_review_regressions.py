"""Regressions from the full v2 review, using isolated real lifecycle fixtures."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest
import zipfile

from tests import test_lifecycle as lifecycle
from tests import test_execution_integration as execution
from web_pipeline.common import PipelineError, atomic_json, atomic_text, load_config, read_state
from web_pipeline.runner import _validate_argv, run_profile
from web_pipeline.state import archive_task, create_task, policy_check, prepare_task, revise_task, transition

ROOT = Path(__file__).resolve().parents[1] / 'kit'


class ReviewRegressions(unittest.TestCase):
    def fixture(self):
        fixture = lifecycle.LifecycleTests(methodName='test_unrun_baseline_blocks_ready')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def done(self, fixture):
        fixture.baseline_and_start()
        full = fixture.full_and_review()
        fixture.sign_review(full)
        transition(fixture.root, fixture.task, 'DONE', trust_path=fixture.trust)
        return full

    def test_merge_gate_rejects_draft_but_progress_inspection_allows_it(self):
        f = self.fixture()
        self.assertEqual('PASS', policy_check(f.root)['status'])
        self.assertEqual('FAIL', policy_check(f.root, gate='merge')['status'])

    def test_merge_gate_requires_every_active_task_done_and_valid(self):
        f = self.fixture()
        self.done(f)
        self.assertEqual('PASS', policy_check(f.root, gate='merge', trust_path=f.trust)['status'])
        create_task(f.root, 'OTHER-001', 'Unfinished work', 'T1', ['backend'], base_ref='HEAD')
        self.assertEqual('FAIL', policy_check(f.root, gate='merge', trust_path=f.trust)['status'])
        self.assertEqual('FAIL', policy_check(f.root, task_id=f.task, gate='merge', trust_path=f.trust)['status'])

    def test_report_exclusion_cannot_hide_tracked_source(self):
        f = self.fixture()
        config = copy.deepcopy(f.config)
        config['project']['report_root'] = 'src'
        atomic_json(f.root / 'pipeline.config.yaml', config)
        atomic_text(f.root / 'src/main.py', 'value = 1\n')
        f.git('add', 'src/main.py', 'pipeline.config.yaml')
        f.git('commit', '-qm', 'tracked source and unsafe output configuration')
        with self.assertRaises(PipelineError):
            load_config(f.root)

    def test_report_exclusion_cannot_overlap_governance(self):
        f = self.fixture()
        for relative in ('Docs/Work', 'Docs/Architecture', 'web_pipeline/nested'):
            config = copy.deepcopy(f.config)
            config['project']['report_root'] = relative
            atomic_json(f.root / 'pipeline.config.yaml', config)
            with self.subTest(relative=relative), self.assertRaises(PipelineError):
                load_config(f.root)

    def test_baseline_cannot_be_replaced_after_implementation_or_done(self):
        f = self.fixture()
        f.baseline_and_start()
        before = read_state(f.root, f.task)
        with self.assertRaises(PipelineError):
            run_profile(f.root, f.task, 'Baseline', run_id='replacement-baseline')
        self.assertEqual(before, read_state(f.root, f.task))
        full = f.full_and_review()
        f.sign_review(full)
        transition(f.root, f.task, 'DONE', trust_path=f.trust)
        before = read_state(f.root, f.task)
        with self.assertRaises(PipelineError):
            run_profile(f.root, f.task, 'Baseline', run_id='post-done-baseline')
        self.assertEqual(before, read_state(f.root, f.task))

    def test_successful_signed_na_does_not_exhaust_same_failure_budget(self):
        test = execution.ExecutionIntegrationTests(methodName='test_real_signed_exception_runs_and_revalidates_as_not_applicable')
        test.setUp()
        self.addCleanup(test.doCleanups)
        test.test_real_signed_exception_runs_and_revalidates_as_not_applicable()
        f = test.fixture
        transition(f.root, f.task, 'READY', trust_path=f.trust)
        transition(f.root, f.task, 'IN_PROGRESS', trust_path=f.trust)
        for number in range(3):
            summary = run_profile(f.root, f.task, 'Fast', trust_path=f.trust, run_id=f'na-fast-{number}')
            self.assertEqual('PASS', summary['status'])
            self.assertIsNone(summary['failure_fingerprint'])
            self.assertEqual(0, read_state(f.root, f.task)['iteration']['same_failure'])
        self.assertEqual('PASS', run_profile(f.root, f.task, 'Full', trust_path=f.trust, run_id='na-full')['status'])

    def test_acceptance_check_outside_domain_is_executed_by_full(self):
        f = self.fixture()
        atomic_json(f.root / f'Docs/Work/{f.task}/ACCEPTANCE.json', {'criteria': [
            {'id': 'AC-1', 'description': 'Task-specific consumer contract', 'checks': ['contract-consumer']}]})
        prepare_task(f.root, f.task, 'fixture-implementer')
        f.baseline_and_start()
        full = f.full_and_review()
        self.assertIn('contract-consumer', {check['id'] for check in full['checks']})

    def test_prepare_rejects_acceptance_check_that_cannot_run_in_full(self):
        f = self.fixture()
        config = copy.deepcopy(f.config)
        command = dict(config['verification']['commands'][0])
        command.update(id='task-specific', profiles=['Fast'])
        config['verification']['commands'].append(command)
        atomic_json(f.root / 'pipeline.config.yaml', config)
        f.git('add', 'pipeline.config.yaml')
        f.git('commit', '-qm', 'fixture check registration')
        atomic_json(f.root / f'Docs/Work/{f.task}/ACCEPTANCE.json', {'criteria': [
            {'id': 'AC-1', 'description': 'Task-specific check', 'checks': ['task-specific']}]})
        with self.assertRaisesRegex(PipelineError, 'Full'):
            prepare_task(f.root, f.task, 'fixture-implementer')

    def test_blocked_task_requires_revision_to_return_to_draft(self):
        f = self.fixture()
        f.baseline_and_start()
        transition(f.root, f.task, 'BLOCKED')
        before = read_state(f.root, f.task)
        with self.assertRaises(PipelineError):
            transition(f.root, f.task, 'DRAFT')
        self.assertEqual(before, read_state(f.root, f.task))
        revised = revise_task(f.root, f.task, 'Changed acceptance scope')
        self.assertEqual(before['revision'] + 1, revised['revision'])
        self.assertIsNone(revised['baseline_run'])

    def test_duplicate_full_run_id_preserves_entire_state(self):
        f = self.fixture()
        f.baseline_and_start()
        run_profile(f.root, f.task, 'Full', run_id='unique-full')
        before = read_state(f.root, f.task)
        with self.assertRaises(PipelineError):
            run_profile(f.root, f.task, 'Full', run_id='unique-full')
        self.assertEqual(before, read_state(f.root, f.task))

    def test_policy_profile_cannot_pass_when_risk_classification_is_stale(self):
        f = self.fixture()
        f.baseline_and_start()
        atomic_text(f.root / 'new_auth.py', '# Newly affected authentication domain\n')
        self.assertEqual('FAIL', policy_check(f.root)['status'])
        with self.assertRaises(PipelineError):
            run_profile(f.root, f.task, 'Policy', run_id='stale-policy')

    def test_shell_executable_suffixes_and_combined_flags_cannot_bypass_policy(self):
        for argv in (['sh', '-lc', 'false; true'], ['sh.exe', '-c', 'false; true'],
                     ['bash.exe', '-lc', 'false; true'], ['cmd.exe', '/c', 'exit 0']):
            with self.subTest(argv=argv), self.assertRaises(PipelineError):
                _validate_argv({'id': 'shell-test', 'argv': argv, 'environment': 'test'})
        for argv in (['sh', 'verify.sh'], ['powershell.exe', '-NoProfile', '-File', 'verify.ps1']):
            self.assertEqual(argv, _validate_argv({'id': 'script-test', 'argv': argv, 'environment': 'test'}))

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell adapter integration')
    def test_powershell_adapter_works_outside_its_repository(self):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(ROOT / 'Scripts/policy-check.ps1'),
                                 '-RootPath', str(ROOT), '-Kit'], cwd=ROOT.parent,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_archive_preserves_verified_dirty_source_bytes(self):
        f = self.fixture()
        f.baseline_and_start()
        code = b'assert 8 * 8 == 64\nprint("verified uncommitted source")\n'
        atomic_text(f.root / 'check.py', code.decode())
        full = f.full_and_review()
        f.sign_review(full)
        transition(f.root, f.task, 'DONE', trust_path=f.trust)
        archived = archive_task(f.root, f.task, trust_path=f.trust)
        target = f.root / archived['path']
        with zipfile.ZipFile(target / 'SOURCE.zip') as bundle:
            self.assertEqual(code, bundle.read('check.py'))
        manifest = json.loads((target / 'SOURCE_MANIFEST.json').read_text())
        self.assertEqual(full['snapshot']['tree_digest'], manifest['tree_digest'])
        from web_pipeline.source_bundle import verify_source_bundle
        verify_source_bundle(target, full['snapshot']['tree_digest'])
        with zipfile.ZipFile(target / 'SOURCE.zip', 'w') as bundle:
            bundle.writestr('check.py', b'replacement source')
        with self.assertRaises(PipelineError):
            verify_source_bundle(target, full['snapshot']['tree_digest'])

    def test_source_bundle_rejects_potential_local_credentials(self):
        from web_pipeline.common import code_snapshot
        from web_pipeline.source_bundle import capture_source_bundle
        f = self.fixture()
        atomic_text(f.root / '.env', 'TEST_ONLY_PLACEHOLDER=not-a-real-secret\n')
        target = f.root / 'Docs/Work' / f.task
        with self.assertRaisesRegex(PipelineError, 'credential'):
            capture_source_bundle(f.root, f.config, target, code_snapshot(f.root, f.config)['tree_digest'])
        self.assertFalse((target / 'SOURCE.zip').exists())

    def test_ci_resolves_numeric_artifact_reference_and_prevents_kit_downgrade(self):
        from web_pipeline.ci import resolve_context
        f = self.fixture()
        atomic_json(f.root / 'Docs/Work/CI_EVIDENCE.json', {'workflow_run_id': '123456'})
        context = resolve_context(f.root, 'HEAD')
        self.assertTrue(context['project'])
        self.assertEqual('123456', context['evidence_run_id'])
        for invalid in ('123; echo x', '0', '../run'):
            with self.subTest(invalid=invalid), self.assertRaises(PipelineError):
                resolve_context(f.root, 'HEAD', invalid)
        config = copy.deepcopy(f.config)
        config['project'].update(mode='kit', ready=False)
        atomic_json(f.root / 'pipeline.config.yaml', config)
        with self.assertRaisesRegex(PipelineError, 'kit mode'):
            resolve_context(f.root, 'HEAD', '123456')

    def test_ci_project_without_artifact_reference_fails_closed(self):
        from web_pipeline.ci import resolve_context
        f = self.fixture()
        with self.assertRaises(PipelineError):
            resolve_context(f.root, 'HEAD')

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell installer integration')
    def test_powershell_installer_works_outside_its_repository(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix='adapter-install-') as sandbox:
            target = Path(sandbox) / 'adopted'
            result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(ROOT / 'Scripts/Install-To-Project.ps1'),
                                     '-TargetPath', str(target)], cwd=ROOT.parent,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue((target / 'web_pipeline/cli.py').is_file())


if __name__ == '__main__':
    unittest.main()
