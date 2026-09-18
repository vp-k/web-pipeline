"""Real, ephemeral T4 Release-readiness lifecycle tests."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from web_pipeline.common import (PipelineError, atomic_json, atomic_text, hash_file,
                                 load_config, read_state, write_state)
from web_pipeline.runner import run_profile
from web_pipeline.state import create_task, policy_check, prepare_task, transition

ROOT = Path(__file__).resolve().parents[1] / 'kit'


class ReleaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="web-pipeline-release-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.config = copy.deepcopy(load_config(ROOT, kit=True))
        self.config["project"].update(mode="project", ready=True,
                                      supported_domains=["payment"])
        atomic_text(self.root / "check.py", "assert 3 * 7 == 21\nprint('T4 fixture check passed')\n")
        for command in self.config["verification"]["commands"]:
            command.update(enabled=True, argv=[sys.executable, "check.py"], artifacts=[])
        for path in self.config["sources"].values():
            atomic_text(self.root / path, "T4 fixture source revision one.\n")
        atomic_json(self.root / "pipeline.config.yaml", self.config)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "release@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "TEST ONLY"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "T4 fixture baseline"], cwd=self.root, check=True)

        self.task = "PAY-001"
        create_task(self.root, self.task, "Payment readiness fixture", "T4", ["payment"],
                    protected_changes=["payment"], base_ref="HEAD")
        task_dir = self.root / "Docs" / "Work" / self.task
        for name in ("BRIEF.md", "DOR.md", "PLAN.md", "EXEC_PLAN.md", "RELEASE.md"):
            atomic_text(task_dir / name, f"# {name}\n\nTest-only T4 scope, recovery, and readiness evidence.\n")
        atomic_json(task_dir / "ACCEPTANCE.json", {"criteria": [{
            "id": "AC-1", "description": "All payment readiness checks execute",
            "checks": ["payment-tests"]}]})
        adr_rel = f"Docs/Work/{self.task}/ADR-PAYMENT.json"
        atomic_json(self.root / adr_rel, {
            "id": "ADR-PAYMENT", "title": "Test-only payment decision", "status": "ACCEPTED",
            "task_id": self.task, "revision": 1, "scope": ["payment"],
            "context": "Ephemeral lifecycle fixture", "decision": "Exercise readiness only",
            "risks": "No production system exists", "recovery": "Discard the temporary directory"})
        state = read_state(self.root, self.task)
        state["decision_records"] = [adr_rel]
        write_state(self.root, state)
        from tests.planning_fixture import record_fixture_planning
        record_fixture_planning(self.root, self.task)
        prepare_task(self.root, self.task, "fixture-implementer")

        self.keys = {name: Ed25519PrivateKey.generate() for name in
                     ("payment-owner", "tech-owner", "reviewer", "release-owner")}
        roles = {"payment-owner": ["Payment Owner"], "tech-owner": ["Tech Owner"],
                 "reviewer": ["Reviewer"], "release-owner": ["Release Owner"]}
        identities = {}
        for name, key in self.keys.items():
            public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            identities[name] = {"type": "human", "roles": roles[name],
                                "public_key": base64.b64encode(public).decode()}
        self.trust = Path(self.temp.name) / "trust.json"
        atomic_json(self.trust, {"identities": identities})

    def _approval(self, phase, role, identity, *, run=None):
        state = read_state(self.root, self.task)
        now = datetime.now(timezone.utc)
        payload = {"task_id": self.task, "revision": state["revision"],
                   "fingerprint": state["fingerprint"], "phase": phase, "role": role,
                   "identity": identity, "approved_utc": (now-timedelta(seconds=1)).isoformat(),
                   "expires_utc": (now+timedelta(hours=1)).isoformat(), "outcome": "APPROVED",
                   "scope": ["payment"], "conditions": []}
        if run:
            summary = self.root / self.config["project"]["report_root"] / run["run_id"] / "summary.json"
            payload.update(tree_digest=run["snapshot"]["tree_digest"], run_id=run["run_id"],
                           run_digest=hash_file(summary))
        message = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        record = {"payload": payload,
                  "signature": base64.b64encode(self.keys[identity].sign(message)).decode()}
        rel = f"Docs/Work/{self.task}/{phase}-{role.replace(' ', '-').lower()}.json"
        atomic_json(self.root / rel, record)
        return rel

    def test_t4_release_requires_all_signers_then_reaches_ready(self):
        self.release_lifecycle()

    def test_development_does_not_require_release_only_setup_but_release_still_fails(self):
        command = copy.deepcopy(self.config['verification']['commands'][0])
        command.update(id='release-only-fixture', profiles=['Release'], enabled=False, argv=[])
        self.config['verification']['commands'].append(command)
        self.config['verification']['requirements']['payment']['Release'].append('release-only-fixture')
        atomic_json(self.root / 'pipeline.config.yaml', self.config)
        # This is the pre-existing configuration under test, not an infrastructure
        # change made by the payment task (whose base_ref is HEAD).
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'release-only setup fixture'], cwd=self.root, check=True)
        prepare_task(self.root, self.task, 'fixture-implementer')
        self.release_lifecycle(missing_release_check=True)

    def release_lifecycle(self, missing_release_check=False):
        design = [self._approval("design", "Payment Owner", "payment-owner"),
                  self._approval("design", "Tech Owner", "tech-owner")]
        state = read_state(self.root, self.task)
        state["approvals"] = design
        write_state(self.root, state)
        baseline = run_profile(self.root, self.task, "Baseline", trust_path=self.trust,
                               run_id="pay-baseline-001")
        self.assertEqual("PASS", baseline["status"])
        transition(self.root, self.task, "READY", self.trust)
        transition(self.root, self.task, "IN_PROGRESS", self.trust)
        full = run_profile(self.root, self.task, "Full", trust_path=self.trust,
                           run_id="pay-full-001")
        self.assertEqual("PASS", full["status"])
        transition(self.root, self.task, "VERIFYING", self.trust)
        transition(self.root, self.task, "REVIEW", self.trust)
        review = self._approval("review", "Reviewer", "reviewer", run=full)
        state = read_state(self.root, self.task)
        state["approvals"] = design + [review]
        write_state(self.root, state)
        transition(self.root, self.task, "DONE", self.trust)

        report_root = self.root / self.config["project"]["report_root"]
        before = set(report_root.iterdir())
        with self.assertRaises(PipelineError):
            run_profile(self.root, self.task, "Release", trust_path=self.trust,
                        run_id="pay-release-none")
        self.assertEqual(before, set(report_root.iterdir()))

        release_owner = self._approval("release", "Release Owner", "release-owner", run=full)
        state = read_state(self.root, self.task)
        state["approvals"] = design + [review, release_owner]
        write_state(self.root, state)
        with self.assertRaises(PipelineError):
            run_profile(self.root, self.task, "Release", trust_path=self.trust,
                        run_id="pay-release-single")
        self.assertFalse((report_root / "pay-release-single").exists())

        payment = self._approval("release", "Payment Owner", "payment-owner", run=full)
        tech = self._approval("release", "Tech Owner", "tech-owner", run=full)
        state = read_state(self.root, self.task)
        state["approvals"] = design + [review, release_owner, payment, tech]
        write_state(self.root, state)
        release = run_profile(self.root, self.task, "Release", trust_path=self.trust,
                              run_id="pay-release-001")
        if missing_release_check:
            self.assertNotEqual('PASS', release['status'])
            check = next(c for c in release['checks'] if c['id'] == 'release-only-fixture')
            self.assertEqual('NOT_RUN', check['status'])
            state = read_state(self.root, self.task)
            self.assertEqual('DONE', state['status'])
            self.assertEqual('NOT_READY', state['release_status'])
            self.assertIsNone(state['release_run'])
            return
        self.assertEqual("PASS", release["status"])
        self.assertEqual("READY", read_state(self.root, self.task)["release_status"])
        policy = policy_check(self.root, task_id=self.task, trust_path=self.trust)
        self.assertEqual("PASS", policy["status"], policy)


if __name__ == "__main__":
    unittest.main()
