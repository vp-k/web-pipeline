"""Real Git conflicts and worktree-local operation markers; no user checkout mutation."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from web_pipeline.common import PipelineError
from web_pipeline.git_state import require_settled_checkout


class GitStateTests(unittest.TestCase):
    def setUp(self):
        sandbox = tempfile.TemporaryDirectory(prefix='pipeline-git-state-')
        self.addCleanup(sandbox.cleanup)
        self.root = Path(sandbox.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'TEST ONLY')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('base')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')

    def git(self, *args, root=None, check=True):
        return subprocess.run(['git', '-C', str(root or self.root), *args], check=check,
                              capture_output=True, text=True)

    def write(self, text, root=None):
        ((root or self.root) / 'value.txt').write_text(text + '\n', encoding='utf-8')

    def conflict(self, root):
        self.git('checkout', '-qb', 'incoming', root=root)
        self.write('incoming', root)
        self.git('commit', '-qam', 'incoming', root=root)
        self.git('checkout', '-qb', 'current', 'HEAD~1', root=root)
        self.write('current', root)
        self.git('commit', '-qam', 'current', root=root)
        self.assertNotEqual(0, self.git('merge', 'incoming', root=root, check=False).returncode)

    def test_real_merge_conflict_and_staged_resolution_remain_blocked_until_finished(self):
        self.conflict(self.root)
        with self.assertRaisesRegex(PipelineError, 'unmerged index'):
            require_settled_checkout(self.root)
        self.write('resolved')
        self.git('add', 'value.txt')
        with self.assertRaisesRegex(PipelineError, 'MERGE_HEAD'):
            require_settled_checkout(self.root)
        self.git('commit', '-qm', 'resolved merge')
        require_settled_checkout(self.root)

    def test_worktree_conflict_is_detected_without_blocking_the_unaffected_checkout(self):
        worktree = self.root.parent / 'linked'
        self.git('worktree', 'add', '-qb', 'linked', str(worktree))
        self.assertTrue((worktree / '.git').is_file())
        self.conflict(worktree)
        with self.assertRaisesRegex(PipelineError, 'Unfinished Git integration'):
            require_settled_checkout(worktree)
        require_settled_checkout(self.root)
        self.git('merge', '--abort', root=worktree)
        require_settled_checkout(worktree)

    def test_subproject_detects_squash_conflict_outside_its_directory(self):
        worktree = self.root.parent / 'squash-linked'
        self.git('worktree', 'add', '-qb', 'squash-linked', str(worktree))
        self.conflict(worktree)
        self.git('merge', '--abort', root=worktree)
        self.assertNotEqual(0, self.git('merge', '--squash', 'incoming', root=worktree, check=False).returncode)
        subproject = worktree / 'app'
        subproject.mkdir()
        gitdir = Path(self.git('rev-parse', '--absolute-git-dir', root=worktree).stdout.strip())
        self.assertFalse((gitdir / 'MERGE_HEAD').exists())
        self.assertTrue(self.git('ls-files', '--unmerged', '-z', root=worktree).stdout)
        with self.assertRaisesRegex(PipelineError, 'unmerged index'):
            require_settled_checkout(subproject)
        require_settled_checkout(self.root)
        self.write('resolved', worktree)
        self.git('add', 'value.txt', root=worktree)
        self.git('commit', '-qm', 'resolved squash', root=worktree)
        require_settled_checkout(subproject)

    def test_other_operation_markers_and_git_inspection_failure_fail_closed(self):
        gitdir = Path(self.git('rev-parse', '--absolute-git-dir').stdout.strip())
        for name in ('CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'sequencer'):
            with self.subTest(marker=name):
                marker = gitdir / name
                marker.mkdir()
                with self.assertRaisesRegex(PipelineError, name):
                    require_settled_checkout(self.root)
                marker.rmdir()
        with self.assertRaisesRegex(PipelineError, 'Cannot inspect Git'):
            require_settled_checkout(self.root.parent / 'missing')
