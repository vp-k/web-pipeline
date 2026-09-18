"""Regressions from the whole-kit review, using actual child processes and gates."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from web_pipeline import autopilot
from web_pipeline.common import PipelineError, atomic_json, atomic_text, hash_file, read_state
from web_pipeline.evidence import failure_fingerprint
from web_pipeline.runner import _execute, run_profile
from web_pipeline.state import archive_task, create_task, policy_check
from tests import test_archive, test_scopes, test_simplified_approvals


class RuntimeArchiveFixes(unittest.TestCase):
    def test_timeout_kills_descendants_before_their_delayed_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic_text(root / 'child.py',
                        'import time\nfrom pathlib import Path\ntime.sleep(3)\nPath("late.txt").write_text("late")\n')
            atomic_text(root / 'parent.py',
                        'import subprocess, sys, time\nsubprocess.Popen([sys.executable, "-B", "child.py"], '
                        'stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\ntime.sleep(30)\n')
            result = _execute({'id': 'timeout', 'argv': [sys.executable, '-B', 'parent.py'],
                               'timeout_seconds': 1}, root, root / 'report')
            time.sleep(3.2)
            self.assertEqual('timeout', result['reason'], result)
            self.assertFalse((root / 'late.txt').exists(), result)

    def test_successful_parent_cannot_leave_writer_running(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic_text(root / 'child.py',
                        'import time\nfrom pathlib import Path\ntime.sleep(3)\nPath("late.txt").write_text("late")\n')
            atomic_text(root / 'parent.py',
                        'import subprocess, sys\nsubprocess.Popen([sys.executable, "-B", "child.py"], '
                        'stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n')
            result = _execute({'id': 'orphan', 'argv': [sys.executable, '-B', 'parent.py'],
                               'timeout_seconds': 1}, root, root / 'report')
            time.sleep(3.2)
            self.assertFalse((root / 'late.txt').exists(), result)
            self.assertEqual('FAIL', result['status'], result)

    def test_failure_identity_uses_error_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identities = []
            for index, source in enumerate(('assert False, "first failure"', '1 / 0', '{}["missing"]')):
                atomic_text(root / 'check.py', source + '\n')
                run = root / f'run-{index}'
                result = _execute({'id': 'unit', 'argv': [sys.executable, '-B', 'check.py']}, root, run)
                identities.append(failure_fingerprint([result], run_dir=run))
            self.assertEqual(3, len(set(identities)))

    def test_failure_identity_ignores_progress_and_volatile_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identities = []
            for index in (1, 2):
                run = root / f'run-{index}'
                atomic_text(run / 'unit.log', f'progress {index}\n'
                            f'2026-09-14T07:30:0{index}Z AssertionError: mismatch pid={index} in {index}.2 seconds\n')
                identities.append(failure_fingerprint([{'id': 'unit', 'status': 'FAIL',
                    'exit_code': 1, 'reason': 'exit code 1', 'log': 'unit.log'}], run_dir=run))
            self.assertEqual(*identities)

    def test_different_failures_do_not_exhaust_same_failure_guard(self):
        f = test_simplified_approvals.SimplifiedApprovalTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.f.baseline_and_start()
        for source in ('assert False, "first failure"', '1 / 0', '{}["missing"]'):
            atomic_text(f.root / 'check.py', source + '\n')
            result = run_profile(f.root, f.task, 'Fast')
            self.assertEqual('FAIL', result['status'])
            self.assertEqual(1, read_state(f.root, f.task)['iteration']['same_failure'])
        atomic_text(f.root / 'check.py', 'assert 2 + 2 == 4\n')
        self.assertEqual('PASS', run_profile(f.root, f.task, 'Fast')['status'])
        self.assertEqual(3, read_state(f.root, f.task)['iteration']['failed_attempts'])

    def _done(self):
        fixture = test_archive.ArchiveTests()
        self.addCleanup(fixture.doCleanups)
        return fixture._done_fixture()

    def test_repeated_real_error_still_stops_after_three_failures(self):
        f = test_simplified_approvals.SimplifiedApprovalTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.f.baseline_and_start()
        for index in range(3):
            atomic_text(f.root / 'check.py', f'print("progress {index}")\nraise ValueError("same defect")\n')
            self.assertEqual('FAIL', run_profile(f.root, f.task, 'Fast')['status'])
        self.assertEqual(3, read_state(f.root, f.task)['iteration']['same_failure'])
        with self.assertRaisesRegex(PipelineError, 'same-failure'):
            run_profile(f.root, f.task, 'Fast')

    def test_archive_cannot_bypass_failed_merge_gate(self):
        f = self._done()
        create_task(f.root, 'TASK-UNFINISHED', 'Other work', 'T1', ['backend'], base_ref='HEAD')
        plan = {'objective': 'Explicit merge gate', 'completion_gate': 'merge',
                'tasks': [{'task_id': f.task, 'depends_on': []}]}
        autopilot.start(f.root, plan, f.trust)
        queue = hash_file(f.root / autopilot.QUEUE)
        with self.assertRaisesRegex(PipelineError, 'queue to complete'):
            archive_task(f.root, f.task, trust_path=f.trust)
        self.assertEqual(queue, hash_file(f.root / autopilot.QUEUE))
        self.assertTrue((f.root / f'Docs/Work/{f.task}/STATE.md').is_file())

    def test_archive_rename_failure_restores_queue_and_state(self):
        f = self._done()
        plan = {'objective': 'Archive rollback', 'tasks': [{'task_id': f.task, 'depends_on': []}]}
        queue = autopilot.start(f.root, plan, f.trust)
        state_hash = hash_file(f.root / f'Docs/Work/{f.task}/STATE.md')
        original = Path.rename
        def fail_target(path, target):
            if Path(target).parent == f.root / 'Docs/Archive':
                raise OSError('injected filesystem failure')
            return original(path, target)
        with patch.object(Path, 'rename', fail_target), self.assertRaisesRegex(PipelineError, 'rolled back'):
            archive_task(f.root, f.task, trust_path=f.trust)
        self.assertEqual(state_hash, hash_file(f.root / f'Docs/Work/{f.task}/STATE.md'))
        self.assertEqual(queue['queue_id'], autopilot.status(f.root)['queue_id'])
        self.assertFalse((f.root / f'Docs/Work/{f.task}/SOURCE.zip').exists())
        self.assertFalse((f.root / 'Docs/Work/ARCHIVE_PENDING.json').exists())

    def test_interrupted_archive_blocks_gates_until_recovered(self):
        from web_pipeline.archival import OUTPUTS, recover_archive
        f = self._done()
        result = archive_task(f.root, f.task, trust_path=f.trust)
        folder = f.root / result['path']
        journal = {'entries': [{'task_id': f.task, 'revision': 1,
                    'state_sha256': hash_file(folder / 'STATE.md'),
                    'outputs': {name: hash_file(folder / name) for name in OUTPUTS}}], 'queue': None}
        atomic_json(f.root / 'Docs/Work/ARCHIVE_PENDING.json', journal)
        self.assertEqual('FAIL', policy_check(f.root, kit=True)['status'])
        with self.assertRaisesRegex(PipelineError, 'archive --recover'):
            create_task(f.root, 'TASK-NEXT', 'Blocked until recovery', 'T1', ['backend'], base_ref='HEAD')
        self.assertEqual('RECOVERED', recover_archive(f.root)['status'])
        self.assertEqual('DONE', read_state(f.root, f.task)['status'])
        self.assertFalse(folder.exists())

    def test_archived_completed_queue_allows_next_queue(self):
        fixture = test_archive.ArchiveTests()
        self.addCleanup(fixture.doCleanups)
        f = fixture._done_fixture()
        plan = {'objective': 'Archive completed work', 'tasks': [{'task_id': f.task, 'depends_on': []}]}
        queue = autopilot.start(f.root, plan, f.trust)
        self.assertEqual('COMPLETE', autopilot.advance(f.root, trust=f.trust)['status'])
        archive_task(f.root, f.task, trust_path=f.trust)
        create_task(f.root, 'TASK-NEXT', 'Next task', 'T1', ['backend'], base_ref='HEAD')
        plan['tasks'] = [{'task_id': 'TASK-NEXT', 'depends_on': []}]
        self.assertEqual('STARTED', autopilot.start(f.root, plan, f.trust)['status'])
        self.assertTrue((f.root / f"Docs/Work/AUTOPILOT-{queue['queue_id']}.json").is_file())

    def test_phase_and_historical_member_archive_together(self):
        f = test_scopes.ScopeTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.start()
        atomic_text(f.root / 'a.py', 'value = 1\n# member change\n')
        member_run = f.finish()
        phase = 'PHASE-ARCHIVE'
        f.new(phase, ['a', 'b'], [f.task])
        f.start(phase)
        atomic_text(f.root / 'b.py', 'value = 2\n# integrated change\n')
        phase_run = f.finish(phase)
        for task in (f.task, phase):
            with self.assertRaisesRegex(PipelineError, '--include-members'):
                archive_task(f.root, task)
        plan = {'objective': 'Archive integrated group', 'tasks': [
            {'task_id': f.task, 'depends_on': []}, {'task_id': phase, 'depends_on': [f.task]}]}
        queue = autopilot.start(f.root, plan)
        original = Path.rename
        moved = []
        def fail_second(path, target):
            if Path(target).parent == f.root / 'Docs/Archive':
                moved.append(path.name)
                if len(moved) == 2:
                    raise OSError('injected second move failure')
            return original(path, target)
        with patch.object(Path, 'rename', fail_second), self.assertRaisesRegex(PipelineError, 'rolled back'):
            archive_task(f.root, phase, include_members=True)
        for task in (phase, f.task):
            self.assertTrue((f.root / f'Docs/Work/{task}/STATE.md').is_file())
            self.assertFalse((f.root / f'Docs/Work/{task}/SOURCE.zip').exists())
        self.assertEqual(queue['queue_id'], autopilot.status(f.root)['queue_id'])
        archive_task(f.root, phase, include_members=True)
        for task in (phase, f.task):
            self.assertFalse((f.root / f'Docs/Work/{task}').exists())
            self.assertTrue((f.root / f'Docs/Archive/{task}-r1/STATE.md').is_file())
        metadata = json.loads((f.root / f'Docs/Archive/{f.task}-r1/ARCHIVE.json').read_text())
        self.assertEqual(member_run['run_id'], metadata['runs']['full'])
        self.assertEqual(phase_run['run_id'], metadata['phase_coverage']['run_id'])
        self.assertNotEqual(member_run['snapshot']['tree_digest'], metadata['source_bundle']['tree_digest'])
        self.assertFalse((f.root / autopilot.QUEUE).exists())
        self.assertTrue((f.root / f"Docs/Work/AUTOPILOT-{queue['queue_id']}.json").is_file())


if __name__ == '__main__':
    unittest.main()
