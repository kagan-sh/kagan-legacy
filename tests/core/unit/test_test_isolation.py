from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from kagan.core.test_isolation import (
    STRICT_TEST_ISOLATION_ENV,
    enforce_test_db_path,
    enforce_test_runtime_dir,
    strict_test_isolation_enabled,
)


def test_strict_test_isolation_disabled_allows_non_temp_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(STRICT_TEST_ISOLATION_ENV, raising=False)
    assert strict_test_isolation_enabled() is False
    enforce_test_db_path(Path.home() / ".local" / "share" / "kagan" / "kagan.db")


def test_strict_test_isolation_rejects_non_temp_db_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STRICT_TEST_ISOLATION_ENV, "1")
    with pytest.raises(RuntimeError, match="Database path escaped strict test sandbox"):
        enforce_test_db_path(Path.home() / ".local" / "share" / "kagan" / "kagan.db")


def test_strict_test_isolation_allows_temp_db_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STRICT_TEST_ISOLATION_ENV, "1")
    safe_path = Path(tempfile.gettempdir()) / "kagan-tests" / "safe.db"
    enforce_test_db_path(safe_path)


def test_strict_test_isolation_allows_memory_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STRICT_TEST_ISOLATION_ENV, "1")
    enforce_test_db_path(":memory:")


def test_strict_test_isolation_rejects_non_temp_runtime_dirs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STRICT_TEST_ISOLATION_ENV, "1")
    error_pattern = "Core runtime directory path escaped strict test sandbox"
    with pytest.raises(RuntimeError, match=error_pattern):
        enforce_test_runtime_dir(Path.home() / ".local" / "share" / "kagan" / "core")


def test_strict_test_isolation_allows_tmp_runtime_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STRICT_TEST_ISOLATION_ENV, "1")
    if os.name == "nt":
        pytest.skip("/tmp runtime path is not used on Windows")
    enforce_test_runtime_dir(Path("/tmp") / "kagan-core" / "safe-runtime")
