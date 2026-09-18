import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_pipeline.common import PipelineError
from web_pipeline.evidence import (collect_artifacts, required_checks,
                                   validate_artifact_hashes, validate_screenshots)
from web_pipeline.runner import _enforce_iteration_limits, _execute, _validate_argv


class RunnerSafetyTests(unittest.TestCase):
    def test_timestamp_pyc_collision_cannot_hide_changed_source(self):
        import py_compile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = root / 'app.py'
            module.write_text('value = 4\n', encoding='utf-8')
            os.utime(module, (1700000000, 1700000000))
            py_compile.compile(str(module), doraise=True)
            module.write_text('value = 8\n', encoding='utf-8')
            os.utime(module, (1700000000, 1700000000))
            run = root / 'run'
            run.mkdir()
            result = _execute({'id': 'unit', 'argv': [sys.executable, '-c',
                'from app import value; assert value == 4, value'], 'cwd': '.',
                'timeout_seconds': 10, 'environment': 'test'}, root, run)
            self.assertEqual('FAIL', result['status'], result)
            self.assertIn('AssertionError: 8', (run / result['log']).read_text())

    def test_rejects_compound_shells_and_production(self):
        for argv in (["sh", "-c", "echo unsafe"], ["cmd.exe", "/c", "echo unsafe"],
                     ["pwsh", "-Command", "Write-Host unsafe"],
                     ["pwsh", "-co", "Write-Host unsafe"],
                     ["powershell", "-ec", "AAAA"],
                     ["pwsh", "Write-Host unsafe"]):
            with self.subTest(argv=argv), self.assertRaises(PipelineError):
                _validate_argv({"id": "x", "argv": argv, "environment": "test"})
        with self.assertRaises(PipelineError):
            _validate_argv({"id": "x", "argv": [sys.executable, "x.py"], "environment": "production"})

    def test_executes_argv_without_shell_and_records_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            run.mkdir()
            result = _execute({"id": "unit", "argv": [sys.executable, "-c", "print('ok')"],
                               "cwd": ".", "timeout_seconds": 5, "environment": "test"}, root, run)
            self.assertEqual("PASS", result["status"])
            self.assertEqual("ok\n", (run / result["log"]).read_text())

    def test_spawn_failure_is_durable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            run.mkdir()
            result = _execute({"id": "unit", "argv": [str(root / "absent")], "cwd": ".",
                               "timeout_seconds": 1, "environment": "test"}, root, run)
            self.assertEqual("BLOCKED", result["status"])
            self.assertIn("runner error", (run / result["log"]).read_text())

    def test_timeout_is_finite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            run.mkdir()
            result = _execute({"id": "unit", "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
                               "cwd": ".", "timeout_seconds": .05, "environment": "test"}, root, run)
            self.assertEqual("FAIL", result["status"])
            self.assertEqual("timeout", result["reason"])
            self.assertLess(result["duration_ms"], 5000)

    def test_log_cleanup_failure_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch('web_pipeline.process_tree.wait_log_release',
                       side_effect=RuntimeError('log handle cleanup deadline')):
                result = _execute({'id': 'unit', 'argv': [sys.executable, '-c', 'pass'],
                                   'timeout_seconds': 5}, root, root / 'run')
            self.assertEqual('BLOCKED', result['status'])
            self.assertIsNone(result['exit_code'])
            self.assertIn('cleanup deadline', result['reason'])
            self.assertIn('runner error', (root / 'run' / result['log']).read_text())

    def test_release_inherits_full_requirements(self):
        config = {"verification": {"requirements": {"backend": {
            "Full": ["unit", "integration"], "Release": ["audit"]}}}, "risk": {"protected_rules": {}}}
        state = {"change_domains": ["backend"], "protected_changes": []}
        self.assertEqual(["audit", "integration", "unit"], required_checks(config, state, "Release"))

    def test_iteration_limits_are_hard_stops(self):
        config = {"iteration_limits": {"total_attempts": 2, "same_failure": 3,
                                       "external_retries": 2, "elapsed_minutes": 120}}
        with self.assertRaisesRegex(PipelineError, "total attempt"):
            _enforce_iteration_limits(config, {"iteration": {"attempts": 2}})

    def test_missing_required_check_is_not_pass(self):
        config = {"verification": {"requirements": {"backend": {"Full": ["unit"]}}},
                  "risk": {"protected_rules": {}}}
        self.assertEqual(["unit"], required_checks(config, {"change_domains": ["backend"],
                                                            "protected_changes": []}, "Full"))

    def test_artifact_hash_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            artifact = run / "artifacts" / "result.txt"
            artifact.parent.mkdir()
            artifact.write_text("original")
            manifest = collect_artifacts(run, ["artifacts/*.txt"])
            artifact.write_text("tampered")
            with self.assertRaisesRegex(PipelineError, "integrity"):
                validate_artifact_hashes(run, manifest)

    def test_screenshot_manifest_checks_decoded_dimensions(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run"
            screenshots = run / "screenshots"
            screenshots.mkdir(parents=True)
            entries = []
            for kind, size in (("desktop", (20, 10)), ("mobile", (8, 16))):
                rel = f"screenshots/{kind}.png"
                Image.new("RGB", size).save(run / rel)
                entries.append({"path": rel, "kind": kind, "url": "http://test.invalid/",
                                "width": size[0], "height": size[1]})
            (screenshots / "manifest.json").write_text(json.dumps(entries))
            config = {"evidence": {"desktop": {"width": 20, "height": 10},
                                   "mobile": {"width": 8, "height": 16}}}
            self.assertEqual(2, len(validate_screenshots(Path(temp), config, run)))
            entries[0]["width"] = 21
            (screenshots / "manifest.json").write_text(json.dumps(entries))
            with self.assertRaisesRegex(PipelineError, "dimensions"):
                validate_screenshots(Path(temp), config, run)


if __name__ == "__main__":
    unittest.main()
