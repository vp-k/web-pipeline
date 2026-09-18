"""Real lifecycle regressions: no mocked verification or approval decisions."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from web_pipeline.common import (PipelineError, atomic_json, atomic_text, hash_file,
                                load_config, read_state, write_state)
from web_pipeline.state import create_task, transition, policy_check, attach_record, prepare_task
from web_pipeline.runner import run_profile, validate_run

ROOT = Path(__file__).resolve().parents[1] / 'kit'


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix='web-pipeline-lifecycle-')
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name) / 'project'
        self.root.mkdir()
        config = copy.deepcopy(load_config(ROOT, kit=True))
        # Keep the existing signed-approval regressions on their original policy.
        # New standard-policy behavior has a separate real lifecycle suite.
        config['approval_policy'] = 'strict'
        # Retain explicit hard-budget regression coverage; warn has its own suite.
        config['iteration_limits']['time_budget_mode'] = 'enforce'
        config['project'].update(mode='project', ready=True, supported_domains=['backend'])
        # Isolated fixture: the checker tests arithmetic rather than claiming real
        # application checks. Production config retains real domain requirements.
        atomic_text(self.root / 'check.py', 'assert 2 + 2 == 4\nprint("fixture check passed")\n')
        for command in config['verification']['commands']:
            command.update(enabled=True, argv=[sys.executable,'check.py'], artifacts=[])
        for path in config['sources'].values():
            atomic_text(self.root / path, 'Fixture source specification revision one.\n')
        atomic_json(self.root / 'pipeline.config.yaml', config)
        self.config = config
        self.git('init','-q')
        self.git('config','user.email','fixture@example.invalid')
        self.git('config','user.name','TEST ONLY')
        self.git('config','core.autocrlf','false')
        self.git('add','.')
        self.git('commit','-qm','fixture baseline')
        self.task = 'TASK-001'
        create_task(self.root,self.task,'Fixture lifecycle','T1',['backend'],base_ref='HEAD')
        directory = self.root / 'Docs/Work' / self.task
        atomic_text(directory / 'BRIEF.md', '# Fixture\n\nVerify the explicit fixture check.\n')
        atomic_text(directory / 'DOR.md', '# Ready criteria\n\nScope and check are defined; Baseline precedes implementation.\n')
        atomic_json(directory / 'ACCEPTANCE.json', {'criteria':[{'id':'AC-1','description':'Arithmetic fixture executes successfully','checks':['unit']}]})
        from web_pipeline.state import prepare_task
        from tests.planning_fixture import record_fixture_planning
        record_fixture_planning(self.root, self.task)
        prepare_task(self.root,self.task,'fixture-implementer')
        self.key = Ed25519PrivateKey.generate()  # isolated fixture; never a real approval
        self.trust = Path(self.sandbox.name) / 'trust.json'
        public = base64.b64encode(self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
        atomic_json(self.trust, {'identities':{'fixture-reviewer':{'type':'human','roles':['Reviewer'],'public_key':public}}})

    def git(self,*arguments):
        return subprocess.run(['git','-C',str(self.root),*arguments],check=True,capture_output=True,text=True).stdout.strip()

    def baseline_and_start(self):
        summary = run_profile(self.root,self.task,'Baseline',run_id='baseline-001')
        self.assertEqual('PASS',summary['status'],summary)
        transition(self.root,self.task,'READY')
        transition(self.root,self.task,'IN_PROGRESS')

    def full_and_review(self):
        summary = run_profile(self.root,self.task,'Full',run_id='full-001')
        self.assertEqual('PASS',summary['status'],summary)
        state = read_state(self.root,self.task)
        if state['status'] == 'IN_PROGRESS':
            transition(self.root,self.task,'VERIFYING')
        transition(self.root,self.task,'REVIEW')
        return summary

    def sign_review(self, summary):
        state = read_state(self.root,self.task)
        now = datetime.now(timezone.utc)
        payload = {'task_id':self.task,'revision':state['revision'],'fingerprint':state['fingerprint'],
                   'phase':'review','role':'Reviewer','identity':'fixture-reviewer',
                   'approved_utc':(now-timedelta(seconds=1)).isoformat(),
                   'expires_utc':(now+timedelta(hours=1)).isoformat(),'outcome':'APPROVED','scope':[],
                   'tree_digest':summary['snapshot']['tree_digest'],'run_id':summary['run_id'],
                   'run_digest':hash_file(self.root / self.config['project']['report_root'] / summary['run_id'] / 'summary.json'), 'conditions':[]}
        signature = base64.b64encode(self.key.sign(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())).decode()
        relative = f'Docs/Work/{self.task}/review.json'
        atomic_json(self.root / relative,{'payload':payload,'signature':signature})
        state['approvals'] = [relative]
        write_state(self.root,state)

    def test_executed_lifecycle_reaches_done_with_signed_review(self):
        self.baseline_and_start()
        summary = self.full_and_review()
        with self.assertRaises(PipelineError):
            transition(self.root,self.task,'DONE')
        self.sign_review(summary)
        result = transition(self.root,self.task,'DONE',trust_path=self.trust)
        self.assertEqual('DONE',result['status'])
        policy = policy_check(self.root,trust_path=self.trust)
        self.assertEqual('PASS',policy['status'],policy)

    def test_fabricated_done_and_run_pointer_fail_all_task_scan(self):
        state = read_state(self.root,self.task)
        state.update(status='DONE',full_run='nonexistent-run')
        write_state(self.root,state)
        result = policy_check(self.root,trust_path=self.trust)
        self.assertEqual('FAIL',result['status'])

    def test_unrun_baseline_blocks_ready(self):
        with self.assertRaises(PipelineError):
            transition(self.root,self.task,'READY')

    def test_modified_evidence_blocks_done(self):
        self.baseline_and_start()
        summary = self.full_and_review()
        self.sign_review(summary)
        run_dir = self.root / self.config['project']['report_root'] / summary['run_id']
        atomic_text(run_dir / summary['artifacts'][0]['path'],'tampered evidence')
        with self.assertRaises(PipelineError):
            transition(self.root,self.task,'DONE',trust_path=self.trust)

    def test_code_change_stales_full(self):
        self.baseline_and_start()
        summary = self.full_and_review()
        atomic_text(self.root / 'check.py','assert False\n')
        with self.assertRaises(PipelineError):
            validate_run(self.root,self.config,read_state(self.root,self.task),summary['run_id'],'Full')

    def test_reused_run_id_rejected_without_overwrite(self):
        self.baseline_and_start()
        run_profile(self.root,self.task,'Fast',run_id='once-001')
        path = self.root / self.config['project']['report_root'] / 'once-001/summary.json'
        contents = path.read_bytes()
        with self.assertRaises(PipelineError):
            run_profile(self.root,self.task,'Fast',run_id='once-001')
        self.assertEqual(contents,path.read_bytes())

    def test_rehashed_evidence_invalidates_human_approval(self):
        self.baseline_and_start()
        summary = self.full_and_review()
        self.sign_review(summary)
        run_dir = self.root / self.config['project']['report_root'] / summary['run_id']
        path = run_dir / 'summary.json'
        modified = json.loads(path.read_text())
        entry = modified['artifacts'][0]
        atomic_text(run_dir / entry['path'],'replacement log')
        entry.update(size=(run_dir / entry['path']).stat().st_size,sha256=hash_file(run_dir / entry['path']))
        atomic_json(path,modified)
        with self.assertRaises(PipelineError):
            transition(self.root,self.task,'DONE',trust_path=self.trust)

    def test_missing_log_manifest_cannot_be_relabelled_as_pass(self):
        self.baseline_and_start()
        summary = self.full_and_review()
        path = self.root / self.config['project']['report_root'] / summary['run_id'] / 'summary.json'
        modified = json.loads(path.read_text())
        modified['artifacts'] = []
        for check in modified['checks']:
            check['log'] = None
        atomic_json(path,modified)
        with self.assertRaises(PipelineError):
            validate_run(self.root,self.config,read_state(self.root,self.task),summary['run_id'],'Full')

    def test_release_without_done_t4_never_executes(self):
        with self.assertRaises(PipelineError):
            run_profile(self.root,self.task,'Release',run_id='release-forbidden')
        self.assertFalse((self.root / self.config['project']['report_root'] / 'release-forbidden').exists())

    def test_scope_edit_invalidates_prepared_baseline(self):
        self.baseline_and_start()
        atomic_text(self.root / f'Docs/Work/{self.task}/BRIEF.md', 'Changed scope after READY')
        with self.assertRaises(PipelineError):
            run_profile(self.root,self.task,'Full',run_id='stale-scope')

    def test_attach_signed_review_registers_without_changing_workflow_state(self):
        self.baseline_and_start()
        summary = self.full_and_review()
        self.sign_review(summary)
        state = read_state(self.root,self.task)
        state['approvals'] = []
        write_state(self.root,state)
        relative = f'Docs/Work/{self.task}/review.json'
        result = attach_record(self.root,self.task,'approval',relative)
        self.assertEqual('REVIEW',result['status'])
        self.assertEqual([relative],result['approvals'])
        self.assertEqual([relative],attach_record(self.root,self.task,'approval',relative)['approvals'])
        self.assertEqual('DONE',transition(self.root,self.task,'DONE',trust_path=self.trust)['status'])

    def test_prepare_rejects_unfilled_template(self):
        atomic_text(self.root / f'Docs/Work/{self.task}/BRIEF.md','# Brief\n\nTBD\n')
        with self.assertRaisesRegex(PipelineError,'unfilled'):
            prepare_task(self.root,self.task,'fixture-implementer')

    def test_prepare_rejects_duplicate_acceptance_ids(self):
        criterion = {'id':'AC-1','description':'Fixture check','checks':['unit']}
        atomic_json(self.root / f'Docs/Work/{self.task}/ACCEPTANCE.json',{'criteria':[criterion,criterion]})
        with self.assertRaisesRegex(PipelineError,'unique'):
            prepare_task(self.root,self.task,'fixture-implementer')


if __name__ == '__main__':
    unittest.main()
