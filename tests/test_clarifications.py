"""Planning questions must not be replaced by an agent's implicit assumptions."""
import unittest
import json
import subprocess
import sys

from web_pipeline.common import (PipelineError, atomic_json, atomic_text, load_config,
                                 read_state, source_fingerprint, write_state)
from web_pipeline.state import create_task, prepare_task, revise_task, transition
from tests import test_governance as governance
from tests.planning_fixture import record_fixture_planning


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        fixture = governance.GovernanceTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.root = fixture.root
        config_path = self.root / 'pipeline.config.yaml'
        config = json.loads(config_path.read_text())
        for command in config['verification']['commands']:
            command.update(enabled=True, argv=[sys.executable, 'check.py'], artifacts=[])
        atomic_json(config_path, config)
        atomic_text(self.root / 'check.py', 'assert 2 + 2 == 4\n')
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'commit', '-qm', 'Configure executable fixture'], check=True, capture_output=True)
        self.task = 'PLAN-001'
        create_task(self.root, self.task, 'Explicit planning fixture', 'T1', ['backend'], base_ref='HEAD')
        self.directory = self.root / 'Docs/Work' / self.task
        atomic_text(self.directory / 'BRIEF.md', '# Scope\nReturn the specified fixture result.\n')
        atomic_text(self.directory / 'DOR.md', '# Preconditions\nAn executable fixture check is configured.\n')
        atomic_json(self.directory / 'ACCEPTANCE.json', {'criteria': [
            {'id': 'AC-1', 'description': 'Return the fixture result', 'checks': ['unit']}]})

    def test_new_task_cannot_prepare_without_planning_analysis(self):
        with self.assertRaisesRegex(PipelineError, 'planning|clarification'):
            prepare_task(self.root, self.task)

    def save(self, data):
        atomic_json(self.directory / 'CLARIFICATIONS.json', data)

    def question(self, resolution=None):
        return {'id': 'Q-1', 'question': 'What result is required for empty input?',
                'impact': 'Changes observable fixture behavior and AC-1.', 'resolution': resolution}

    def resolution(self):
        return {'answer': 'Return the specified fixture result.',
                'source': {'kind': 'user_message', 'reference': 'synthetic test conversation',
                           'excerpt': 'TEST ONLY: return the specified fixture result.'},
                'acceptance_ids': ['AC-1']}

    def test_deleted_record_does_not_disable_gate(self):
        (self.directory / 'CLARIFICATIONS.json').unlink()
        with self.assertRaisesRegex(PipelineError, 'missing CLARIFICATIONS'):
            prepare_task(self.root, self.task)

    def test_malformed_acceptance_is_a_planning_error_not_an_unhandled_exception(self):
        from web_pipeline.clarifications import report
        record_fixture_planning(self.root, self.task)
        for value in ([], None, {'criteria': [None]}):
            with self.subTest(value=value):
                atomic_json(self.directory / 'ACCEPTANCE.json', value)
                self.assertEqual('NEEDS_INPUT', report(self.root, self.task)['result'])
                with self.assertRaises(PipelineError):
                    prepare_task(self.root, self.task)

    def test_unresolved_question_blocks_even_after_all_areas_analyzed(self):
        data = record_fixture_planning(self.root, self.task)
        data['questions'] = [self.question()]
        self.save(data)
        with self.assertRaisesRegex(PipelineError, 'unresolved material clarification Q-1'):
            prepare_task(self.root, self.task)

    def test_answer_with_actual_source_and_acceptance_mapping_allows_preparation(self):
        data = record_fixture_planning(self.root, self.task)
        data['questions'] = [self.question(self.resolution())]
        self.save(data)
        from web_pipeline.clarifications import report
        self.assertEqual('CLEAR', report(self.root, self.task)['result'])
        result = prepare_task(self.root, self.task)
        self.assertEqual('DRAFT', result['status'])
        self.assertEqual([], result['approvals'])

    def test_no_questions_needed_when_existing_sources_resolve_scope(self):
        record_fixture_planning(self.root, self.task)
        self.assertTrue(prepare_task(self.root, self.task)['fingerprint'])

    def test_invalid_sources_answers_and_analysis_are_rejected(self):
        import copy
        data = record_fixture_planning(self.root, self.task)
        data['questions'] = [self.question(self.resolution())]
        invalid = []
        candidate = copy.deepcopy(data)
        candidate['questions'][0]['resolution']['source']['kind'] = 'assistant_guess'
        invalid.append(candidate)
        candidate = copy.deepcopy(data)
        candidate['questions'][0]['resolution']['source']['excerpt'] = ' '
        invalid.append(candidate)
        candidate = copy.deepcopy(data)
        candidate['questions'][0]['resolution']['acceptance_ids'] = ['AC-MISSING']
        invalid.append(candidate)
        candidate = copy.deepcopy(data)
        candidate['questions'].append(candidate['questions'][0])
        invalid.append(candidate)
        candidate = copy.deepcopy(data)
        candidate['analysis'][1] = candidate['analysis'][0]
        invalid.append(candidate)
        candidate = copy.deepcopy(data)
        candidate['analysis'][0]['sources'][0]['reference'] = 'missing.md'
        invalid.append(candidate)
        candidate = copy.deepcopy(data)
        candidate['analysis'][0]['sources'][0]['excerpt'] = 'fabricated quote'
        invalid.append(candidate)
        candidate = copy.deepcopy(data)
        candidate['revision'] = 2
        invalid.append(candidate)
        for index, candidate in enumerate(invalid):
            with self.subTest(index=index):
                self.save(candidate)
                with self.assertRaises(PipelineError):
                    prepare_task(self.root, self.task)

    def test_changed_answer_and_referenced_document_invalidate_fingerprint(self):
        data = record_fixture_planning(self.root, self.task)
        atomic_text(self.root / 'detail.md', 'A concrete fixture constraint.\n')
        data['analysis'][0]['sources'].append({'kind': 'document', 'reference': 'detail.md',
                                               'excerpt': 'A concrete fixture constraint.'})
        data['questions'] = [self.question(self.resolution())]
        self.save(data)
        state = prepare_task(self.root, self.task)
        config = load_config(self.root, kit=True)
        original = source_fingerprint(self.root, config, state)
        data['questions'][0]['resolution']['answer'] = 'Changed answer'
        self.save(data)
        self.assertNotEqual(original, source_fingerprint(self.root, config, state))
        data['questions'][0]['resolution'] = self.resolution()
        self.save(data)
        self.assertEqual(original, source_fingerprint(self.root, config, state))
        atomic_text(self.root / 'detail.md', 'A concrete fixture constraint.\nAdditional requirement.\n')
        self.assertNotEqual(original, source_fingerprint(self.root, config, state))

    def test_revision_retains_answers_but_requires_reanalysis(self):
        data = record_fixture_planning(self.root, self.task)
        data['questions'] = [self.question(self.resolution())]
        self.save(data)
        before = (self.directory / 'CLARIFICATIONS.json').read_bytes()
        revise_task(self.root, self.task, 'Explicitly changed fixture scope')
        self.assertEqual(before, (self.directory / 'CLARIFICATIONS.json').read_bytes())
        with self.assertRaisesRegex(PipelineError, 'revision is stale'):
            prepare_task(self.root, self.task)

    def test_legacy_task_reports_no_coverage_then_revision_enables_gate(self):
        from web_pipeline.clarifications import report
        from web_pipeline.state import policy_check
        state = read_state(self.root, self.task)
        del state['planning_version']  # Explicit old-engine fixture, not an operational bypass.
        write_state(self.root, state)
        (self.directory / 'CLARIFICATIONS.json').unlink()
        self.assertEqual('NOT_CONFIGURED', report(self.root, self.task)['result'])
        self.assertTrue(any('planning clarification NOT_CONFIGURED' in value
                            for value in policy_check(self.root, kit=True)['warnings']))
        prepare_task(self.root, self.task)
        revised = revise_task(self.root, self.task, 'Adopt planning for changed fixture requirements')
        self.assertEqual(1, revised['planning_version'])
        with self.assertRaisesRegex(PipelineError, 'planning analysis incomplete'):
            prepare_task(self.root, self.task)

    def test_diagnostic_is_read_only_and_returns_nonzero_until_clear(self):
        import contextlib
        import io
        from web_pipeline.cli import main
        before = {p.name: p.read_bytes() for p in self.directory.iterdir() if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, main(['--root', str(self.root), 'clarification-report', '--task', self.task]))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir() if p.is_file()})
        record_fixture_planning(self.root, self.task)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, main(['--root', str(self.root), 'clarification-report', '--task', self.task]))

    def test_late_question_blocks_direct_transition_and_loop_implementation(self):
        from tests import test_simplified_approvals as fixtures
        from web_pipeline import autopilot
        f = fixtures.SimplifiedApprovalTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.f.baseline_and_start()
        directory = f.root / 'Docs/Work' / f.task
        data = json.loads((directory / 'CLARIFICATIONS.json').read_text())
        data['questions'] = [self.question()]
        atomic_json(directory / 'CLARIFICATIONS.json', data)
        with self.assertRaisesRegex(PipelineError, 'unresolved material clarification'):
            transition(f.root, f.task, 'VERIFYING')
        autopilot.start(f.root, {'objective': 'Do not guess late requirements',
                                'tasks': [{'task_id': f.task, 'depends_on': []}]})
        result = autopilot.advance(f.root)
        self.assertEqual('WAITING', result['status'], result)
        self.assertIn('unresolved material clarification', str(result))
        self.assertIsNone(autopilot.status(f.root)['lease'])


if __name__ == '__main__':
    unittest.main()
