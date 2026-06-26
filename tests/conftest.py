"""Shared pytest configuration: isolated XDG paths."""

import os
import shutil
import tempfile

import pytest

_kagan_test_root: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    """Redirect XDG/kagan paths to a temp tree before anything touches the real ones."""
    global _kagan_test_root
    _kagan_test_root = tempfile.mkdtemp(prefix="kagan-test-")
    os.environ["XDG_DATA_HOME"] = os.path.join(_kagan_test_root, "data")
    os.environ["XDG_STATE_HOME"] = os.path.join(_kagan_test_root, "state")
    os.environ["XDG_CONFIG_HOME"] = os.path.join(_kagan_test_root, "config")
    os.environ["KAGAN_WORKTREE_BASE"] = os.path.join(_kagan_test_root, "worktrees")
    # platformdirs ignores XDG_*_HOME on macOS, so pin the kagan dirs explicitly.
    os.environ["KAGAN_DATA_DIR"] = os.path.join(_kagan_test_root, "data")
    os.environ["KAGAN_CONFIG_DIR"] = os.path.join(_kagan_test_root, "config")


def pytest_unconfigure(config: pytest.Config) -> None:
    global _kagan_test_root
    if _kagan_test_root and os.path.isdir(_kagan_test_root):
        shutil.rmtree(_kagan_test_root, ignore_errors=True)
        _kagan_test_root = None
