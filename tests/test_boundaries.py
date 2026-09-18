"""Boundary policy, artifact protocol and real engine lifecycle regressions."""
import copy
import json
import sys
import unittest

from tests import test_lifecycle
from web_pipeline import boundaries
from web_pipeline.common import (PipelineError, atomic_json, atomic_text, code_snapshot, hash_file, load_config, read_state, source_fingerprint)
from web_pipeline.evidence import policy_snapshot, required_checks
from web_pipeline.policy import classify
from web_pipeline.runner import run_profile, validate_run
from web_pipeline.state import policy_check, prepare_task, transition

MODEL = {
    'source_patterns': ['src/*'],
    'components': [
        {'id': 'web', 'runtime': 'browser', 'paths': ['src/client/*'], 'depends_on': ['shared']},
        {'id': 'api', 'runtime': 'server', 'paths': ['src/server/*'], 'depends_on': ['shared']},
        {'id': 'shared', 'runtime': 'shared', 'paths': ['src/shared/*'], 'depends_on': []}],
    'contracts': [], 'dependency_check': 'boundary-imports', 'server_only_packages': ['private-db']}

# An intentionally explicit graph protocol fixture, NOT the production AST adapter.
# The Node suite independently exercises the real JS/TS parser and CLI.
ADAPTER = '''import json, os
from pathlib import Path
root = Path(os.environ['PIPELINE_EVIDENCE_DIR'])
data = json.loads((root / 'artifacts/boundary-input.json').read_text())
edges = []
for name in data['files']:
    value = Path(name).read_text().strip()
    if value.startswith('fixture-import:'):
        edges.append({'from': name, 'to': value.split(':', 1)[1]})
graph = {'schema_version': '1.0', 'files': data['files'], 'edges': edges, 'unresolved': []}
(root / 'artifacts/boundary-graph.json').write_text(json.dumps(graph))
print('Fixture graph adapter executed')
'''


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.f = test_lifecycle.LifecycleTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root, self.task = self.f.root, self.f.task
        self.config = copy.deepcopy(self.f.config)
        self.config['approval_policy'] = 'standard'
        self.config['boundaries'] = copy.deepcopy(MODEL)
        self.config['verification']['policy_checks'] = []
        for profile in ('Baseline', 'Fast', 'Full', 'Release'):
            self.config['verification']['requirements']['backend'][profile] = ['unit']
        self.config['verification']['commands'].append({
            'id': 'boundary-imports', 'enabled': True, 'profiles': sorted(boundaries.PROFILES),
            'argv': [sys.executable, 'graph_fixture.py'], 'cwd': '.', 'timeout_seconds': 20,
            'artifacts': [boundaries.GRAPH], 'environment': 'test'})
        atomic_text(self.root / 'src/client/page.ts', 'fixture-import:src/shared/types.ts')
        atomic_text(self.root / 'src/server/api.ts', 'fixture-import:src/shared/types.ts')
        atomic_text(self.root / 'src/shared/types.ts', 'Fixture neutral contract types')
        atomic_text(self.root / 'graph_fixture.py', ADAPTER)
        self.save()
        self.f.git('add', '.')
        self.f.git('commit', '-qm', 'Boundary protocol fixture baseline')
        prepare_task(self.root, self.task)

    def save(self):
        atomic_json(self.root / 'pipeline.config.yaml', self.config)

    def graph(self, edges=None):
        snapshot = code_snapshot(self.root, self.config)
        run_dir = self.root / 'Reports/Pipeline/graph-fixture'
        data = boundaries.prepare_input(self.root, self.config, run_dir, snapshot)
        graph = {'schema_version': '1.0', 'files': data['files'], 'edges': edges or [], 'unresolved': []}
        atomic_json(run_dir / boundaries.GRAPH, graph)
        return run_dir, snapshot, graph

    def verify(self, edges):
        directory, snapshot, _ = self.graph(edges)
        return boundaries.validate_graph(self.root, self.config, directory, snapshot)

    def test_legacy_absence_is_reported_not_silently_claimed_isolated(self):
        self.config.pop('boundaries')
        self.save()
        result = policy_check(self.root, kit=True)
        self.assertTrue(any('NOT_CONFIGURED' in warning for warning in result['warnings']))

    def test_browser_and_server_can_depend_on_shared_only_when_declared(self):
        self.assertEqual([], self.verify([
            {'from': 'src/client/page.ts', 'to': 'src/shared/types.ts'},
            {'from': 'src/server/api.ts', 'to': 'src/shared/types.ts'}]))
        self.config['boundaries']['components'][0]['depends_on'] = []
        self.assertTrue(self.verify([{'from': 'src/client/page.ts', 'to': 'src/shared/types.ts'}]))

    def test_browser_server_and_transitive_shared_server_imports_fail(self):
        for source, target in [('src/client/page.ts', 'src/server/api.ts'),
                               ('src/shared/types.ts', 'src/server/api.ts'),
                               ('src/server/api.ts', 'src/client/page.ts')]:
            with self.subTest(source=source):
                self.assertTrue(self.verify([{'from': source, 'to': target}]))

    def test_server_only_packages_are_denied_to_browser_and_shared(self):
        for source in ('src/client/page.ts', 'src/shared/types.ts'):
            for package in ('node:fs', 'private-db'):
                self.assertTrue(self.verify([{'from': source, 'external': package}]))
        self.assertEqual([], self.verify([{'from': 'src/server/api.ts', 'external': 'node:fs'}]))

    def test_unclassified_overlap_empty_and_omitted_component_files_fail(self):
        atomic_text(self.root / 'src/orphan.ts', 'not assigned')
        with self.assertRaisesRegex(PipelineError, 'exactly one'):
            boundaries.inventory(self.root, self.config)
        self.config['boundaries']['components'].append(
            {'id': 'extra', 'runtime': 'shared', 'paths': ['src/*'], 'depends_on': []})
        with self.assertRaisesRegex(PipelineError, 'exactly one'):
            boundaries.inventory(self.root, self.config)
        self.config['boundaries']['components'] = [
            {'id': 'empty', 'runtime': 'browser', 'paths': ['missing/*'], 'depends_on': []}]
        self.config['boundaries']['source_patterns'] = ['missing/*']
        with self.assertRaisesRegex(PipelineError, 'empty'):
            boundaries.inventory(self.root, self.config)

    def test_coverage_hashes_unknown_edges_and_unresolved_analysis_fail(self):
        for mutation in ('missing', 'hash', 'unknown', 'unresolved', 'malformed'):
            directory, snapshot, graph = self.graph()
            if mutation == 'missing': graph['files'].pop('src/client/page.ts')
            if mutation == 'hash': graph['files']['src/client/page.ts'] = '0' * 64
            if mutation == 'unknown': graph['edges'] = [{'from': 'src/client/page.ts', 'to': 'outside.ts'}]
            if mutation == 'unresolved': graph['unresolved'] = ['Computed dynamic import']
            atomic_json(directory / boundaries.GRAPH, graph)
            if mutation == 'malformed': atomic_text(directory / boundaries.GRAPH, '{invalid json')
            with self.subTest(mutation=mutation), self.assertRaises(PipelineError):
                boundaries.validate_graph(self.root, self.config, directory, snapshot)

    def test_forbidden_permission_unknown_components_and_bad_commands_rejected(self):
        for mutation in ('runtime', 'unknown', 'disabled', 'profile', 'cwd', 'duplicate'):
            config = copy.deepcopy(self.config)
            if mutation == 'runtime': config['boundaries']['components'][0]['depends_on'].append('api')
            if mutation == 'unknown': config['boundaries']['components'][0]['depends_on'].append('missing')
            if mutation == 'disabled': config['verification']['commands'][-1]['enabled'] = False
            if mutation == 'profile': config['verification']['commands'][-1]['profiles'] = ['Full']
            if mutation == 'cwd': config['verification']['commands'][-1]['cwd'] = 'src'
            if mutation == 'duplicate': config['boundaries']['components'].append(config['boundaries']['components'][0])
            atomic_json(self.root / 'pipeline.config.yaml', config)
            with self.subTest(mutation=mutation), self.assertRaises(PipelineError):
                load_config(self.root)

    def contract(self):
        self.config['boundaries']['contracts'] = [{
            'id': 'api', 'paths': ['src/shared/*'], 'provider': 'api', 'consumers': ['web'],
            'checks': {'provider': 'contract-provider', 'consumer': 'contract-consumer',
                       'compatibility': 'contract-compatibility', 'integration': 'integration'}}]

    def test_contracts_require_all_four_checks_and_real_parties(self):
        self.contract()
        wanted = required_checks(self.config, read_state(self.root, self.task), 'Full')
        self.assertTrue({'contract-provider', 'contract-consumer', 'contract-compatibility', 'integration'} <= set(wanted))
        self.config['boundaries']['contracts'][0]['consumers'] = ['missing']
        with self.assertRaises(PipelineError): boundaries.validate_config(self.root, self.config)
        self.config['boundaries']['contracts'][0]['consumers'] = ['web']
        self.config['boundaries']['contracts'][0]['checks']['integration'] = 'boundary-imports'
        with self.assertRaises(PipelineError): boundaries.validate_config(self.root, self.config)

    def test_actual_contract_bytes_bind_fingerprint_and_affect_both_sides(self):
        self.contract()
        self.save()
        state = read_state(self.root, self.task)
        before = source_fingerprint(self.root, self.config, state)
        atomic_text(self.root / 'src/shared/types.ts', 'Changed API shape')
        self.assertNotEqual(before, source_fingerprint(self.root, self.config, state))
        result = classify(self.root, self.config, state)
        self.assertTrue({'frontend', 'backend', 'api'} <= set(result['change_domains']))

    def test_deleted_contract_and_shared_changes_promote_consumers(self):
        self.contract()
        self.assertTrue({'frontend', 'backend', 'api'} <= boundaries.classify_paths(self.config, ['src/shared/deleted.ts']))
        self.config['boundaries']['contracts'] = []
        self.assertTrue({'frontend', 'backend'} <= boundaries.classify_paths(self.config, ['src/shared/types.ts']))

    def test_static_project_needs_no_backend_or_contract(self):
        config = copy.deepcopy(self.config)
        config['boundaries'].update(source_patterns=['src/client/*'], contracts=[], components=[
            {'id': 'web', 'runtime': 'browser', 'paths': ['src/client/*'], 'depends_on': []}])
        boundaries.validate_config(self.root, config)
        self.assertEqual({'src/client/page.ts'}, set(boundaries.inventory(self.root, config)))

    def test_policy_snapshot_changes_when_boundary_policy_changes(self):
        before = policy_snapshot(self.config)
        self.config['boundaries']['server_only_packages'].append('another-package')
        self.assertNotEqual(before, policy_snapshot(self.config))

    def test_real_profile_preserves_preexisting_violation_then_requires_repair(self):
        atomic_text(self.root / 'src/server/api.ts', 'fixture-import:src/client/page.ts')
        # Product bytes, unlike scope docs/contracts, do not change this task fingerprint.
        baseline = run_profile(self.root, self.task, 'Baseline', run_id='boundary-baseline')
        self.assertEqual('FAIL', baseline['status'])
        self.assertEqual('boundary-baseline', read_state(self.root, self.task)['baseline_run'])
        transition(self.root, self.task, 'READY')
        transition(self.root, self.task, 'IN_PROGRESS')
        failing = run_profile(self.root, self.task, 'Full', run_id='boundary-fail')
        self.assertEqual('FAIL', failing['status'])
        self.assertIsNone(read_state(self.root, self.task)['full_run'])
        atomic_text(self.root / 'src/server/api.ts', 'fixture-import:src/shared/types.ts')
        passing = run_profile(self.root, self.task, 'Full', run_id='boundary-pass')
        self.assertEqual('PASS', passing['status'], passing)
        validate_run(self.root, self.config, read_state(self.root, self.task), 'boundary-pass', 'Full')
        # Original Baseline remains usable as historical pre-change evidence.
        validate_run(self.root, self.config, read_state(self.root, self.task), 'boundary-baseline', 'Baseline', False)

    def test_dummy_success_without_graph_does_not_establish_baseline(self):
        for code in ("print('no graph')\n", "import os\nfrom pathlib import Path\nPath(os.environ['PIPELINE_EVIDENCE_DIR'], 'artifacts/boundary-graph.json').write_text('{invalid')\n"):
            atomic_text(self.root / 'graph_fixture.py', code)
            result = run_profile(self.root, self.task, 'Baseline')
            self.assertEqual('FAIL', result['status'])
            self.assertIsNone(read_state(self.root, self.task)['baseline_run'])

    def test_revalidation_rejects_graph_tampering_even_after_artifact_rehash(self):
        run_profile(self.root, self.task, 'Baseline')
        transition(self.root, self.task, 'READY')
        transition(self.root, self.task, 'IN_PROGRESS')
        result = run_profile(self.root, self.task, 'Full')
        directory = self.root / 'Reports/Pipeline' / result['run_id']
        graph = json.loads((directory / boundaries.GRAPH).read_text())
        graph['edges'] = [{'from': 'src/client/page.ts', 'to': 'src/server/api.ts'}]
        atomic_json(directory / boundaries.GRAPH, graph)
        for artifact in result['artifacts']:
            if artifact['path'] == boundaries.GRAPH:
                artifact.update(size=(directory / boundaries.GRAPH).stat().st_size, sha256=hash_file(directory / boundaries.GRAPH))
        atomic_json(directory / 'summary.json', result)
        with self.assertRaisesRegex(PipelineError, 'Boundary violations'):
            validate_run(self.root, self.config, read_state(self.root, self.task), result['run_id'], 'Full')


if __name__ == '__main__':
    unittest.main()
