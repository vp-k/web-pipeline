"""Actual scoped commands, lifecycle gates, phase aggregation and legacy regressions."""
import copy
import json
import sys
import unittest

from tests import test_simplified_approvals as fixtures
from web_pipeline import autopilot, scopes
from web_pipeline.common import (PipelineError, atomic_json, atomic_text, hash_file,
                                 read_state, write_state)
from web_pipeline.local_review import record_review
from web_pipeline.runner import run_profile, validate_run, validate_completion
from web_pipeline.state import create_task, prepare_task, transition, policy_check

DECISION = fixtures.DECISION


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SimplifiedApprovalTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root, self.task, self.config = self.f.root, self.f.task, self.f.config
        for name, value in [('a', 1), ('b', 2), ('shared', 3)]:
            atomic_text(self.root / f'{name}.py', f'value = {value}\n')
            self.config['verification']['commands'].append({
                'id': f'unit-{name}', 'enabled': True, 'profiles': ['Full', 'Release'],
                'argv': [sys.executable, '-c', f'import {name}; assert {name}.value == {value}'],
                'cwd': '.', 'timeout_seconds': 30, 'artifacts': [], 'environment': 'test'})
        self.config['verification']['commands'].append({
            'id': 'phase-integration', 'enabled': True, 'profiles': ['Full', 'Release'],
            'argv': [sys.executable, '-c', 'import a, b, shared; assert a.value + b.value == shared.value'],
            'cwd': '.', 'timeout_seconds': 30, 'artifacts': [], 'environment': 'test'})
        self.config['verification']['scopes'] = {
            'components': [{'id': name, 'paths': [f'{name}.py'], 'domains': ['backend'],
                            'depends_on': [] if name == 'shared' else ['shared'],
                            'checks': {'Task': [f'unit-{name}'], 'Phase': ['phase-integration']}}
                           for name in ['a', 'b', 'shared']],
            'task_checks': ['unit'], 'phase_checks': ['phase-integration'], 'broad_paths': ['global/*']}
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        self.scope(self.task, ['a'])
        self.acceptance(self.task, 'unit-a')
        self.f.f.git('add', '.')
        self.f.f.git('commit', '-qm', 'scoped verification fixture')
        prepare_task(self.root, self.task)

    def scope(self, task, components, members=None):
        atomic_json(self.root / f'Docs/Work/{task}/SCOPE.json', {
            'level': 'phase' if members is not None else 'task', 'components': components,
            'members': members or []})

    def acceptance(self, task, check):
        atomic_json(self.root / f'Docs/Work/{task}/ACCEPTANCE.json', {
            'criteria': [{'id': 'AC-1', 'description': 'Execute the declared behavior', 'checks': [check]}]})

    def new(self, task, components, members=None):
        create_task(self.root, task, 'Scoped fixture', 'T1', ['backend'], base_ref='HEAD')
        for name in ['BRIEF', 'DOR']:
            atomic_text(self.root / f'Docs/Work/{task}/{name}.md', '# Fixture\nVerify actual arithmetic behavior.\n')
        self.scope(task, components, members)
        self.acceptance(task, 'phase-integration' if members is not None else f'unit-{components[0]}')
        from tests.planning_fixture import record_fixture_planning
        record_fixture_planning(self.root, task)
        prepare_task(self.root, task)

    def start(self, task=None):
        task = task or self.task
        result = run_profile(self.root, task, 'Baseline')
        self.assertEqual('PASS', result['status'], result)
        transition(self.root, task, 'READY')
        transition(self.root, task, 'IN_PROGRESS')

    def finish(self, task=None):
        task = task or self.task
        profile = scopes.completion_profile(self.root, self.config, read_state(self.root, task))
        result = run_profile(self.root, task, profile)
        self.assertEqual('PASS', result['status'], result)
        transition(self.root, task, 'VERIFYING')
        transition(self.root, task, 'REVIEW')
        record_review(self.root, task, DECISION)
        transition(self.root, task, 'DONE')
        return result

    def test_task_executes_acceptance_and_impacted_checks_not_unrelated_failure(self):
        atomic_text(self.root / 'b.py', 'value = -1\n')
        self.f.f.git('add', 'b.py')
        self.f.f.git('commit', '-qm', 'known unrelated fixture failure')
        prepare_task(self.root, self.task)
        self.start()
        task = run_profile(self.root, self.task, 'Task')
        self.assertEqual('PASS', task['status'], task)
        self.assertEqual({'unit', 'unit-a'}, {c['id'] for c in task['checks']})
        full = run_profile(self.root, self.task, 'Full')
        self.assertEqual('FAIL', full['status'])
        self.assertIn('unit-b', {c['id'] for c in full['checks'] if c['status'] == 'FAIL'})

    def test_transitive_consumers_and_unknown_paths_expand_scope(self):
        state = read_state(self.root, self.task)
        shared = scopes.selection(self.root, self.config, state, 'Task', changed_paths=['shared.py'])
        self.assertEqual(['a', 'b', 'shared'], shared['components'])
        self.assertIn('unit-b', shared['checks'])
        for path in ['unknown.py', 'pipeline.config.yaml', 'global/tool.py']:
            plan = scopes.selection(self.root, self.config, state, 'Task', changed_paths=[path])
            self.assertEqual('project', plan['level'])
            self.assertIn('phase-integration', plan['checks'])
        state['risk_tier'] = 'T3'
        self.assertEqual('project', scopes.selection(self.root, self.config, state, 'Task', changed_paths=[])['level'])

    def test_release_selects_full_union_and_cannot_execute_without_gate(self):
        plan = scopes.selection(self.root, self.config, read_state(self.root, self.task), 'Release', changed_paths=[])
        self.assertTrue({'unit-a', 'unit-b', 'unit-shared', 'phase-integration'} <= set(plan['checks']))
        with self.assertRaises(PipelineError):
            run_profile(self.root, self.task, 'Release')

    def test_scope_and_check_evidence_cannot_be_removed_or_relabelled(self):
        self.start()
        result = run_profile(self.root, self.task, 'Task')
        state = read_state(self.root, self.task)
        path = self.root / self.config['project']['report_root'] / result['run_id'] / scopes.ARTIFACT
        plan = json.loads(path.read_text())
        plan['checks'].remove('unit-a')
        atomic_json(path, plan)
        summary_path = path.parent.parent / 'summary.json'
        summary = json.loads(summary_path.read_text())
        for artifact in summary['artifacts']:
            if artifact['path'] == scopes.ARTIFACT:
                artifact.update(sha256=hash_file(path), size=path.stat().st_size)
        atomic_json(summary_path, summary)
        with self.assertRaises(PipelineError):
            validate_completion(self.root, self.config, state, result['run_id'])

    def test_phase_reverifies_historical_members_and_covers_merge(self):
        self.start()
        atomic_text(self.root / 'a.py', 'value = 1\n# first task\n')
        first = self.finish()
        self.new('TASK-002', ['b'])
        self.start('TASK-002')
        atomic_text(self.root / 'b.py', 'value = 2\n# second task\n')
        self.finish('TASK-002')
        self.assertEqual('FAIL', policy_check(self.root, gate='merge')['status'])
        self.new('PHASE-001', ['a', 'b'], [self.task, 'TASK-002'])
        self.start('PHASE-001')
        with self.assertRaises(PipelineError):
            run_profile(self.root, 'PHASE-001', 'Task')
        phase = self.finish('PHASE-001')
        self.assertEqual('Phase', phase['profile'])
        self.assertTrue({'unit-a', 'unit-b', 'phase-integration'} <= {c['id'] for c in phase['checks']})
        merged = policy_check(self.root, gate='merge')
        self.assertEqual('PASS', merged['status'], merged)
        with self.assertRaises(PipelineError):
            validate_run(self.root, self.config, read_state(self.root, self.task), first['run_id'])
        atomic_text(self.root / 'b.py', 'value = -1\n')
        self.assertEqual('FAIL', policy_check(self.root, gate='merge')['status'])

    def test_phase_requires_completed_members_and_real_integration_success(self):
        self.new('PHASE-001', ['a'], [self.task])
        self.start('PHASE-001')
        with self.assertRaisesRegex(PipelineError, 'requires DONE'):
            run_profile(self.root, 'PHASE-001', 'Phase')

    def test_phase_failure_is_budgeted_and_fast_cannot_satisfy_completion(self):
        self.start()
        fast = run_profile(self.root, self.task, 'Fast')
        with self.assertRaises(PipelineError):
            validate_completion(self.root, self.config, read_state(self.root, self.task), fast['run_id'])
        self.finish()
        self.new('PHASE-001', ['a', 'b'], [self.task])
        self.start('PHASE-001')
        atomic_text(self.root / 'shared.py', 'value = -1\n')
        result = run_profile(self.root, 'PHASE-001', 'Phase')
        self.assertEqual('FAIL', result['status'])
        self.assertIn('phase-integration', {c['id'] for c in result['checks'] if c['status'] == 'FAIL'})
        state = read_state(self.root, 'PHASE-001')
        self.assertIsNone(state['full_run'])
        self.assertEqual(1, state['iteration']['failed_attempts'])

    def test_phase_does_not_trust_forged_done_or_missing_review(self):
        self.start()
        run_profile(self.root, self.task, 'Task')
        state = read_state(self.root, self.task)
        state['status'] = 'DONE'
        write_state(self.root, state)  # explicit adversarial fixture, not a workflow transition
        self.new('PHASE-001', ['a'], [self.task])
        self.start('PHASE-001')
        with self.assertRaisesRegex(PipelineError, 'local review'):
            run_profile(self.root, 'PHASE-001', 'Phase')

    def test_configuration_and_scope_changes_fail_closed(self):
        bad = copy.deepcopy(self.config)
        bad['verification']['scopes']['components'][0]['depends_on'] = ['missing']
        with self.assertRaises(PipelineError):
            scopes.validate_config(self.root, bad)
        bad = copy.deepcopy(self.config)
        bad['verification']['scopes']['components'][0]['checks']['Task'] = ['disabled-check']
        with self.assertRaises(PipelineError):
            scopes.validate_config(self.root, bad)
        self.start()
        self.scope(self.task, ['b'])
        with self.assertRaisesRegex(PipelineError, 'fingerprint'):
            run_profile(self.root, self.task, 'Task')

    def test_loop_uses_task_completion_and_preserves_review_gate(self):
        autopilot.start(self.root, {'objective': 'Scoped arithmetic', 'tasks': [{'task_id': self.task, 'depends_on': []}]})
        ticket = autopilot.advance(self.root)
        self.assertEqual('IMPLEMENT', ticket['action'])
        autopilot.complete(self.root, ticket['token'], 'implemented', DECISION)
        ticket = autopilot.advance(self.root)
        self.assertEqual('REVIEW', ticket['action'])
        state = read_state(self.root, self.task)
        result = validate_completion(self.root, self.config, state, state['full_run'])
        self.assertEqual('Task', result['profile'])
        autopilot.complete(self.root, ticket['token'], 'reviewed', DECISION)
        self.assertEqual('COMPLETE', autopilot.advance(self.root)['status'])

    def test_dependent_queue_reaches_phase_without_replaying_old_tasks(self):
        self.new('TASK-002', ['b'])
        self.new('PHASE-001', ['a', 'b'], [self.task, 'TASK-002'])
        plan = {'objective': 'Verify connected arithmetic', 'completion_gate': 'merge', 'tasks': [
            {'task_id': self.task, 'depends_on': []},
            {'task_id': 'TASK-002', 'depends_on': [self.task]},
            {'task_id': 'PHASE-001', 'depends_on': [self.task, 'TASK-002']}]}
        invalid = copy.deepcopy(plan)
        invalid['tasks'][-1]['depends_on'] = []
        with self.assertRaisesRegex(PipelineError, 'explicit dependencies'):
            autopilot.start(self.root, invalid)
        autopilot.start(self.root, plan)
        for task_id, component in [(self.task, 'a'), ('TASK-002', 'b'), ('PHASE-001', None)]:
            ticket = autopilot.advance(self.root)
            self.assertEqual(('IMPLEMENT', task_id), (ticket.get('action'), ticket.get('task_id')), ticket)
            if component:
                path = self.root / f'{component}.py'
                atomic_text(path, path.read_text() + f'# implemented {task_id}\n')
            autopilot.complete(self.root, ticket['token'], 'implemented', DECISION)
            ticket = autopilot.advance(self.root)
            self.assertEqual(('REVIEW', task_id), (ticket.get('action'), ticket.get('task_id')), ticket)
            autopilot.complete(self.root, ticket['token'], 'reviewed', DECISION)
        result = autopilot.advance(self.root)
        self.assertEqual('COMPLETE', result['status'], result)
        self.assertEqual('PASS', result['merge_gate']['status'], result)

    def test_rename_includes_original_and_destination_component(self):
        self.config['verification']['scopes']['components'][1]['paths'].append('moved.py')
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        self.scope(self.task, ['b'])
        self.f.f.git('add', '.')
        self.f.f.git('commit', '-qm', 'map destination component')
        prepare_task(self.root, self.task)
        self.f.f.git('mv', 'a.py', 'moved.py')
        plan = scopes.selection(self.root, self.config, read_state(self.root, self.task), 'Task')
        self.assertTrue({'a.py', 'moved.py'} <= set(plan['changed_paths']))
        self.assertEqual(['a', 'b'], plan['components'])

    def test_cli_plan_is_read_only_and_includes_consumer_contracts(self):
        from web_pipeline.cli import _parser, dispatch
        before = read_state(self.root, self.task)
        report_paths = list(self.root.glob('Reports/Pipeline/*'))
        args = _parser().parse_args(['--root', str(self.root), 'verification-plan', '--task', self.task])
        plan = dispatch(args)
        self.assertEqual('Task', plan['profile'])
        self.assertEqual(['a'], plan['components'])
        self.assertEqual(before, read_state(self.root, self.task))
        self.assertEqual(report_paths, list(self.root.glob('Reports/Pipeline/*')))
        config = copy.deepcopy(self.config)
        config['boundaries'] = {'components': [
            {'id': c['id'], 'paths': c['paths'], 'depends_on': c['depends_on']}
            for c in config['verification']['scopes']['components']],
            'dependency_check': 'dependency-graph', 'contracts': [{
                'paths': ['shared.py'], 'provider': 'a', 'consumers': ['b'],
                'checks': {'provider': 'contract-provider', 'consumer': 'contract-consumer',
                           'compatibility': 'contract-compatibility', 'integration': 'integration'}}]}
        plan = scopes.selection(self.root, config, before, 'Task', changed_paths=['a.py'])
        self.assertTrue({'dependency-graph', 'contract-provider', 'contract-consumer',
                         'contract-compatibility', 'integration'} <= set(plan['checks']))


if __name__ == '__main__':
    unittest.main()
