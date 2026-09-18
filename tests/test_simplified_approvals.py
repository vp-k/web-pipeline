"""Real standard lifecycles plus fail-closed protected/legacy approval checks."""
import copy
import json
import unittest

from tests import test_lifecycle
from web_pipeline import autopilot
from web_pipeline.cli import _parser, dispatch
from web_pipeline.common import PipelineError, atomic_json, atomic_text, load_config, read_state
from web_pipeline.local_review import ordinary_work, record_review
from web_pipeline.state import _roles, policy_check, prepare_task, transition
from web_pipeline.runner import run_profile

DECISION = {'choice': 'Keep the scoped fix', 'rationale': 'Reviewed the diff and executed Full evidence',
            'alternatives': ['Broader refactor deferred because it is outside scope'], 'risks': []}


class SimplifiedApprovalTests(unittest.TestCase):
    def setUp(self):
        self.f = test_lifecycle.LifecycleTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root, self.task = self.f.root, self.f.task
        self.config = copy.deepcopy(self.f.config)
        self.config['approval_policy'] = 'standard'
        # Explicit isolated arithmetic command, not a substitute production check.
        self.config['verification']['policy_checks'] = []
        for profile in ('Baseline', 'Fast', 'Full', 'Release'):
            self.config['verification']['requirements']['backend'][profile] = ['unit']
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'standard policy fixture baseline')
        prepare_task(self.root, self.task)

    def review_stage(self):
        self.f.baseline_and_start()
        return self.f.full_and_review()

    def test_standard_t1_manual_done_and_merge_without_trust_or_human_name(self):
        self.assertEqual('claude', read_state(self.root, self.task)['implementer'])
        self.review_stage()
        with self.assertRaisesRegex(PipelineError, 'local review'):
            transition(self.root, self.task, 'DONE')
        decision_path = self.root / 'Docs/Work' / self.task / 'choice.json'
        atomic_json(decision_path, DECISION)
        args = _parser().parse_args(['--root', str(self.root), 'review', '--task', self.task,
                                     '--decision', str(decision_path)])
        result = dispatch(args)
        record = json.loads((self.root / result['path']).read_text())
        self.assertEqual('self_review', record['kind'])
        self.assertNotIn('identity', record)
        self.assertEqual(DECISION, record['decision'])
        transition(self.root, self.task, 'DONE')
        # Even an unusable trust path is irrelevant to ordinary work, not silently
        # accepted as an approval for anything requiring a signature.
        check = policy_check(self.root, gate='merge', trust_path='not-a-trust-file')
        self.assertEqual('PASS', check['status'], check)

    def test_ordinary_requests_need_no_user_approval_but_keep_verification_and_review(self):
        from web_pipeline.user_approval import approval_request
        before = read_state(self.root, self.task)
        self.assertEqual('NO_APPROVAL_REQUIRED', approval_request(self.root, self.task, 'design')['status'])
        self.assertEqual(before, read_state(self.root, self.task))
        with self.assertRaises(PipelineError):
            transition(self.root, self.task, 'READY')
        self.review_stage()
        self.assertEqual('NO_APPROVAL_REQUIRED', approval_request(self.root, self.task, 'review')['status'])
        with self.assertRaisesRegex(PipelineError, 'local review'):
            transition(self.root, self.task, 'DONE')

    def test_request_does_not_hide_new_protected_classification(self):
        from web_pipeline.user_approval import approval_request
        atomic_text(self.root / 'auth_handler.py', '# Newly introduced protected path\n')
        with self.assertRaisesRegex(PipelineError, 'classification'):
            approval_request(self.root, self.task, 'design')

    def test_standard_t2_loop_stops_on_required_merge_failure_without_trust(self):
        from web_pipeline.state import create_task
        self.task = 'FEATURE-002'
        create_task(self.root, self.task, 'Ordinary internal feature', 'T2', ['backend'], base_ref='HEAD')
        directory = self.root / 'Docs/Work' / self.task
        atomic_text(directory / 'BRIEF.md', '# Scope\nCheck arithmetic fixture.\n')
        atomic_text(directory / 'DOR.md', '# Ready\nExplicit fixture acceptance.\n')
        atomic_text(directory / 'PLAN.md', '# Plan\nVerify scoped arithmetic behavior.\n')
        atomic_json(directory / 'ACCEPTANCE.json', {'criteria': [{'id': 'AC-1', 'description': 'Arithmetic works', 'checks': ['unit']}]})
        from tests.planning_fixture import record_fixture_planning
        record_fixture_planning(self.root, self.task)
        prepare_task(self.root, self.task)
        plan = {'objective': 'Complete scoped T2 fixture', 'completion_gate': 'merge',
                'tasks': [{'task_id': self.task, 'depends_on': []}]}
        autopilot.start(self.root, plan)
        ticket = autopilot.advance(self.root)
        self.assertEqual('IMPLEMENT', ticket['action'])
        autopilot.complete(self.root, ticket['token'], 'implemented', DECISION)
        ticket = autopilot.advance(self.root)
        self.assertEqual('REVIEW', ticket['action'])
        autopilot.complete(self.root, ticket['token'], 'reviewed', DECISION)
        result = autopilot.advance(self.root)
        self.assertEqual('WAITING', result['status'], result)
        self.assertEqual('DONE', read_state(self.root, self.task)['status'])
        # Other active DRAFT fixture still blocks the all-task merge gate.
        self.assertEqual('FAIL', result['merge_gate']['status'])
        self.assertTrue(result['merge_gate']['errors'])
        checkpoint = (self.root / autopilot.QUEUE).read_bytes()
        with self.assertRaisesRegex(PipelineError, 'Queue already exists'):
            autopilot.start(self.root, {**plan, 'completion_gate': 'queue'})
        self.assertEqual(checkpoint, (self.root / autopilot.QUEUE).read_bytes())
        autopilot.retry(self.root, self.task, 'Check whether the external gate changed')
        self.assertEqual('WAITING', autopilot.advance(self.root)['status'])
        events = autopilot.status(self.root)['events']
        self.assertTrue(any(e['kind'] == 'DECISION' and e['decision'] == DECISION for e in events))
        self.assertTrue(any(e.get('result', {}).get('merge_gate', {}).get('status') == 'FAIL' for e in events))
        # Complete the actual blocking fixture through its normal gates, then resume.
        self.f.baseline_and_start()
        self.f.full_and_review()
        record_review(self.root, self.f.task, DECISION)
        transition(self.root, self.f.task, 'DONE')
        result = autopilot.advance(self.root)
        self.assertEqual('COMPLETE', result['status'], result)
        self.assertEqual('PASS', result['merge_gate']['status'])
        autopilot.start(self.root, plan)

    def test_sequential_completion_does_not_require_unrelated_task_merge_readiness(self):
        from web_pipeline.state import create_task
        self.review_stage()
        record_review(self.root, self.task, DECISION)
        transition(self.root, self.task, 'DONE')
        create_task(self.root, 'LATER-001', 'Unrelated future work', 'T1', ['backend'], base_ref='HEAD')
        plan = {'objective': 'Finish only the requested task',
                'tasks': [{'task_id': self.task, 'depends_on': []}]}
        autopilot.start(self.root, plan)
        result = autopilot.advance(self.root)
        self.assertEqual('COMPLETE', result['status'], result)
        self.assertEqual('NOT_APPLICABLE', result['merge_gate']['status'])
        self.assertEqual('FAIL', policy_check(self.root, gate='merge')['status'])
        # A new queue can preserve the completed sequential checkpoint.
        old_id = autopilot.status(self.root)['queue_id']
        autopilot.start(self.root, {'objective': 'Now plan the later work',
                                   'tasks': [{'task_id': 'LATER-001', 'depends_on': []}]})
        self.assertTrue((self.root / f'Docs/Work/AUTOPILOT-{old_id}.json').exists())

    def test_missing_or_strict_policy_keeps_legacy_roles_and_rejects_unknown(self):
        state = read_state(self.root, self.task)
        for policy in (None, 'strict'):
            config = copy.deepcopy(self.config)
            if policy is None:
                config.pop('approval_policy')
            else:
                config['approval_policy'] = policy
            self.assertEqual(['Reviewer'], _roles(config, state, 'review'))
            self.assertEqual(['Tech Owner'], _roles(config, {**state, 'risk_tier': 'T2'}, 'design'))
        invalid = {**self.config, 'approval_policy': 'off'}
        atomic_json(self.root / 'pipeline.config.yaml', invalid)
        with self.assertRaises(PipelineError):
            load_config(self.root)

    def test_standard_never_removes_protected_high_risk_or_release_roles(self):
        state = read_state(self.root, self.task)
        for tier in ('T3', 'T4'):
            candidate = {**state, 'risk_tier': tier}
            self.assertFalse(ordinary_work(self.config, candidate))
            self.assertEqual(['Reviewer'], _roles(self.config, candidate, 'review'))
            self.assertEqual(['Tech Owner'], _roles(self.config, candidate, 'design'))
        for change, rule in self.config['risk']['protected_rules'].items():
            candidate = {**state, 'protected_changes': [change]}
            self.assertFalse(ordinary_work(self.config, candidate), change)
            self.assertEqual(['Reviewer'], _roles(self.config, candidate, 'review'))
            self.assertEqual(sorted(rule['roles']), _roles(self.config, candidate, 'design'))
        self.assertEqual(['Release Owner'], _roles(self.config, state, 'release'))

    def test_authentication_cannot_start_without_explicit_owner_decision(self):
        from web_pipeline.state import create_task
        self.config['project']['supported_domains'].append('authentication')
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'fixture authentication coverage')
        task = 'AUTH-001'
        state = create_task(self.root, task, 'Auth fixture', 'T1', ['authentication'], base_ref='HEAD')
        self.assertEqual('T3', state['risk_tier'])
        # Do not invent accepted ADR/design approvals to get past the gate.
        with self.assertRaises(PipelineError):
            record_review(self.root, task, DECISION)
        with self.assertRaises(PipelineError):
            transition(self.root, task, 'READY')
        from web_pipeline.approval import validate_approvals
        with self.assertRaisesRegex(PipelineError, 'missing valid design approval'):
            validate_approvals(self.root, self.config, state,
                               _roles(self.config, state, 'design'), 'design')

    def test_review_requires_real_full_and_nonblank_choices(self):
        with self.assertRaises(PipelineError):
            record_review(self.root, self.task, DECISION)
        self.review_stage()
        for bad in ({**DECISION, 'rationale': ' '}, {**DECISION, 'alternatives': [' ']},
                    {**DECISION, 'alternatives': []}):
            with self.assertRaises(PipelineError):
                record_review(self.root, self.task, bad)

    def test_record_is_preserved_and_rework_requires_new_review(self):
        self.review_stage()
        record = record_review(self.root, self.task, DECISION)
        path = self.root / record['path']
        original = path.read_bytes()
        record_review(self.root, self.task, DECISION)  # idempotent, not overwrite
        self.assertEqual(original, path.read_bytes())
        with self.assertRaisesRegex(PipelineError, 'overwrite'):
            record_review(self.root, self.task, {**DECISION, 'choice': 'Replace history'})
        transition(self.root, self.task, 'IN_PROGRESS')
        run_profile(self.root, self.task, 'Full', run_id='full-002')
        transition(self.root, self.task, 'VERIFYING')
        transition(self.root, self.task, 'REVIEW')
        with self.assertRaisesRegex(PipelineError, 'local review'):
            transition(self.root, self.task, 'DONE')
        record_review(self.root, self.task, DECISION)
        transition(self.root, self.task, 'DONE')
        self.assertEqual(original, path.read_bytes())

    def test_tampered_review_or_code_cannot_pass_done(self):
        self.review_stage()
        result = record_review(self.root, self.task, DECISION)
        path = self.root / result['path']
        original = json.loads(path.read_text())
        atomic_json(path, {**original, 'kind': 'human_approval'})
        with self.assertRaises(PipelineError):
            transition(self.root, self.task, 'DONE')
        atomic_json(path, {**original, 'revision': 999})
        with self.assertRaisesRegex(PipelineError, 'stale'):
            transition(self.root, self.task, 'DONE')
        atomic_json(path, original)
        atomic_text(self.root / 'check.py', 'assert False\n')
        with self.assertRaises(PipelineError):
            transition(self.root, self.task, 'DONE')

    def test_policy_change_stales_prepared_fingerprint(self):
        self.f.baseline_and_start()
        self.config['approval_policy'] = 'strict'
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        checked = policy_check(self.root, task_id=self.task)
        self.assertEqual('FAIL', checked['status'])
        self.assertTrue(any('stale' in error for error in checked['errors']))

    def test_cli_defaults_are_execution_labels_not_human_names(self):
        self.assertEqual('claude', _parser().parse_args(['prepare', '--task', self.task]).implementer)
        self.assertEqual('claude', _parser().parse_args(['loop', 'next']).worker)


if __name__ == '__main__':
    unittest.main()
