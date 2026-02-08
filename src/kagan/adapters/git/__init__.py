"""Git adapter contracts."""

from kagan.adapters.git.operations import GitOperationsAdapter, GitOperationsProtocol
from kagan.adapters.git.worktrees import GitWorktreeAdapter, GitWorktreeProtocol

__all__ = [
    "GitOperationsAdapter",
    "GitOperationsProtocol",
    "GitWorktreeAdapter",
    "GitWorktreeProtocol",
]
