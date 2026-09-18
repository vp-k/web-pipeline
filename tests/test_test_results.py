"""Protocol fixtures are parser tests, not substitutes for real web coverage."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from web_pipeline.common import PipelineError, atomic_json, atomic_text, read_state, source_fingerprint, write_state
from web_pipeline.test_results import validate_report
from web_pipeline.runner import run_profile, validate_run
from tests import test_baseline_regression


class TestReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run = Path(temp.name) / 'run-001'
        self.run.mkdir()
        self.command = {'id':'unit','test_report':{'path':'artifacts/tests.json','min_tests':1,'max_skipped':0,'required_groups':['unit']}}
        self.data = {'schema_version':'1.0','run_id':'run-001','check_id':'unit','completed':True,'errors':[],
                     'tests':[{'id':'one','group':'unit','status':'passed','duration_ms':1}]}

    def check(self, data=None, **kwargs):
        atomic_json(self.run / 'artifacts/tests.json', self.data if data is None else data)
        return validate_report(self.run, self.run, self.command, **kwargs)

    def test_valid_counts_and_explicit_skip_allowance(self):
        self.assertEqual({'executed':1,'skipped':0,'failures':0}, self.check())
        self.command['test_report']['max_skipped'] = 1
        self.data['tests'].append({'id':'two','group':'unit','status':'skipped','duration_ms':0})
        self.assertEqual(1, self.check()['skipped'])

    def test_zero_skips_failure_errors_incomplete_stale_and_duplicates_rejected(self):
        variants = []
        for field, value in [('tests',[]),('completed',False),('errors',['setup failed']),('run_id','old'),('check_id','other')]:
            data = copy.deepcopy(self.data); data[field] = value; variants.append(data)
        for field, value in [('status','skipped'),('status','failed'),('status','error'),('group','wrong'),('duration_ms',float('nan'))]:
            data = copy.deepcopy(self.data); data['tests'][0][field] = value; variants.append(data)
        data = copy.deepcopy(self.data); data['tests'] *= 2; variants.append(data)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(PipelineError): self.check(data)

    def test_missing_malformed_and_unsafe_report(self):
        with self.assertRaises(PipelineError): validate_report(self.run, self.run, self.command)
        for value in ['{', '{"tests":[],"tests":[]}', 'null']:
            atomic_text(self.run / 'artifacts/tests.json', value)
            with self.assertRaises(PipelineError): validate_report(self.run, self.run, self.command)
        self.command['test_report']['path'] = '../outside.json'
        with self.assertRaises(PipelineError): validate_report(self.run, self.run, self.command)

    def test_baseline_can_record_real_failures_but_not_incomplete_execution(self):
        self.data['tests'][0]['status'] = 'failed'
        self.assertEqual(1, self.check(allow_failures=True)['failures'])
        self.data['completed'] = False
        with self.assertRaises(PipelineError): self.check(allow_failures=True)


class ReportGateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_baseline_regression.BaselineRegressionTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.command = next(c for c in f.config['verification']['commands'] if c['id'] == 'unit')
        self.command['test_report'] = {'path':'artifacts/tests.json','min_tests':1,'max_skipped':0,'required_groups':['unit']}
        self.command['argv'][-1] = 'report.py'
        atomic_json(f.root / 'pipeline.config.yaml', f.config)
        state = read_state(f.root, 'TASK-BASE')
        state['fingerprint'] = source_fingerprint(f.root, f.config, state); write_state(f.root, state)

    def script(self, cases, exit_code=0):
        atomic_text(self.fixture.root / 'report.py',
            "import json, os\nfrom pathlib import Path\nr=Path(os.environ['PIPELINE_EVIDENCE_DIR'])\n(r/'artifacts').mkdir(exist_ok=True)\n"
            "data=dict(schema_version='1.0',run_id=r.name,check_id=os.environ['PIPELINE_CHECK_ID'],completed=True,errors=[],tests=" + repr(cases) + ")\n"
            "(r/'artifacts/tests.json').write_text(json.dumps(data))\nraise SystemExit(" + str(exit_code) + ")\n")

    def test_zero_exit_zero_tests_is_fail_and_not_baseline(self):
        self.script([])
        summary = run_profile(self.fixture.root, 'TASK-BASE', 'Baseline')
        unit = next(c for c in summary['checks'] if c['id'] == 'unit')
        self.assertEqual('FAIL', unit['status']); self.assertEqual(0, unit['exit_code'])
        self.assertIsNone(read_state(self.fixture.root, 'TASK-BASE')['baseline_run'])

    def test_real_failed_baseline_and_gate_revalidation(self):
        self.script([{'id':'case','group':'unit','status':'failed','duration_ms':1}], 1)
        f = self.fixture
        summary = run_profile(f.root, 'TASK-BASE', 'Baseline')
        self.assertEqual(summary['run_id'], read_state(f.root, 'TASK-BASE')['baseline_run'])
        run = f.root / 'Reports/Pipeline' / summary['run_id']
        data = json.loads((run / 'artifacts/tests.json').read_text()); data['tests'] = []
        atomic_json(run / 'artifacts/tests.json', data)
        # Even if a local summary is rehashed, semantic gate validation must fail.
        from web_pipeline.evidence import collect_artifacts
        summary['artifacts'] = collect_artifacts(run)
        atomic_json(run / 'summary.json', summary)
        with self.assertRaisesRegex(PipelineError, 'Insufficient'):
            validate_run(f.root, f.config, read_state(f.root, 'TASK-BASE'), summary['run_id'], require_current=False)
