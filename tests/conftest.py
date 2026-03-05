"""Shared fixtures for acceptance tests.

pytest_configure runs before collection/imports, so XDG env overrides are in
place before ``kagan.core.__init__`` calls ``configure_logging()``.
"""

import os
import shutil
import tempfile

import pytest

# Temp root created once per worker process (xdist-safe).
_kagan_test_root: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    """Redirect every XDG / kagan path to a disposable temp tree.

    This fires before *any* test module is imported, which means
    ``kagan.core.__init__`` → ``configure_logging()`` already sees the
    overridden ``XDG_STATE_HOME`` and writes the log file into our temp dir
    instead of the real ``~/.local/state/kagan/``.
    """
    global _kagan_test_root
    _kagan_test_root = tempfile.mkdtemp(prefix="kagan-test-")

    os.environ["XDG_DATA_HOME"] = os.path.join(_kagan_test_root, "data")
    os.environ["XDG_STATE_HOME"] = os.path.join(_kagan_test_root, "state")
    os.environ["XDG_CONFIG_HOME"] = os.path.join(_kagan_test_root, "config")
    os.environ["KAGAN_WORKTREE_BASE"] = os.path.join(_kagan_test_root, "worktrees")
    # Set KAGAN_DATA_DIR and KAGAN_CONFIG_DIR to ensure tests use temp dir
    # (especially on macOS where platformdirs doesn't respect XDG_*_HOME)
    os.environ["KAGAN_DATA_DIR"] = os.path.join(_kagan_test_root, "data")
    os.environ["KAGAN_CONFIG_DIR"] = os.path.join(_kagan_test_root, "config")


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove the disposable temp tree created in ``pytest_configure``."""
    global _kagan_test_root
    if _kagan_test_root and os.path.isdir(_kagan_test_root):
        shutil.rmtree(_kagan_test_root, ignore_errors=True)
        _kagan_test_root = None


# Re-export canonical fixtures so every test file can use ``board`` and ``git_board``
# without a local fixture definition.
from tests.helpers.fixtures import board, git_board  # noqa: E402

__all__ = ["board", "git_board"]
