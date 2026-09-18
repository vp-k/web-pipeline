"""Risk propagation and explicit prepare/implement/verify group barriers."""
import copy
import json
import sys
import unittest

from tests import test_scopes, test_boundaries
from web_pipeline import autopilot, boundaries, scopes
from web_pipeline.common import PipelineError, atomic_json, atomic_text, read_state
from web_pipeline.policy import classify
from web_pipeline.state import prepare_task, transition


class BoundaryOrderTests(unittest.TestCase):
    def fixture(self):
        f = test_scopes.ScopeTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        return f

    def model(self, config):
        return {'source_patterns': ['a.py', 'b.py', 'shared.py'],
                'dependency_check': 'unit', 'server_only_packages': [], 'contracts': [],
                'components': [{'id': c['id'], 'paths': c['paths'],
                    'runtime': 'shared' if c['id'] == 'shared' else 'server',
                    'depends_on': ['a'] if c['id'] == 'b' else []}
                    for c in config['verification']['scopes']['components']]}

    def test_boundary_dependency_promotes_authorization_risk_and_full_scope(self):
        f = self.fixture()
        config = copy.deepcopy(f.config)
        for component in config['verification']['scopes']['components']:
            component['depends_on'] = []
        config['verification']['scopes']['components'][1]['domains'] = ['authorization']
        if 'authorization' not in config['project']['supported_domains']:
            config['project']['supported_domains'].append('authorization')
        config['boundaries'] = self.model(config)
        boundaries.validate_config(f.root, config)
        scopes.validate_config(f.root, config)
        state = read_state(f.root, f.task)
        result = classify(f.root, config, state, changed_paths=['a.py'])
        self.assertEqual('T3', result['risk_tier'], result)
        self.assertIn('authorization_rbac', result['protected_changes'])
        state.update({key: result[key] for key in ('risk_tier', 'change_domains', 'protected_changes')})
        plan = scopes.selection(f.root, config, state, 'Task', changed_paths=['a.py'])
        self.assertEqual('project', plan['level'])
        self.assertIn('authorization-tests', plan['checks'])

    def group_fixture(self):
        f = self.fixture()
        for name, value in [('a', 1), ('b', 2)]:
            atomic_text(f.root / f'{name}.py', f'value = {value}\nready = False\n')
        config = f.config
        config['boundaries'] = self.model(config)
        config['boundaries']['dependency_check'] = 'boundary-imports'
        config['boundaries']['contracts'] = [{
            'id': 'feature', 'paths': ['shared.py'], 'provider': 'a', 'consumers': ['b'],
            'checks': {'provider': 'unit-a', 'consumer': 'unit-b',
                       'compatibility': 'unit', 'integration': 'phase-integration'}}]
        for command in config['verification']['commands']:
            if command['id'] in {'unit-a', 'unit-b', 'phase-integration'}:
                command['profiles'] = list(set(command['profiles']) | {'Release'})
            if command['id'] == 'phase-integration':
                command['argv'] = [sys.executable, '-c', 'import a,b; assert a.ready and b.ready']
        config['verification']['commands'].append({
            'id': 'boundary-imports', 'enabled': True, 'profiles': sorted(boundaries.PROFILES),
            'argv': [sys.executable, 'graph_fixture.py'], 'cwd': '.', 'timeout_seconds': 30,
            'artifacts': [boundaries.GRAPH], 'environment': 'test'})
        atomic_text(f.root / 'graph_fixture.py', test_boundaries.ADAPTER)
        atomic_json(f.root / 'pipeline.config.yaml', config)
        f.f.f.git('add', '.')
        f.f.f.git('commit', '-qm', 'Declared contract and grouped implementation fixture')
        f.new('TASK-002', ['b'])
        f.new('PHASE-001', ['a', 'b'], [f.task, 'TASK-002'])
        for name in (f.task, 'TASK-002', 'PHASE-001'):
            prepare_task(f.root, name)
        plan = {'objective': 'Build provider then consumer, verify only after both exist',
                'tasks': [{'task_id': f.task, 'depends_on': []},
                          {'task_id': 'TASK-002', 'depends_on': []},
                          {'task_id': 'PHASE-001', 'depends_on': [f.task, 'TASK-002']}],
                'implementation_groups': [{'phase': 'PHASE-001', 'order': [f.task, 'TASK-002']}]}
        return f, plan

    def test_group_baselines_then_both_implementations_then_unchanged_checks(self):
        f, plan = self.group_fixture()
        autopilot.start(f.root, plan)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', f.task), (ticket['action'], ticket['task_id']))
        baselines = []
        for name in (f.task, 'TASK-002'):
            state = read_state(f.root, name)
            self.assertEqual('IN_PROGRESS', state['status'])
            baseline = f.root / f"Reports/Pipeline/{state['baseline_run']}/summary.json"
            baselines.append(json.loads(baseline.read_text())['snapshot']['tree_digest'])
        self.assertEqual(*baselines)
        atomic_text(f.root / 'a.py', 'value = 1\nready = True\n')
        autopilot.complete(f.root, ticket['token'], 'implemented', test_scopes.DECISION)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', 'TASK-002'), (ticket['action'], ticket['task_id']))
        summaries = [json.loads(p.read_text()) for p in f.root.glob('Reports/Pipeline/*/summary.json')]
        self.assertEqual({'Baseline'}, {s['profile'] for s in summaries})
        atomic_text(f.root / 'b.py', 'value = 2\nready = True\n')
        autopilot.complete(f.root, ticket['token'], 'implemented', test_scopes.DECISION)
        for name in (f.task, 'TASK-002'):
            ticket = autopilot.advance(f.root)
            self.assertEqual(('REVIEW', name), (ticket['action'], ticket['task_id']), ticket)
            state = read_state(f.root, name)
            summary = json.loads((f.root / f"Reports/Pipeline/{state['full_run']}/summary.json").read_text())
            self.assertIn('phase-integration', {c['id'] for c in summary['checks']})
            self.assertEqual('PASS', summary['status'])
            autopilot.complete(f.root, ticket['token'], 'reviewed', test_scopes.DECISION)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', 'PHASE-001'), (ticket['action'], ticket['task_id']), ticket)
        autopilot.complete(f.root, ticket['token'], 'implemented', test_scopes.DECISION)
        ticket = autopilot.advance(f.root)
        self.assertEqual(('REVIEW', 'PHASE-001'), (ticket['action'], ticket['task_id']))
        autopilot.complete(f.root, ticket['token'], 'reviewed', test_scopes.DECISION)
        self.assertEqual('COMPLETE', autopilot.advance(f.root)['status'])

    def test_group_rejects_internal_completion_dependency_before_checkpoint(self):
        f, plan = self.group_fixture()
        plan['tasks'][1]['depends_on'] = [f.task]
        with self.assertRaisesRegex(PipelineError, 'completion dependencies inside'):
            autopilot.start(f.root, plan)
        self.assertFalse((f.root / autopilot.QUEUE).exists())

    def test_contract_party_impact_reaches_transitive_authorization_consumer(self):
        f = self.fixture()
        config = copy.deepcopy(f.config)
        for component in config['verification']['scopes']['components']:
            component['depends_on'] = []
        config['verification']['scopes']['components'][1]['domains'] = ['authorization']
        if 'authorization' not in config['project']['supported_domains']:
            config['project']['supported_domains'].append('authorization')
        config['boundaries'] = self.model(config)
        config['boundaries']['contracts'] = [{'id': 'api', 'paths': ['shared.py'],
            'provider': 'a', 'consumers': ['shared'], 'checks': {
                'provider': 'unit-a', 'consumer': 'unit-shared',
                'compatibility': 'unit-b', 'integration': 'phase-integration'}}]
        for command in config['verification']['commands']:
            if command['id'] in {'unit-a', 'unit-b', 'unit-shared', 'phase-integration'}:
                command['profiles'] = list(set(command['profiles']) | {'Release'})
        boundaries.validate_config(f.root, config)
        scopes.validate_config(f.root, config)
        # Pure impact calculation: contract-party insertion must precede closure.
        result = classify(f.root, config, read_state(f.root, f.task), changed_paths=['shared.py'])
        self.assertEqual('T3', result['risk_tier'], result)
        self.assertIn('authorization', result['change_domains'])

    def test_group_rejects_missing_members_and_indirect_wait_cycle(self):
        f, plan = self.group_fixture()
        bad = copy.deepcopy(plan)
        bad['implementation_groups'][0]['order'].append('PHASE-001')
        with self.assertRaisesRegex(PipelineError, 'every Phase member'):
            autopilot.start(f.root, bad)
        f.new('TASK-EXT', ['shared'])
        plan['tasks'].append({'task_id': 'TASK-EXT', 'depends_on': [f.task]})
        plan['tasks'][1]['depends_on'] = ['TASK-EXT']
        with self.assertRaisesRegex(PipelineError, 'barrier creates'):
            autopilot.start(f.root, plan)
        self.assertFalse((f.root / autopilot.QUEUE).exists())

    def test_blocked_member_prevents_every_group_implementation(self):
        f, plan = self.group_fixture()
        autopilot.start(f.root, plan)
        transition(f.root, 'TASK-002', 'BLOCKED')
        result = autopilot.advance(f.root)
        self.assertEqual('WAITING', result['status'], result)
        events = autopilot.status(f.root)['events']
        self.assertFalse(any(e.get('action') == 'IMPLEMENT' for e in events))

    def test_interrupted_implementation_resumes_with_original_baselines(self):
        f, plan = self.group_fixture()
        autopilot.start(f.root, plan)
        first = autopilot.advance(f.root)
        before = {name: read_state(f.root, name)['baseline_run'] for name in (f.task, 'TASK-002')}
        atomic_text(f.root / 'a.py', 'value = 1\nready = True\n')
        autopilot.recover(f.root, first['token'], 'Fixture worker stopped after its partial edit')
        autopilot.retry(f.root, f.task, 'Partial edit inspected; resume without replacing Baseline')
        resumed = autopilot.advance(f.root)
        self.assertEqual(('IMPLEMENT', f.task), (resumed['action'], resumed['task_id']), resumed)
        self.assertEqual(before, {name: read_state(f.root, name)['baseline_run'] for name in before})
        autopilot.complete(f.root, resumed['token'], 'implemented', test_scopes.DECISION)
        next_ticket = autopilot.advance(f.root)
        self.assertEqual('TASK-002', next_ticket['task_id'])
        autopilot.recover(f.root, next_ticket['token'], 'Fixture inspection finished')
        atomic_text(f.root / 'shared.py', 'value = 3\n# changed agreed contract\n')
        with self.assertRaisesRegex(PipelineError, 'final contract and scope'):
            autopilot.advance(f.root)


if __name__ == '__main__':
    unittest.main()
