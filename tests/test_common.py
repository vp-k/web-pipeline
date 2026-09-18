import copy
import json
from pathlib import Path
import tempfile
import unittest

from web_pipeline.common import (PipelineError, atomic_json, atomic_text, canonical_hash,
    code_snapshot, load_config, lock, safe_path, validate_schema)

ROOT = Path(__file__).resolve().parents[1] / 'kit'


class CommonTests(unittest.TestCase):
    def test_kit_config_and_all_schema_definitions(self):
        from jsonschema import Draft202012Validator
        config = load_config(ROOT, kit=True)
        self.assertEqual(len(config['risk']['protected_rules']), 20)
        for path in (ROOT / 'Schemas').glob('*.schema.json'):
            Draft202012Validator.check_schema(json.loads(path.read_text()))

    def test_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            for value in ('../outside', '/outside', 'C:/outside', 'a/../../outside', 'a:stream'):
                with self.subTest(value=value), self.assertRaises(PipelineError):
                    safe_path(folder, value)

    def test_lock_rejects_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as folder:
            with lock(folder, 'task-one'):
                with self.assertRaises(PipelineError):
                    with lock(folder, 'task-one'):
                        pass
            with lock(folder, 'task-one'):
                pass

    def test_atomic_utf8_and_canonical_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'nested' / 'value.json'
            atomic_json(path, {'name': '검증'})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'name':'검증'})
            self.assertEqual(canonical_hash({'a':1,'b':2}), canonical_hash({'b':2,'a':1}))

    def test_config_rejects_duplicate_and_unreachable_checks(self):
        config = load_config(ROOT, kit=True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pipeline.config.yaml'
            changed = copy.deepcopy(config)
            changed['verification']['commands'].append(changed['verification']['commands'][0])
            atomic_json(path, changed)
            with self.assertRaisesRegex(PipelineError, 'Duplicate'):
                load_config(folder, kit=True)
            changed = copy.deepcopy(config)
            next(x for x in changed['verification']['commands'] if x['id'] == 'migration-dry-run')['profiles'] = ['Release']
            atomic_json(path, changed)
            with self.assertRaisesRegex(PipelineError, 'cannot execute'):
                load_config(folder, kit=True)

    def test_schema_rejects_fake_minimal_state(self):
        with self.assertRaises(PipelineError):
            validate_schema(ROOT, 'state', {'status':'DONE','verification_status':'PASS'})

    def test_snapshot_ignores_evidence_but_detects_code(self):
        config = load_config(ROOT, kit=True)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_text(root / 'app.py', 'one')
            before = code_snapshot(root, config)
            atomic_text(root / 'Reports/Pipeline/run/summary.json', '{}')
            atomic_text(root / 'Docs/Work/TASK/STATE.md', 'state')
            self.assertEqual(before, code_snapshot(root, config))
            atomic_text(root / 'app.py', 'two')
            self.assertNotEqual(before['tree_digest'], code_snapshot(root, config)['tree_digest'])

    def test_generated_build_output_does_not_invalidate_sources(self):
        config = load_config(ROOT, kit=True)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_text(root / 'app.js','export const answer = 42')
            before = code_snapshot(root,config)
            atomic_text(root / 'dist/app.js','compiled bundle')
            self.assertEqual(before['tree_digest'],code_snapshot(root,config)['tree_digest'])

    def test_generated_exclusions_cannot_hide_governance(self):
        config = load_config(ROOT, kit=True)
        with tempfile.TemporaryDirectory() as folder:
            config['project']['generated_paths'] = ['Scripts']
            atomic_json(Path(folder) / 'pipeline.config.yaml',config)
            with self.assertRaisesRegex(PipelineError,'hide governance'):
                load_config(folder,kit=True)


if __name__ == '__main__':
    unittest.main()
