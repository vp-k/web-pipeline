"""Focused real-process integration tests for runner-only security boundaries."""
import base64
from datetime import datetime, timedelta, timezone
import json
import sys
import unittest

from web_pipeline.common import atomic_json, atomic_text, read_state, source_fingerprint, write_state
from web_pipeline.runner import run_profile, validate_run
from tests import test_lifecycle


class ExecutionIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Composition deliberately avoids inheriting LifecycleTests and duplicating
        # its test methods during discovery.
        self.fixture = test_lifecycle.LifecycleTests(methodName="test_unrun_baseline_blocks_ready")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def _sign(self, payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode()
        return base64.b64encode(self.fixture.key.sign(encoded)).decode()

    def test_real_signed_exception_runs_and_revalidates_as_not_applicable(self):
        trust = json.loads(self.fixture.trust.read_text())
        trust["identities"]["fixture-reviewer"]["roles"].append("Tech Owner")
        atomic_json(self.fixture.trust, trust)
        state = read_state(self.fixture.root, self.fixture.task)
        now = datetime.now(timezone.utc)
        payload = {
            "task_id": self.fixture.task, "revision": state["revision"],
            "fingerprint": state["fingerprint"], "phase": "exception",
            "role": "Tech Owner", "identity": "fixture-reviewer",
            "approved_utc": (now - timedelta(seconds=1)).isoformat(),
            "expires_utc": (now + timedelta(hours=1)).isoformat(),
            "outcome": "APPROVED", "scope": [], "conditions": [],
            "check_id": "unit", "reason": "Test-only signed fixture exception",
        }
        relative = f"Docs/Work/{self.fixture.task}/unit-exception.json"
        atomic_json(self.fixture.root / relative,
                    {"payload": payload, "signature": self._sign(payload)})
        state["exceptions"] = [relative]
        write_state(self.fixture.root, state)

        summary = run_profile(self.fixture.root, self.fixture.task, "Baseline",
                              trust_path=self.fixture.trust, run_id="exception-001")
        unit = next(check for check in summary["checks"] if check["id"] == "unit")
        self.assertEqual("PASS", summary["status"])
        self.assertEqual("NOT_APPLICABLE", unit["status"])
        validate_run(self.fixture.root, self.fixture.config,
                     read_state(self.fixture.root, self.fixture.task), summary["run_id"],
                     "Baseline", require_current=False, trust_path=self.fixture.trust)

    def test_successful_process_that_mutates_source_forces_failure(self):
        source = next(iter(self.fixture.config["sources"].values()))
        script = self.fixture.root / "mutate.py"
        atomic_text(script, "from pathlib import Path\nPath(%r).write_text('changed')\n" % source)
        for command in self.fixture.config["verification"]["commands"]:
            command["argv"] = [sys.executable, "mutate.py"]
        atomic_json(self.fixture.root / "pipeline.config.yaml", self.fixture.config)
        state = read_state(self.fixture.root, self.fixture.task)
        state["fingerprint"] = source_fingerprint(self.fixture.root, self.fixture.config, state)
        write_state(self.fixture.root, state)

        summary = run_profile(self.fixture.root, self.fixture.task, "Baseline",
                              run_id="mutation-001")
        self.assertEqual("FAIL", summary["status"])
        stability = next(check for check in summary["checks"] if check["id"] == "source-stability")
        self.assertEqual("FAIL", stability["status"])


if __name__ == "__main__":
    unittest.main()
