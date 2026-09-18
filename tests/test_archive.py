import json
import re
import unittest

from web_pipeline.common import PipelineError, hash_file, read_state, write_state
from web_pipeline.state import archive_task, create_task, policy_check, transition
from tests import test_lifecycle as lifecycle


class ArchiveTests(unittest.TestCase):
    def _fixture(self):
        fixture = lifecycle.LifecycleTests(methodName="test_executed_lifecycle_reaches_done_with_signed_review")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def _done_fixture(self):
        fixture = self._fixture()
        fixture.baseline_and_start()
        summary = fixture.full_and_review()
        fixture.sign_review(summary)
        fixture.transition_result = transition(fixture.root, fixture.task, "DONE", trust_path=fixture.trust)
        return fixture

    def test_signed_done_archives_and_new_active_task_is_independent(self):
        fixture = self._done_fixture()
        old_state_path = fixture.root / "Docs/Work" / fixture.task / "STATE.md"
        old_hash = hash_file(old_state_path)
        old_state = read_state(fixture.root, fixture.task)

        result = archive_task(fixture.root, fixture.task, trust_path=fixture.trust)
        target = fixture.root / result["path"]

        self.assertFalse((fixture.root / "Docs/Work" / fixture.task).exists())
        self.assertEqual("DONE", json.loads(
            next(iter(re.finditer(
                r"~~~json\s*(.*?)\s*~~~", (target / "STATE.md").read_text(), re.S
            ))).group(1))["status"])
        metadata = json.loads((target / "ARCHIVE.json").read_text())
        self.assertEqual(old_hash, metadata["state_sha256"])
        self.assertEqual(old_state["full_run"], metadata["runs"]["full"])
        self.assertTrue((fixture.root / fixture.config["project"]["report_root"] /
                         old_state["full_run"] / "summary.json").is_file())

        with self.assertRaisesRegex(PipelineError, "archived history"):
            create_task(fixture.root, fixture.task, "Confused replay", "T1", ["backend"], base_ref="HEAD")
        create_task(fixture.root, "TASK-NEW", "New active task", "T1", ["backend"], base_ref="HEAD")
        result = policy_check(fixture.root, kit=False, trust_path=fixture.trust)
        self.assertEqual("PASS", result["status"], result)

    def test_unapproved_or_not_done_archive_is_rejected_without_target(self):
        fixture = self._fixture()
        target = fixture.root / "Docs/Archive" / f"{fixture.task}-r1"
        with self.assertRaises(PipelineError):
            archive_task(fixture.root, fixture.task, trust_path=fixture.trust)
        self.assertFalse(target.exists())
        self.assertTrue((fixture.root / "Docs/Work" / fixture.task / "STATE.md").is_file())

        forged = read_state(fixture.root, fixture.task)
        forged.update(status="DONE", full_run="missing-run")
        write_state(fixture.root, forged)
        with self.assertRaisesRegex(PipelineError, "not currently valid"):
            archive_task(fixture.root, fixture.task, trust_path=fixture.trust)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
