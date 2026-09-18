import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from web_pipeline.common import atomic_json, atomic_text, load_config, read_state
from web_pipeline.runner import run_profile
from web_pipeline.state import create_task, prepare_task, transition

ROOT = Path(__file__).resolve().parents[1] / 'kit'


class BaselineRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="baseline-regression-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        config = copy.deepcopy(load_config(ROOT, kit=True))
        config["project"].update(mode="project", ready=True, supported_domains=["backend"])
        atomic_text(self.root / "pass.py", "print('policy pass')\n")
        atomic_text(self.root / "check.py", "print('known baseline regression')\nraise SystemExit(7)\n")
        policy_ids = set(config["verification"]["policy_checks"])
        for command in config["verification"]["commands"]:
            script = "pass.py" if command["id"] in policy_ids else "check.py"
            command.update(enabled=True, argv=[sys.executable, script], artifacts=[])
        for relative in config["sources"].values():
            atomic_text(self.root / relative, "test source\n")
        atomic_json(self.root / "pipeline.config.yaml", config)
        self.config = config
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "TEST ONLY")
        self._git("config", "core.autocrlf", "false")
        self._git("add", ".")
        self._git("commit", "-qm", "baseline fixture")
        create_task(self.root, "TASK-BASE", "Fix regression", "T1", ["backend"], base_ref="HEAD")
        task = self.root / "Docs/Work/TASK-BASE"
        atomic_text(task / "BRIEF.md", "# Fix regression\n\nRepair the known checker failure.\n")
        atomic_text(task / "DOR.md", "# Ready\n\nCapture the failing Baseline before repair.\n")
        atomic_json(task / "ACCEPTANCE.json", {"criteria": [{"id": "AC-1", "description": "Unit passes",
                                                               "checks": ["unit"]}]})
        from tests.planning_fixture import record_fixture_planning
        record_fixture_planning(self.root, 'TASK-BASE')
        prepare_task(self.root, "TASK-BASE", "test-implementer")

    def _git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_real_failing_baseline_is_captured_then_fix_can_pass_full(self):
        baseline = run_profile(self.root, "TASK-BASE", "Baseline", run_id="baseline-failing")
        self.assertEqual("FAIL", baseline["status"])
        failures = [c for c in baseline["checks"] if c["status"] == "FAIL"]
        self.assertTrue(failures)
        self.assertTrue(all(isinstance(c["exit_code"], int) and c["exit_code"] != 0 and c["log"] for c in failures))
        self.assertEqual("baseline-failing", read_state(self.root, "TASK-BASE")["baseline_run"])
        transition(self.root, "TASK-BASE", "READY")
        transition(self.root, "TASK-BASE", "IN_PROGRESS")
        atomic_text(self.root / "check.py", "print('fixed')\n")
        full = run_profile(self.root, "TASK-BASE", "Full", run_id="full-fixed")
        self.assertEqual("PASS", full["status"])

    def test_policy_failure_and_disabled_check_do_not_capture_baseline(self):
        policy_id = self.config["verification"]["policy_checks"][0]
        config = load_config(self.root)
        for command in config["verification"]["commands"]:
            if command["id"] == policy_id:
                command["argv"] = [sys.executable, "check.py"]
        atomic_json(self.root / "pipeline.config.yaml", config)
        # Configuration is fingerprinted, so explicitly reseal the still-DRAFT task.
        prepare_task_state = read_state(self.root, "TASK-BASE")
        prepare_task_state["fingerprint"] = None
        from web_pipeline.common import source_fingerprint, write_state
        prepare_task_state["fingerprint"] = source_fingerprint(self.root, config, prepare_task_state)
        write_state(self.root, prepare_task_state)
        summary = run_profile(self.root, "TASK-BASE", "Baseline", run_id="baseline-policy-fail")
        self.assertEqual("FAIL", summary["status"])
        self.assertIsNone(read_state(self.root, "TASK-BASE")["baseline_run"])

        # A missing required execution is likewise not captured.
        for command in config["verification"]["commands"]:
            if command["id"] == policy_id:
                command["argv"] = [sys.executable, "pass.py"]
            if command["id"] == "unit":
                command["enabled"] = False
        config["project"]["ready"] = False
        atomic_json(self.root / "pipeline.config.yaml", config)
        # Strict project loading correctly blocks before any run is created.
        with self.assertRaises(Exception):
            run_profile(self.root, "TASK-BASE", "Baseline", run_id="baseline-disabled")


if __name__ == "__main__":
    unittest.main()
