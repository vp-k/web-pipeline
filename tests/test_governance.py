import base64
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from web_pipeline.approval import validate_approvals
from web_pipeline.common import PipelineError, atomic_json, hash_file, load_config, source_fingerprint, write_state
from web_pipeline.state import create_task, policy_check, revise_task
from web_pipeline.policy import classify


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        source = Path(__file__).resolve().parents[1] / 'kit'
        shutil.copy2(source / "pipeline.config.yaml", self.root / "pipeline.config.yaml")
        config = json.loads((self.root / "pipeline.config.yaml").read_text(encoding="utf-8"))
        if config.get("schema_version") != "2.0":
            self.skipTest("v2 config is being installed by the primary implementation")
        config["project"]["mode"] = "kit"
        config["project"]["ready"] = False
        for rel in config["sources"].values():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test source\n", encoding="utf-8")
        atomic_json(self.root / "pipeline.config.yaml", config)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "TEST ONLY"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "test baseline"], cwd=self.root, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def _key_and_trust(self, identity="human-reviewer", roles=("Reviewer",)):
        key = Ed25519PrivateKey.generate()  # TEST ONLY ephemeral key
        raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        trust = Path(self.temp.name) / "trust.json"
        atomic_json(trust, {"identities": {identity: {"type": "human", "roles": list(roles),
                                                       "public_key": base64.b64encode(raw).decode()}}})
        return key, trust

    def _signed(self, key, payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return {"payload": payload, "signature": base64.b64encode(key.sign(encoded)).decode()}

    def test_create_is_schema_backed_and_destructive_migration_promotes(self):
        state = create_task(self.root, "TASK-01", "Migration", "T0", ["database"],
                            migration_class="destructive")
        self.assertEqual("T4", state["risk_tier"])
        self.assertIn("database_schema", state["protected_changes"])
        self.assertIn("destructive_migration", state["protected_changes"])
        self.assertEqual("DRAFT", state["status"])

    def test_all_task_policy_scan_does_not_stop_at_first_task(self):
        create_task(self.root, "TASK-01", "One", "T0", ["frontend"])
        create_task(self.root, "TASK-02", "Two", "T0", ["frontend"])
        (self.root / "Docs/Work/TASK-02/STATE.md").write_text("corrupt", encoding="utf-8")
        result = policy_check(self.root, kit=True)
        self.assertEqual("FAIL", result["status"])
        self.assertTrue(any("TASK-02" in error for error in result["errors"]))

    def test_external_ed25519_signature_role_and_revision_are_enforced(self):
        state = create_task(self.root, "TASK-01", "Review", "T1", ["backend"])
        config = load_config(self.root, kit=True)
        state["implementer"] = "implementer"
        state["fingerprint"] = source_fingerprint(self.root, config, state)
        key, trust = self._key_and_trust()
        summary_path = self.root / config["project"]["report_root"] / "run-01" / "summary.json"
        atomic_json(summary_path, {"test": True})
        now = datetime.now(timezone.utc)
        payload = {"task_id": state["task_id"], "revision": state["revision"],
                   "fingerprint": state["fingerprint"], "phase": "review", "role": "Reviewer",
                   "identity": "human-reviewer", "approved_utc": (now-timedelta(minutes=1)).isoformat(),
                   "expires_utc": (now+timedelta(hours=1)).isoformat(), "outcome": "APPROVED", "scope": [],
                   "tree_digest": "a"*64, "run_id": "run-01", "conditions": []}
        payload["run_digest"] = hash_file(summary_path)
        approval_path = self.root / "Docs/Work/TASK-01/review.json"
        atomic_json(approval_path, self._signed(key, payload))
        state["approvals"] = ["Docs/Work/TASK-01/review.json"]
        validate_approvals(self.root, config, state, ["Reviewer"], "review", trust,
                           {"tree_digest": "a"*64}, "run-01")
        payload["revision"] += 1
        atomic_json(approval_path, self._signed(key, payload))
        with self.assertRaisesRegex(PipelineError, "stale|missing valid"):
            validate_approvals(self.root, config, state, ["Reviewer"], "review", trust,
                               {"tree_digest": "a"*64}, "run-01")

    def test_trust_inside_repository_and_self_review_are_rejected(self):
        state = create_task(self.root, "TASK-01", "Review", "T1", ["backend"])
        config = load_config(self.root, kit=True)
        state["implementer"] = "same-person"
        state["fingerprint"] = source_fingerprint(self.root, config, state)
        key, external = self._key_and_trust("same-person")
        summary_path = self.root / config["project"]["report_root"] / "run-01" / "summary.json"
        atomic_json(summary_path, {"test": True})
        inside = self.root / "trust.json"
        shutil.copy2(external, inside)
        now = datetime.now(timezone.utc)
        payload = {"task_id": state["task_id"], "revision": 1, "fingerprint": state["fingerprint"],
                   "phase": "review", "role": "Reviewer", "identity": "same-person",
                   "approved_utc": (now-timedelta(minutes=1)).isoformat(),
                   "expires_utc": (now+timedelta(hours=1)).isoformat(), "outcome": "APPROVED", "scope": [],
                   "tree_digest": "b"*64, "run_id": "run-01", "conditions": []}
        payload["run_digest"] = hash_file(summary_path)
        rel = "Docs/Work/TASK-01/review.json"
        atomic_json(self.root / rel, self._signed(key, payload))
        state["approvals"] = [rel]
        # Standard only needs trust when an actual signed candidate is present.
        # Exercise the original trust-path boundary with that signed record.
        with self.assertRaisesRegex(PipelineError, "outside"):
            validate_approvals(self.root, config, state, ["Reviewer"], "review", inside,
                               {"tree_digest": "b"*64}, "run-01")
        with self.assertRaisesRegex(PipelineError, "independent"):
            validate_approvals(self.root, config, state, ["Reviewer"], "review", external,
                               {"tree_digest": "b"*64}, "run-01")

    def test_revision_invalidates_runs_approvals_and_fingerprint(self):
        state = create_task(self.root, "TASK-01", "Revise", "T1", ["backend"])
        state.update({"fingerprint": "a"*64, "approvals": ["a.json"], "exceptions": ["e.json"],
                      "baseline_run": "base-1", "full_run": "full-1", "release_run": "rel-1"})
        write_state(self.root, state)
        revised = revise_task(self.root, "TASK-01", "scope changed")
        self.assertEqual(2, revised["revision"])
        self.assertEqual("DRAFT", revised["status"])
        self.assertIsNone(revised["fingerprint"])
        self.assertEqual([], revised["approvals"])
        self.assertEqual([], revised["exceptions"])
        self.assertIsNone(revised["full_run"])

    def test_diff_promotion_includes_untracked_and_deleted_paths(self):
        tracked = self.root / "old_payment.py"
        tracked.write_text("value = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "old_payment.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "tracked payment file"], cwd=self.root, check=True)
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True,
                              text=True, capture_output=True).stdout.strip()
        tracked.unlink()
        (self.root / "new_auth.py").write_text("# untracked auth change\n", encoding="utf-8")
        state = create_task(self.root, "TASK-01", "Diff", "T0", ["frontend"], base_ref=base)
        result = classify(self.root, load_config(self.root, kit=True), state)
        self.assertIn("old_payment.py", result["changed_paths"])
        self.assertIn("new_auth.py", result["changed_paths"])
        self.assertEqual("T4", result["risk_tier"])
        self.assertIn("payment", result["protected_changes"])
        self.assertIn("authentication", result["protected_changes"])

    def test_invalid_creation_does_not_leave_orphan_task_directory(self):
        with self.assertRaises(PipelineError):
            create_task(self.root,'BAD-01','Invalid scope','T1',['not-a-domain'])
        self.assertFalse((self.root / 'Docs/Work/BAD-01').exists())

    def test_one_signing_key_cannot_alias_multiple_human_identities(self):
        from web_pipeline.approval import _trust
        _, trust = self._key_and_trust()
        data = json.loads(trust.read_text())
        data['identities']['second-alias'] = dict(data['identities']['human-reviewer'])
        atomic_json(trust,data)
        with self.assertRaisesRegex(PipelineError,'distinct'):
            _trust(self.root,trust)


if __name__ == "__main__":
    unittest.main()
