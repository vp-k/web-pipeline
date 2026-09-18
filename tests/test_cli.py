import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from web_pipeline import cli


class CliTests(unittest.TestCase):
    def test_transition_exposes_no_writable_pass_inputs(self):
        parser=cli._parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["transition","--task","X-1","--status","READY","--verification-status","PASS"])

    def test_csv_normalizes(self): self.assertEqual(["api","backend"],cli._csv(" api, backend, "))

    def test_init_preflights_all_conflicts_before_copy(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td); (target/"pipeline.config.yaml").write_text("mine",encoding="utf-8")
            with self.assertRaises(Exception): cli._init(Path(__file__).resolve().parents[1] / 'kit',target)
            self.assertEqual("mine",(target/"pipeline.config.yaml").read_text(encoding="utf-8"))
            self.assertFalse((target/"web_pipeline").exists())

    def test_init_copies_engine_and_leaves_project_not_ready(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"adopted"
            result=cli._init(Path(__file__).resolve().parents[1] / 'kit',target)
            config=json.loads((target/"pipeline.config.yaml").read_text(encoding="utf-8"))
            self.assertEqual("project",config["project"]["mode"])
            self.assertFalse(config["project"]["ready"])
            self.assertTrue((target/"web_pipeline/runner.py").is_file())
            self.assertTrue((target/"PIPELINE.md").is_file())
            self.assertTrue((target/".gitignore").is_file())
            self.assertTrue((target/"Reports/Pipeline/.gitkeep").is_file())
            self.assertGreater(result["files_copied"],10)

    def test_main_returns_nonzero_on_pipeline_error(self):
        with patch.object(cli,"dispatch",side_effect=cli.PipelineError("bad")):
            self.assertEqual(1,cli.main(["validate","--kit"]))

    def test_loop_stop_outcomes_return_nonzero(self):
        for status in ('WAITING', 'BUSY', 'PAUSED_LIMIT', 'FAIL'):
            with self.subTest(status=status), patch.object(cli, 'dispatch', return_value={'status': status}):
                self.assertEqual(1, cli.main(['loop', 'next']))
        for status in ('ACTION_REQUIRED', 'CONTINUE', 'COMPLETE'):
            with self.subTest(status=status), patch.object(cli, 'dispatch', return_value={'status': status}):
                self.assertEqual(0, cli.main(['loop', 'next']))

if __name__ == "__main__": unittest.main()
