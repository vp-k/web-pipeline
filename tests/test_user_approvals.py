"""Real protected standard lifecycles; fixture messages are not real approvals."""
import copy
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import patch

from tests import test_lifecycle
from web_pipeline import autopilot
from web_pipeline.approval import validate_approvals, validate_exception
from web_pipeline.cli import _parser, dispatch
from web_pipeline.common import (PipelineError, atomic_json, atomic_text, code_snapshot,
                                 hash_file, read_state, write_state)
from web_pipeline.runner import run_profile, validate_run
from web_pipeline.state import (_roles, attach_record, create_task, policy_check,
                                prepare_task, revise_task, transition)
from web_pipeline.user_approval import approval_request, record_approval


class UserApprovalTests(unittest.TestCase):
    def setUp(self):
        self.f = test_lifecycle.LifecycleTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.config = copy.deepcopy(self.f.config)
        self.config['approval_policy'] = 'standard'
        self.config['project']['supported_domains'] = ['backend', 'infrastructure', 'authentication', 'security']
        # These isolated checks test arithmetic, not production security coverage.
        self.config['verification']['policy_checks'] = []
        for requirements in self.config['verification']['requirements'].values():
            for phase in ('Baseline', 'Fast', 'Full', 'Release'):
                requirements[phase] = ['unit']
        for rule in self.config['risk']['protected_rules'].values():
            for phase in ('Baseline', 'Fast', 'Full', 'Release'):
                rule['checks'][phase] = ['unit']
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'isolated standard approval fixture')
        self.task = self.new_task('PROTECTED-003', 'T3')

    def new_task(self, task, tier):
        state = create_task(self.root, task, 'Explicit protected fixture', tier,
                            ['backend', 'authentication', 'infrastructure'],
                            protected_changes=['core_architecture'], base_ref='HEAD')
        directory = self.root / 'Docs/Work' / task
        for name in ('BRIEF.md', 'DOR.md', 'PLAN.md', 'EXEC_PLAN.md', 'RELEASE.md'):
            if name != 'RELEASE.md' or tier == 'T4':
                atomic_text(directory / name, '# Fixture scope\nLocal arithmetic only; no production environment.\n')
        atomic_json(directory / 'ACCEPTANCE.json', {'criteria': [
            {'id': 'AC-1', 'description': 'Arithmetic check executes', 'checks': ['unit']}]})
        adr = f'Docs/Work/{task}/ADR-FIXTURE.json'
        atomic_json(self.root / adr, {'id': 'ADR-FIXTURE', 'title': 'Fixture decision',
            'status': 'ACCEPTED', 'task_id': task, 'revision': 1, 'scope': state['protected_changes'],
            'context': 'Ephemeral test only', 'decision': 'Verify arithmetic',
            'risks': 'No real service involved', 'recovery': 'Discard fixture'})
        attach_record(self.root, task, 'adr', adr)
        from tests.planning_fixture import record_fixture_planning
        record_fixture_planning(self.root, task)
        prepare_task(self.root, task)
        return task

    def consent(self, phase, **kwargs):
        request = approval_request(self.root, self.task, phase, kwargs.get('check_id'))['request']
        return {**request, 'outcome': 'APPROVED',
                'user_message': 'TEST FIXTURE: I approve the specifically presented decision.',
                'presented_scope': f'TEST FIXTURE: {phase} for {self.task}, revision {request["revision"]}; no production execution.',
                'source_reference': 'isolated unittest conversation, not a real user approval', **kwargs}

    def start(self):
        baseline = run_profile(self.root, self.task, 'Baseline')
        self.assertEqual('PASS', baseline['status'])
        record_approval(self.root, self.task, self.consent('design'))
        transition(self.root, self.task, 'READY')
        transition(self.root, self.task, 'IN_PROGRESS')

    def review(self):
        self.start()
        full = run_profile(self.root, self.task, 'Full')
        self.assertEqual('PASS', full['status'])
        transition(self.root, self.task, 'VERIFYING')
        transition(self.root, self.task, 'REVIEW')
        return full

    def test_t3_ready_done_and_policy_without_identity_or_trust(self):
        self.review()
        with self.assertRaisesRegex(PipelineError, 'missing valid review'):
            transition(self.root, self.task, 'DONE')
        data = self.consent('review')
        result = record_approval(self.root, self.task, data)
        record = json.loads((self.root / result['path']).read_text())
        self.assertNotIn('identity', record['payload'])
        self.assertNotIn('signature', record)
        self.assertEqual('local_transcription', record['assurance'])
        self.assertEqual(data, record['payload'])
        transition(self.root, self.task, 'DONE')
        checked = policy_check(self.root, task_id=self.task)
        self.assertEqual('PASS', checked['status'], checked)
        self.assertEqual('T3', read_state(self.root, self.task)['risk_tier'])

    def test_request_is_read_only_and_receipt_never_manufactures_baseline(self):
        before = read_state(self.root, self.task)
        data = self.consent('design')
        self.assertEqual(before, read_state(self.root, self.task))
        result = record_approval(self.root, self.task, data)
        after = read_state(self.root, self.task)
        self.assertEqual('DRAFT', result['task_status'])
        self.assertIsNone(after['baseline_run'])
        self.assertEqual(before['iteration'], after['iteration'])
        self.assertFalse(result['production_authorized'])
        with self.assertRaises(PipelineError):
            transition(self.root, self.task, 'READY')

    def test_missing_user_decision_still_blocks_after_baseline(self):
        run_profile(self.root, self.task, 'Baseline')
        with self.assertRaisesRegex(PipelineError, 'missing valid design'):
            transition(self.root, self.task, 'READY')

    def test_receipt_is_idempotent_and_can_be_reattached(self):
        data = self.consent('design')
        first = record_approval(self.root, self.task, data)
        original = (self.root / first['path']).read_bytes()
        second = record_approval(self.root, self.task, data)
        self.assertEqual(first, second)
        self.assertEqual(original, (self.root / first['path']).read_bytes())
        state = read_state(self.root, self.task)
        self.assertEqual(1, len(state['approvals']))
        state['approvals'] = []
        write_state(self.root, state)
        attach_record(self.root, self.task, 'approval', first['path'])
        self.assertEqual([first['path']], read_state(self.root, self.task)['approvals'])

    def test_repeated_request_reports_existing_consent_without_writes(self):
        self.assertEqual('AWAITING_USER', approval_request(self.root, self.task, 'design')['status'])
        saved = record_approval(self.root, self.task, self.consent('design'))
        before = read_state(self.root, self.task)
        receipt = (self.root / saved['path']).read_bytes()
        for _ in range(2):
            self.assertEqual('SATISFIED', approval_request(self.root, self.task, 'design')['status'])
        self.assertEqual(before, read_state(self.root, self.task))
        self.assertEqual(receipt, (self.root / saved['path']).read_bytes())
        (self.root / saved['path']).unlink()  # simulate missing evidence in the isolated fixture
        self.assertEqual('AWAITING_USER', approval_request(self.root, self.task, 'design')['status'])

    def sign_fixture_request(self, request):
        # Ephemeral fixture identities/keys only; never a real approval.
        trust = json.loads(self.f.trust.read_text(encoding='utf-8'))
        trust['identities']['fixture-reviewer']['roles'] = sorted(
            set(trust['identities']['fixture-reviewer']['roles']) | set(request['roles']))
        atomic_json(self.f.trust, trust)
        now = datetime.now(timezone.utc)
        for index, role in enumerate(request['roles']):
            payload = {key: value for key, value in request.items() if key != 'roles'}
            payload.update(role=role, identity='fixture-reviewer', outcome='APPROVED',
                           approved_utc=(now-timedelta(seconds=2)).isoformat(),
                           expires_utc=(now+timedelta(hours=1)).isoformat())
            if request['phase'] == 'exception':
                payload['reason'] = 'Isolated failing arithmetic fixture only'
            signature = base64.b64encode(self.f.key.sign(json.dumps(
                payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())).decode()
            relative = f'Docs/Work/{self.task}/signed-{request["phase"]}-{index}.json'
            atomic_json(self.root / relative, {'payload': payload, 'signature': signature})
            attach_record(self.root, self.task, 'exception' if request['phase'] == 'exception' else 'approval', relative)

    def test_explicit_trust_reuses_signed_design_and_exception_via_cli(self):
        with patch.dict(os.environ):
            os.environ.pop('WEB_PIPELINE_TRUST', None)
            for phase in ('design', 'exception'):
                with self.subTest(phase=phase):
                    check_id = 'unit' if phase == 'exception' else None
                    request = approval_request(self.root, self.task, phase, check_id)['request']
                    self.sign_fixture_request(request)
                    args = ['--root', str(self.root), 'approval-request', '--task', self.task,
                            '--phase', phase, '--trust', str(self.f.trust)]
                    if check_id:
                        args += ['--check-id', check_id]
                    before = read_state(self.root, self.task)
                    self.assertEqual('SATISFIED', dispatch(_parser().parse_args(args))['status'])
                    self.assertEqual(before, read_state(self.root, self.task))
                    self.assertEqual('AWAITING_USER', approval_request(self.root, self.task, phase, check_id)['status'])
                    trusted = json.loads(self.f.trust.read_text(encoding='utf-8'))
                    untrusted = copy.deepcopy(trusted)
                    untrusted['identities']['unrelated-fixture'] = untrusted['identities'].pop('fixture-reviewer')
                    atomic_json(self.f.trust, untrusted)
                    self.assertEqual('AWAITING_USER', dispatch(_parser().parse_args(args))['status'])
                    atomic_json(self.f.trust, trusted)

    def test_explicit_trust_validates_signed_exception_in_review_prerequisites(self):
        with patch.dict(os.environ):
            os.environ.pop('WEB_PIPELINE_TRUST', None)
            self.start()
            atomic_text(self.root / 'check.py', 'assert False, "isolated exception fixture"\n')
            request = approval_request(self.root, self.task, 'exception', 'unit')['request']
            self.sign_fixture_request(request)
            full = run_profile(self.root, self.task, 'Full', trust_path=self.f.trust)
            self.assertEqual('PASS', full['status'], full)
            transition(self.root, self.task, 'VERIFYING', trust_path=self.f.trust)
            transition(self.root, self.task, 'REVIEW', trust_path=self.f.trust)
            args = ['--root', str(self.root), 'approval-request', '--task', self.task,
                    '--phase', 'review', '--trust', str(self.f.trust)]
            result = dispatch(_parser().parse_args(args))
            self.assertEqual('AWAITING_USER', result['status'])
            self.sign_fixture_request(result['request'])
            self.assertEqual('SATISFIED', dispatch(_parser().parse_args(args))['status'])
            # The following receipt is synthetic test data, not actual consent.
            data = {**result['request'], 'outcome': 'APPROVED',
                    'user_message': 'TEST FIXTURE: accept the presented review.',
                    'presented_scope': 'TEST FIXTURE: current review only, no production authority.',
                    'source_reference': 'isolated test, not an actual user decision'}
            record = self.root / f'Docs/Work/{self.task}/review-input.json'
            atomic_json(record, data)
            approved = dispatch(_parser().parse_args([
                '--root', str(self.root), 'approve', '--task', self.task,
                '--record', str(record), '--trust', str(self.f.trust)]))
            self.assertEqual('RECORDED', approved['status'])
            self.assertEqual('REVIEW', read_state(self.root, self.task)['status'])

    def test_request_keeps_partial_or_invalid_consent_pending(self):
        data = self.consent('design')
        record_approval(self.root, self.task, {**data, 'roles': data['roles'][:1]})
        result = approval_request(self.root, self.task, 'design')
        self.assertEqual('AWAITING_USER', result['status'])
        self.assertIn('missing valid design', result['reason'])
        self.assertEqual(data['roles'], result['request']['roles'])
        path = self.root / f'Docs/Work/{self.task}/condition.txt'
        atomic_text(path, 'fixture evidence')
        condition = {'description': 'Fixture condition', 'status': 'PASS',
                     'evidence': path.relative_to(self.root).as_posix(), 'sha256': hash_file(path)}
        record_approval(self.root, self.task, {**data, 'conditions': [condition]})
        self.assertEqual('SATISFIED', approval_request(self.root, self.task, 'design')['status'])
        atomic_text(path, 'changed evidence')
        self.assertEqual('AWAITING_USER', approval_request(self.root, self.task, 'design')['status'])

    def test_exception_request_reuses_only_the_exact_approved_check(self):
        record_approval(self.root, self.task, self.consent('exception', check_id='unit', reason='Fixture-only exception'))
        self.assertEqual('SATISFIED', approval_request(self.root, self.task, 'exception', 'unit')['status'])
        self.assertEqual('AWAITING_USER', approval_request(self.root, self.task, 'exception', 'lint')['status'])

    def test_review_request_needs_its_own_current_run_decision(self):
        self.review()
        self.assertEqual('AWAITING_USER', approval_request(self.root, self.task, 'review')['status'])
        before = read_state(self.root, self.task)
        self.assertEqual('CHECK_EXISTING_CONSENT', approval_request(self.root, self.task, 'review')['next_action'])
        self.assertEqual(before, read_state(self.root, self.task))
        record_approval(self.root, self.task, self.consent('review'))
        self.assertEqual('SATISFIED', approval_request(self.root, self.task, 'review')['status'])
        self.assertEqual('CONTINUE', approval_request(self.root, self.task, 'review')['next_action'])
        transition(self.root, self.task, 'IN_PROGRESS')
        self.assertEqual('PASS', run_profile(self.root, self.task, 'Full')['status'])
        transition(self.root, self.task, 'VERIFYING')
        transition(self.root, self.task, 'REVIEW')
        self.assertEqual('AWAITING_USER', approval_request(self.root, self.task, 'review')['status'])

    def test_missing_blank_refused_or_ai_approval_fields_are_rejected(self):
        data = self.consent('design')
        bad_inputs = [{**data, field: ' '} for field in ('user_message', 'presented_scope', 'source_reference')]
        bad_inputs += [{**data, 'outcome': 'REFUSED'}, {**data, 'identity': 'fake-owner'},
                       {**data, 'roles': []}, {**data, 'kind': 'self_review'}]
        for candidate in bad_inputs:
            with self.subTest(candidate=candidate), self.assertRaises(PipelineError):
                record_approval(self.root, self.task, candidate)
        self.assertEqual([], read_state(self.root, self.task)['approvals'])

    def test_wrong_task_revision_fingerprint_or_phase_cannot_be_rebound(self):
        data = self.consent('design')
        for key, value in [('task_id', 'ANOTHER-01'), ('revision', 55),
                           ('fingerprint', '0' * 64), ('phase', 'review')]:
            with self.subTest(key=key), self.assertRaises(PipelineError):
                record_approval(self.root, self.task, {**data, key: value})

    def test_source_edits_and_revision_withdrawal_stale_old_consent(self):
        data = self.consent('design')
        saved = record_approval(self.root, self.task, data)
        original = (self.root / saved['path']).read_bytes()
        source = self.root / self.config['sources']['feature_spec']
        atomic_text(source, 'Changed acceptance scope\n')
        with self.assertRaisesRegex(PipelineError, 'fingerprint'):
            record_approval(self.root, self.task, data)
        revise_task(self.root, self.task, 'Fixture user withdrew approval')
        self.assertEqual([], read_state(self.root, self.task)['approvals'])
        self.assertEqual(original, (self.root / saved['path']).read_bytes())
        with self.assertRaises(PipelineError):
            record_approval(self.root, self.task, data)

    def test_partial_roles_or_scope_do_not_satisfy_ready(self):
        run_profile(self.root, self.task, 'Baseline')
        data = self.consent('design')
        self.assertGreater(len(data['roles']), 1)
        record_approval(self.root, self.task, {**data, 'roles': data['roles'][:1]})
        with self.assertRaisesRegex(PipelineError, 'missing valid design'):
            transition(self.root, self.task, 'READY')
        record_approval(self.root, self.task, {**data, 'scope': []})
        with self.assertRaisesRegex(PipelineError, 'scope'):
            transition(self.root, self.task, 'READY')

    def test_conditions_require_pass_and_current_evidence_hash(self):
        data = self.consent('design')
        path = self.root / f'Docs/Work/{self.task}/condition.txt'
        atomic_text(path, 'Fixture condition actually inspected\n')
        condition = {'description': 'Fixture check', 'status': 'PASS',
                     'evidence': path.relative_to(self.root).as_posix(), 'sha256': hash_file(path)}
        for invalid in ({**condition, 'status': 'NOT_RUN'}, {**condition, 'sha256': '0' * 64},
                        {**condition, 'evidence': '../outside.txt'}):
            with self.assertRaises(PipelineError):
                record_approval(self.root, self.task, {**data, 'conditions': [invalid]})
        record_approval(self.root, self.task, {**data, 'conditions': [condition]})
        atomic_text(path, 'Changed evidence\n')
        state = read_state(self.root, self.task)
        with self.assertRaises(PipelineError):
            validate_approvals(self.root, self.config, state, _roles(self.config, state, 'design'), 'design')

    def test_strict_and_legacy_reject_chat_even_with_valid_trust(self):
        data = self.consent('design')
        result = record_approval(self.root, self.task, data)
        state = read_state(self.root, self.task)
        for policy in ('strict', None):
            config = copy.deepcopy(self.config)
            if policy:
                config['approval_policy'] = policy
            else:
                config.pop('approval_policy')
            with self.assertRaises(PipelineError):
                validate_approvals(self.root, config, state, ['Tech Owner'], 'design', self.f.trust)
            atomic_json(self.root / 'pipeline.config.yaml', config)
            with self.assertRaises(PipelineError):
                record_approval(self.root, self.task, data)
            with self.assertRaisesRegex(PipelineError, 'Strict'):
                attach_record(self.root, self.task, 'approval', result['path'])

    def test_old_full_receipt_cannot_approve_a_new_full_or_changed_summary(self):
        full = self.review()
        old = self.consent('review')
        receipt = record_approval(self.root, self.task, old)
        path = self.root / self.config['project']['report_root'] / full['run_id'] / 'summary.json'
        raw = path.read_bytes()
        parsed = json.loads(raw)
        parsed['duration_ms'] = parsed.get('duration_ms', 0) + 1
        atomic_json(path, parsed)
        state = read_state(self.root, self.task)
        with self.assertRaisesRegex(PipelineError, 'summary bytes'):
            validate_approvals(self.root, self.config, state, ['Reviewer'], 'review',
                               snapshot=code_snapshot(self.root, self.config), run_id=full['run_id'])
        # Restore the original fixture report before real rework/reverification.
        path.write_bytes(raw)
        transition(self.root, self.task, 'IN_PROGRESS')
        run_profile(self.root, self.task, 'Full')
        transition(self.root, self.task, 'VERIFYING')
        transition(self.root, self.task, 'REVIEW')
        with self.assertRaises(PipelineError):
            record_approval(self.root, self.task, old)
        with self.assertRaises(PipelineError):
            transition(self.root, self.task, 'DONE')
        self.assertTrue((self.root / receipt['path']).is_file())

    def test_t4_release_needs_separate_full_bound_consent_not_production_permission(self):
        self.task = self.new_task('PROTECTED-004', 'T4')
        self.review()
        record_approval(self.root, self.task, self.consent('review'))
        transition(self.root, self.task, 'DONE')
        with self.assertRaisesRegex(PipelineError, 'missing valid release'):
            run_profile(self.root, self.task, 'Release')
        data = self.consent('release')
        self.assertIn('Release Owner', data['roles'])
        result = record_approval(self.root, self.task, data)
        self.assertFalse(result['production_authorized'])
        release = run_profile(self.root, self.task, 'Release')
        self.assertEqual('PASS', release['status'])
        self.assertEqual('READY', read_state(self.root, self.task)['release_status'])

    def test_exception_is_check_specific_and_remains_not_applicable(self):
        self.start()
        data = self.consent('exception', check_id='unit', reason='Explicit fixture-only exception to arithmetic check')
        record_approval(self.root, self.task, data)
        full = run_profile(self.root, self.task, 'Full')
        self.assertEqual('PASS', full['status'])
        self.assertEqual('NOT_APPLICABLE', full['checks'][0]['status'])
        self.assertIsNone(full['checks'][0]['exit_code'])
        state = read_state(self.root, self.task)
        validate_run(self.root, self.config, state, full['run_id'], 'Full')
        with self.assertRaises(PipelineError):
            validate_exception(self.root, self.config, state, 'lint')
        with self.assertRaises(PipelineError):
            record_approval(self.root, self.task, {**data, 'reason': ' '})

    def test_cli_requests_and_records_without_identity_or_trust_options(self):
        request = dispatch(_parser().parse_args(['--root', str(self.root), 'approval-request',
                                                '--task', self.task, '--phase', 'design']))
        self.assertEqual('AWAITING_USER', request['status'])
        data = self.consent('design')
        path = self.root / f'Docs/Work/{self.task}/input.json'
        atomic_json(path, data)
        result = dispatch(_parser().parse_args(['--root', str(self.root), 'approve',
                                               '--task', self.task, '--record', str(path)]))
        self.assertEqual('RECORDED', result['status'])

    def test_loop_resumes_after_receipts_and_keeps_advisory_review_separate(self):
        decision = {'choice': 'Retain fixture', 'rationale': 'Arithmetic evidence inspected',
                    'alternatives': ['No scope expansion'], 'risks': []}
        autopilot.start(self.root, {'objective': 'Finish protected fixture',
                                   'tasks': [{'task_id': self.task, 'depends_on': []}]})
        self.assertEqual('WAITING', autopilot.advance(self.root)['status'])
        record_approval(self.root, self.task, self.consent('design'))
        autopilot.retry(self.root, self.task, 'Fixture scoped user decision recorded')
        ticket = autopilot.advance(self.root)
        self.assertEqual('IMPLEMENT', ticket['action'])
        autopilot.complete(self.root, ticket['token'], 'implemented', decision)
        ticket = autopilot.advance(self.root)
        self.assertEqual('REVIEW', ticket['action'])
        autopilot.complete(self.root, ticket['token'], 'reviewed', decision)
        self.assertEqual('WAITING', autopilot.advance(self.root)['status'])
        record_approval(self.root, self.task, self.consent('review'))
        autopilot.retry(self.root, self.task, 'Fixture review acceptance recorded')
        result = autopilot.advance(self.root)
        self.assertEqual('COMPLETE', result['status'], result)
        self.assertEqual('DONE', read_state(self.root, self.task)['status'])


if __name__ == '__main__':
    unittest.main()
