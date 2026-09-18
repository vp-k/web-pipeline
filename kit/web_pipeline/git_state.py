"""Read-only integration checks for the shared checkout, including worktrees."""
from pathlib import Path
import subprocess

from .common import PipelineError


def require_settled_checkout(root):
    def git(*args):
        try:
            result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                                    text=True, encoding='utf-8', timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PipelineError('Cannot inspect Git integration state; resolve before continuing') from exc
        if result.returncode:
            raise PipelineError('Cannot inspect Git integration state: ' + result.stderr.strip())
        return result.stdout.strip()

    # .git may be a pointer file; operation state belongs to this worktree's gitdir.
    git_dir = Path(git('rev-parse', '--absolute-git-dir'))
    pending = [name for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD',
                                'rebase-merge', 'rebase-apply', 'sequencer')
               if (git_dir / name).exists()]
    # A pipeline root may be a subdirectory. Include sibling conflicts too,
    # especially squash/stash conflicts that do not leave MERGE_HEAD behind.
    if git('ls-files', '--unmerged', '-z', '--', ':(top)**'):
        pending.append('unmerged index entries')
    if pending:
        raise PipelineError('Unfinished Git integration: ' + ', '.join(pending)
                            + '. Resolve and finish or explicitly abort the operation before continuing; '
                              'do not start another task or discard changes to bypass it.')
