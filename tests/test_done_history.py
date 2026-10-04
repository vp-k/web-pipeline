"""DONE is history: later project work does not reopen a completed task (docs/E2E_TRIAL.md, D3 and D5)."""
import copy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from tests import test_autopilot, test_lifecycle, test_release_integration
from tests.planning_fixture import record_fixture_planning
from web_pipeline import autopilot
from web_pipeline.common import (atomic_json, atomic_text, load_config, read_state, source_fingerprint,
                                 write_state)
from web_pipeline.runner import run_profile
from web_pipeline.state import policy_check, prepare_task, revise_task, transition


def later():
    """A clock two hours ahead: the fixture approvals have expired by then."""
    return (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace('+00:00', 'Z')


def unrelated_check(config):
    """A new check the project enables after the task: the task's own checks are unchanged."""
    command = copy.deepcopy(config['verification']['commands'][0])
    command.update(id='later-audit', profiles=['Release'])
    config['verification']['commands'].append(command)
    return config


class SealTests(unittest.TestCase):
    setUp = test_lifecycle.LifecycleTests.setUp
    git = test_lifecycle.LifecycleTests.git
    baseline_and_start = test_lifecycle.LifecycleTests.baseline_and_start
    full_and_review = test_lifecycle.LifecycleTests.full_and_review
    sign_review = test_lifecycle.LifecycleTests.sign_review

    def done(self):
        self.baseline_and_start()
        summary = self.full_and_review()
        self.sign_review(summary)
        transition(self.root, self.task, 'DONE', trust_path=self.trust)
        return summary

    def check(self):
        return policy_check(self.root, task_id=self.task, trust_path=self.trust)

    def later_project_work(self):
        atomic_text(self.root / 'check.py', 'assert 2 + 2 == 4\nassert 3 * 3 == 9\n')
        atomic_text(self.root / self.config['sources']['product_spec'], 'Product specification revision two.\n')
        atomic_json(self.root / 'pipeline.config.yaml', unrelated_check(copy.deepcopy(self.config)))

    def test_done_is_sealed_and_stays_done_through_later_project_work(self):
        summary = self.done()
        state = read_state(self.root, self.task)
        seal = state['completion_seal']
        self.assertEqual(state['fingerprint'], seal['fingerprint'])
        self.assertEqual(state['revision'], seal['revision'])
        self.assertIn(f'Docs/Work/{self.task}/BRIEF.md', seal['records'])
        self.assertNotIn(f'Docs/Work/{self.task}/STATE.md', seal['records'])
        self.assertEqual({state['baseline_run'], state['full_run']}, set(seal['runs']))
        self.assertEqual(summary['snapshot']['tree_digest'], seal['snapshot']['tree_digest'])
        self.later_project_work()
        with patch('web_pipeline.approval.utc_now', later):
            result = self.check()
        self.assertEqual('PASS', result['status'], result)

    def test_an_unsealed_done_keeps_the_full_current_validation(self):
        self.done()
        state = read_state(self.root, self.task)
        state['completion_seal'] = None  # a task finished before 2.16
        write_state(self.root, state)
        self.assertEqual('PASS', self.check()['status'])
        self.later_project_work()
        self.assertEqual('FAIL', self.check()['status'])

    def test_editing_a_completed_record_requires_a_revision(self):
        self.done()
        atomic_text(self.root / f'Docs/Work/{self.task}/DOR.md', '# Ready\n\nA different definition of ready.\n')
        result = self.check()
        self.assertEqual('FAIL', result['status'])
        message = ' '.join(result['errors'])
        self.assertIn('DOR.md', message)
        self.assertIn('revise', message)
        state = revise_task(self.root, self.task, 'Ready criteria changed after completion')
        self.assertIsNone(state['completion_seal'])
        self.assertEqual('DRAFT', state['status'])

    def test_a_replaced_run_summary_breaks_the_seal(self):
        self.done()
        state = read_state(self.root, self.task)
        path = self.root / self.config['project']['report_root'] / state['full_run'] / 'summary.json'
        summary = json.loads(path.read_text(encoding='utf-8'))
        summary['finished_utc'] = later()
        atomic_json(path, summary)
        self.assertEqual('FAIL', self.check()['status'])

    def test_a_forged_seal_still_needs_the_signed_review(self):
        self.baseline_and_start()
        self.full_and_review()  # verified but never reviewed
        state = read_state(self.root, self.task)
        from web_pipeline import seal
        state['completion_seal'] = seal.make(self.root, self.config, state)
        state['status'] = 'DONE'
        write_state(self.root, state)
        result = self.check()
        self.assertEqual('FAIL', result['status'])
        self.assertIn('review', ' '.join(result['errors']))


class InFlightTests(unittest.TestCase):
    setUp = test_lifecycle.LifecycleTests.setUp
    git = test_lifecycle.LifecycleTests.git
    baseline_and_start = test_lifecycle.LifecycleTests.baseline_and_start
    full_and_review = test_lifecycle.LifecycleTests.full_and_review

    def test_project_docs_and_new_checks_do_not_reopen_started_work(self):
        self.baseline_and_start()
        atomic_text(self.root / self.config['sources']['api_contract'], 'Contract revision two.\n')
        atomic_json(self.root / 'pipeline.config.yaml', unrelated_check(copy.deepcopy(self.config)))
        result = policy_check(self.root, task_id=self.task, trust_path=self.trust)
        self.assertEqual('PASS', result['status'], result)
        self.full_and_review()  # Full runs under the new policy; the Baseline stays the recorded history

    def test_the_task_records_and_cited_docs_still_bind_started_work(self):
        self.baseline_and_start()
        atomic_text(self.root / f'Docs/Work/{self.task}/DOR.md', '# Ready\n\nA different definition of ready.\n')
        result = policy_check(self.root, task_id=self.task, trust_path=self.trust)
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any('fingerprint' in error for error in result['errors']), result)

    def test_a_task_prepared_before_2_16_keeps_its_fingerprint(self):
        state = read_state(self.root, self.task)
        legacy = {key: value for key, value in state.items() if key != 'fingerprint_version'}
        config = load_config(self.root)
        legacy['fingerprint'] = source_fingerprint(self.root, config, legacy)
        self.assertNotEqual(state['fingerprint'], legacy['fingerprint'])
        write_state(self.root, legacy)
        self.assertEqual('PASS', policy_check(self.root, task_id=self.task)['status'])
        atomic_text(self.root / self.config['sources']['api_contract'], 'Contract revision two.\n')
        self.assertEqual('FAIL', policy_check(self.root, task_id=self.task)['status'])
        revise_task(self.root, self.task, 'Move to the current fingerprint')
        record_fixture_planning(self.root, self.task)
        self.assertEqual(2, prepare_task(self.root, self.task, 'fixture-implementer')['fingerprint_version'])


class ReleaseAfterDoneTests(unittest.TestCase):
    setUp = test_release_integration.ReleaseIntegrationTests.setUp
    _approval = test_release_integration.ReleaseIntegrationTests._approval

    def test_release_checks_enabled_after_done_do_not_reopen_the_task(self):
        design = [self._approval('design', 'Payment Owner', 'payment-owner'),
                  self._approval('design', 'Tech Owner', 'tech-owner')]
        state = read_state(self.root, self.task)
        state['approvals'] = design
        write_state(self.root, state)
        run_profile(self.root, self.task, 'Baseline', trust_path=self.trust, run_id='pay-baseline-001')
        transition(self.root, self.task, 'READY', self.trust)
        transition(self.root, self.task, 'IN_PROGRESS', self.trust)
        full = run_profile(self.root, self.task, 'Full', trust_path=self.trust, run_id='pay-full-001')
        transition(self.root, self.task, 'VERIFYING', self.trust)
        transition(self.root, self.task, 'REVIEW', self.trust)
        review = self._approval('review', 'Reviewer', 'reviewer', run=full)
        state = read_state(self.root, self.task)
        state['approvals'] = design + [review]
        write_state(self.root, state)
        transition(self.root, self.task, 'DONE', self.trust)
        # The release infrastructure arrives after the feature: a new Release-only check.
        command = copy.deepcopy(self.config['verification']['commands'][0])
        command.update(id='release-drill', profiles=['Release'])
        self.config['verification']['commands'].append(command)
        self.config['verification']['requirements']['payment']['Release'].append('release-drill')
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        signers = [self._approval('release', role, identity, run=full) for role, identity in (
            ('Release Owner', 'release-owner'), ('Payment Owner', 'payment-owner'), ('Tech Owner', 'tech-owner'))]
        state = read_state(self.root, self.task)
        state['approvals'] = design + [review, *signers]
        write_state(self.root, state)
        release = run_profile(self.root, self.task, 'Release', trust_path=self.trust, run_id='pay-release-001')
        self.assertEqual('PASS', release['status'], release)
        self.assertIn('release-drill', {check['id'] for check in release['checks']})
        self.assertEqual('READY', read_state(self.root, self.task)['release_status'])
        result = policy_check(self.root, task_id=self.task, trust_path=self.trust)
        self.assertEqual('PASS', result['status'], result)


class QueueTests(unittest.TestCase):
    setUp = test_autopilot.AutopilotTests.setUp
    begin = test_autopilot.AutopilotTests.begin
    next = test_autopilot.AutopilotTests.next
    complete = test_autopilot.AutopilotTests.complete
    second_task = test_autopilot.AutopilotTests.second_task

    def sign(self, task):
        state = read_state(self.root, task)
        report = self.root / 'Reports/Pipeline' / state['full_run'] / 'summary.json'
        first, self.f.task = self.f.task, task
        try:
            self.f.sign_review(json.loads(report.read_text(encoding='utf-8')))
        finally:
            self.f.task = first
        autopilot.retry(self.root, task, 'Fixture human signature attached')

    def review(self):
        ticket = self.next()
        self.assertEqual('REVIEW', ticket['action'], ticket)
        self.complete(ticket, 'reviewed')
        self.assertEqual('WAITING', self.next()['status'])

    def test_a_dependent_task_changes_the_project_without_reopening_its_dependency(self):
        first = self.f.task
        second = self.second_task(depends=True)
        self.begin()
        self.complete(self.next())
        self.review()
        self.sign(first)
        implement = self.next()
        self.assertEqual((second, 'IMPLEMENT'), (implement['task_id'], implement['action']), implement)
        self.assertEqual('DONE', read_state(self.root, first)['status'])
        atomic_text(self.root / 'app.py', 'value = 4\nlabel = "notes"\n')
        atomic_text(self.root / self.f.config['sources']['product_spec'], 'Product specification revision two.\n')
        self.complete(implement)
        self.review()
        self.sign(second)
        self.assertEqual('COMPLETE', self.next()['status'])
        self.assertEqual('PASS', policy_check(self.root, task_id=first, trust_path=self.f.trust)['status'])
        merge = policy_check(self.root, trust_path=self.f.trust, gate='merge')
        self.assertEqual('FAIL', merge['status'])  # merge readiness still needs evidence for the merged tree
        self.assertTrue(any(error.startswith(first) for error in merge['errors']), merge)


if __name__ == '__main__':
    unittest.main()
