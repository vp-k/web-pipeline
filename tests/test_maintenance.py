import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from web_pipeline import maintenance as m
from web_pipeline.cli import _init
from web_pipeline.common import PipelineError, atomic_json, atomic_text, hash_file

ROOT = Path(__file__).resolve().parents[1] / 'kit'


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.old, self.new, self.target = [self.work / name for name in ('old','new','project')]
        for root in (self.old,self.new):
            for folder in m.MANAGED:
                shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            shutil.copy2(ROOT / 'pipeline.config.yaml', root / 'pipeline.config.yaml')
        atomic_text(self.old / 'web_pipeline/__init__.py', '__version__ = "2.6.0"\n')
        atomic_text(self.new / 'web_pipeline/__init__.py', '__version__ = "2.7.0"\n')
        atomic_text(self.new / 'Scripts/new-check.py', 'print("new")\n')
        shutil.copytree(self.old, self.target)
        config = json.loads((self.target / 'pipeline.config.yaml').read_text())
        config['project']['mode'] = 'project'
        atomic_json(self.target / 'pipeline.config.yaml',config)
        atomic_json(self.target / m.RECEIPT, m.receipt(self.target))
        for rel in ('AGENTS.md','Docs/Work/A/STATE.md','Docs/Work/A/decision.json','src/app.js','Reports/Pipeline/old/summary.json'):
            atomic_text(self.target / rel, 'User bytes, not a real workflow fixture\n')

    def hashes(self):
        return {p.relative_to(self.target).as_posix():hash_file(p) for p in self.target.rglob('*') if p.is_file()}

    def test_maintenance_reclaims_a_dead_lock_but_a_live_one_still_blocks(self):
        from tests.test_friction import dead_pid
        def dead_lock(name):
            atomic_text(self.target / f'.pipeline-locks/{name}.lock',
                        json.dumps({'pid': dead_pid(), 'started_utc': '2026-01-01T00:00:00Z'}))
        dead_lock('task-A')
        applied = m.upgrade(self.new, self.target, apply=True)  # a crashed run must not block maintenance forever
        self.assertEqual('APPLIED', applied['mode'])
        self.assertFalse((self.target / '.pipeline-locks/task-A.lock').exists())
        dead_lock('task-A')
        m.restore(self.target, applied['transaction'])
        self.assertFalse((self.target / '.pipeline-locks/task-A.lock').exists())
        applied = m.upgrade(self.new, self.target, apply=True)
        atomic_text(self.target / '.pipeline-locks/task-B.lock',
                    json.dumps({'pid': os.getpid(), 'started_utc': '2026-01-01T00:00:00Z'}))
        with self.assertRaisesRegex(PipelineError, 'Stop active pipeline operations.*task-B'):
            m.restore(self.target, applied['transaction'])

    def test_preview_no_writes_apply_preserves_data_restore_exact(self):
        before = self.hashes()
        plan = m.upgrade(self.new, self.target)
        self.assertFalse(plan['writes']); self.assertEqual(before, self.hashes())
        applied = m.upgrade(self.new, self.target, apply=True)
        self.assertEqual('APPLIED', applied['mode'])
        self.assertEqual(m.inventory(self.new), m.inventory(self.target))
        for rel, digest in before.items():
            if rel.split('/')[0] not in m.MANAGED and rel != m.RECEIPT:
                self.assertEqual(digest, hash_file(self.target / rel))
        m.restore(self.target, applied['transaction'])
        after = {p:h for p,h in self.hashes().items() if not p.startswith(m.HISTORY + '/')}
        self.assertEqual(before, after)

    def test_local_edits_missing_and_added_managed_files_block_all_writes(self):
        for action in ('edit','remove','add'):
            with self.subTest(action=action):
                file = self.target / 'Schemas/new-local.json'
                if action == 'add': atomic_text(file, 'local')
                else:
                    file = self.target / 'web_pipeline/__init__.py'
                    if action == 'edit': atomic_text(file, '__version__ = "2.6.0"\n# local\n')
                    else: file.unlink()
                before = self.hashes()
                with self.assertRaisesRegex(PipelineError,'modified/missing'): m.upgrade(self.new, self.target, apply=True)
                self.assertEqual(before, self.hashes())
                if action == 'add': file.unlink()
                else: shutil.copy2(self.old / 'web_pipeline/__init__.py', file)

    def test_legacy_requires_original_baseline_and_preserves_no_receipt_on_restore(self):
        (self.target / m.RECEIPT).unlink()
        with self.assertRaisesRegex(PipelineError,'baseline'): m.upgrade(self.new, self.target)
        applied = m.upgrade(self.new, self.target, baseline=self.old, apply=True)
        m.restore(self.target, applied['transaction'])
        self.assertFalse((self.target / m.RECEIPT).exists())

    def test_changed_after_preview_is_rechecked(self):
        m.upgrade(self.new, self.target)
        atomic_text(self.target / 'Schemas/local.json', 'changed after preview')
        with self.assertRaises(PipelineError): m.upgrade(self.new, self.target, apply=True)

    def test_partial_copy_can_restore_and_blocks_another_upgrade(self):
        before = self.hashes(); original = m._atomic_copy
        def fail(source, target):
            if target.resolve() == (self.target / 'web_pipeline/__init__.py').resolve(): raise OSError('Simulated interruption')
            return original(source,target)
        with patch.object(m,'_atomic_copy',side_effect=fail), self.assertRaises(OSError):
            m.upgrade(self.new,self.target,apply=True)
        transaction = next((self.target / m.HISTORY).iterdir()).name
        with self.assertRaisesRegex(PipelineError,'Unfinished'): m.upgrade(self.new,self.target,apply=True)
        m.restore(self.target,transaction)
        self.assertEqual(before,{p:h for p,h in self.hashes().items() if not p.startswith(m.HISTORY + '/')})

    def test_post_upgrade_edit_and_tampered_backup_block_restore(self):
        result = m.upgrade(self.new,self.target,apply=True)
        target = self.target / 'Scripts/new-check.py'
        atomic_text(target,'user work')
        before = self.hashes()
        with self.assertRaisesRegex(PipelineError,'user edit'): m.restore(self.target,result['transaction'])
        self.assertEqual(before,self.hashes())
        shutil.copy2(self.new / 'Scripts/new-check.py',target)
        atomic_text(self.target / m.HISTORY / result['transaction'] / 'backup/web_pipeline/__init__.py','tampered')
        with self.assertRaisesRegex(PipelineError,'Backup hash'): m.restore(self.target,result['transaction'])

    def test_active_operation_and_unknown_old_version_block(self):
        atomic_text(self.target / '.pipeline-locks/task-x.lock','active fixture')
        with self.assertRaisesRegex(PipelineError,'active'): m.upgrade(self.new,self.target,apply=True)
        (self.target / '.pipeline-locks/task-x.lock').unlink()
        atomic_text(self.target / 'web_pipeline/__init__.py','__version__ = "2.5.0"\n')
        atomic_json(self.target / m.RECEIPT,m.receipt(self.target))
        with self.assertRaisesRegex(PipelineError,'2.6'): m.upgrade(self.new,self.target)

    def test_adoption_preview_preserves_conflicts_and_missing_target(self):
        target = self.work / 'adopt'
        self.assertTrue(_init(ROOT,target,preview=True)['can_adopt']); self.assertFalse(target.exists())
        atomic_text(target / 'PIPELINE.md','user instructions')
        preview = _init(ROOT,target,preview=True)
        self.assertFalse(preview['can_adopt']); self.assertEqual('user instructions',(target/'PIPELINE.md').read_text())
        self.assertEqual(1,len(list(target.iterdir())))

    def test_diagnosis_is_read_only_and_not_boundary_pass(self):
        before = self.hashes()
        self.assertEqual('NOT_CONFIGURED',m.diagnose(self.target)['boundaries'])
        self.assertEqual(before,self.hashes())

    def test_pipeline_lock_refuses_to_start_during_upgrade(self):
        from web_pipeline.common import lock
        with lock(self.target,'upgrade'):
            with self.assertRaisesRegex(PipelineError,'maintenance'):
                with lock(self.target,'task-fixture'): self.fail('Must not enter task action')
        self.assertFalse(list((self.target / '.pipeline-locks').glob('*.lock')))

    def test_interrupted_restore_can_resume(self):
        before = self.hashes()
        result = m.upgrade(self.new,self.target,apply=True)
        with patch.object(m,'_atomic_copy',side_effect=OSError('Interrupted restore')), self.assertRaises(OSError):
            m.restore(self.target,result['transaction'])
        with self.assertRaisesRegex(PipelineError,'Unfinished'): m.upgrade(self.new,self.target,apply=True)
        m.restore(self.target,result['transaction'])
        self.assertEqual(before,{p:h for p,h in self.hashes().items() if not p.startswith(m.HISTORY + '/')})

    def test_traversal_receipt_and_nested_source_refused(self):
        data = m.receipt(self.target)
        data['files']['Scripts/../../user.txt'] = 'a'*64
        atomic_json(self.target / m.RECEIPT,data)
        before = self.hashes()
        with self.assertRaises(PipelineError): m.upgrade(self.new,self.target,apply=True)
        self.assertEqual(before,self.hashes())
        with self.assertRaises(PipelineError): m.upgrade(self.target,self.target / 'nested')

    def test_untouched_engine_file_edit_blocks_restore_too(self):
        result = m.upgrade(self.new,self.target,apply=True)
        atomic_text(self.target / 'Schemas/local-after.json','user work')
        with self.assertRaisesRegex(PipelineError,'managed edit'): m.restore(self.target,result['transaction'])

    def test_inventory_canonicalizes_relative_and_windows_short_roots(self):
        expected = m.inventory(self.target.resolve())
        self.assertEqual(expected,m.inventory(self.target))
        original_cwd = Path.cwd()
        try:
            os.chdir(self.work)
            self.assertEqual(expected,m.inventory(Path('project')))
        finally: os.chdir(original_cwd)
