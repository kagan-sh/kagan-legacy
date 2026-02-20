"""Autouse safety fixtures for isolated test storage and production-path guards."""

from __future__ import annotations

import shutil
import sqlite3
from typing import TYPE_CHECKING, Any, cast

import pytest

from tests.helpers.fixtures.isolation import (
    REAL_PRODUCTION_DB_PATH,
    TEST_BASE_DIR,
    TEST_ENV,
    coerce_db_path,
    is_production_db_path,
    is_safe_test_db_path,
    is_within_test_base,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from os import PathLike
    from pathlib import Path

    from sqlalchemy import URL


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_base_dir() -> Generator[None, None, None]:
    """Remove the shared test path override directory after the session."""
    yield
    shutil.rmtree(TEST_BASE_DIR, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _assert_default_paths_are_isolated() -> None:
    """Verify default Kagan storage paths resolve inside the test base directory."""
    from kagan.core.paths import (
        get_cache_dir,
        get_config_dir,
        get_data_dir,
        get_database_path,
    )

    default_paths = (
        get_data_dir(),
        get_config_dir(),
        get_cache_dir(),
        get_database_path(),
    )
    for path in default_paths:
        if not is_within_test_base(path):
            raise AssertionError(f"Default test path escaped isolated storage root: {path}")


@pytest.fixture(autouse=True)
def _enforce_isolated_storage_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force all Kagan/XDG paths to stay in an isolated test directory."""
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def _block_production_kagan_db_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast if any test tries to touch a real installed Kagan database.

    Guards every layer that can open a SQLite file:
    1. ``sqlalchemy.ext.asyncio.create_async_engine`` (via the engine module)
    2. ``sqlite3.connect``
    3. ``kagan.core.paths.get_database_path`` (resolves the default DB location)
    4. ``kagan.core.adapters.db.engine.create_db_engine`` (top-level Kagan helper)

    A path is rejected if it is not `:memory:` AND does not reside inside
    the test temp tree (``TEST_BASE_DIR`` or the system tempdir used by
    ``tmp_path``).  This is strictly broader than checking against the single
    production path — any accidental escape is caught.
    """
    from kagan.core import constants as core_constants
    from kagan.core import host as host_mod
    from kagan.core import paths as core_paths
    from kagan.core.adapters.db import engine as db_engine
    from kagan.core.adapters.db.repositories import task as task_repo_mod
    from kagan.core.services import runtime as runtime_mod

    original_create_async_engine = db_engine.create_async_engine
    original_sqlite_connect = sqlite3.connect
    original_get_database_path = core_paths.get_database_path
    original_kagan_create_db_engine = db_engine.create_db_engine

    def _assert_safe_db_path(database: object, *, context: str = "") -> None:
        """Reject any DB path that escapes the test sandbox."""
        db_path = coerce_db_path(database)
        if db_path is None:
            # :memory: or unparseable — safe
            return
        if is_production_db_path(db_path):
            raise AssertionError(
                f"Tests must not access production Kagan DB: {REAL_PRODUCTION_DB_PATH}"
                + (f" (via {context})" if context else "")
            )
        if not is_safe_test_db_path(db_path):
            raise AssertionError(
                f"Tests must not access DB paths outside the test sandbox: {db_path}"
                + (f" (via {context})" if context else "")
            )

    # --- Layer 1: SQLAlchemy create_async_engine ---
    def _guarded_create_async_engine(url: URL | str, *args: object, **kwargs: object):
        _assert_safe_db_path(url, context="create_async_engine")
        create_engine = cast("Any", original_create_async_engine)
        return create_engine(url, *args, **kwargs)

    # --- Layer 2: stdlib sqlite3.connect ---
    def _guarded_sqlite_connect(
        database: str | bytes | PathLike[str] | PathLike[bytes],
        *args: object,
        **kwargs: object,
    ):
        _assert_safe_db_path(database, context="sqlite3.connect")
        connect = cast("Any", original_sqlite_connect)
        return connect(database, *args, **kwargs)

    # --- Layer 3: Kagan's get_database_path ---
    def _guarded_get_database_path() -> Path:
        result = original_get_database_path()
        if not is_safe_test_db_path(result):
            raise AssertionError(
                f"get_database_path() resolved outside the test sandbox: {result}. "
                f"Ensure KAGAN_DATA_DIR is set to the test temp directory."
            )
        return result

    # --- Layer 4: Kagan's create_db_engine wrapper ---
    async def _guarded_kagan_create_db_engine(
        db_path: str | Path | None = None,
    ) -> Any:
        if db_path is not None:
            _assert_safe_db_path(db_path, context="kagan.create_db_engine")
        create_engine = cast("Any", original_kagan_create_db_engine)
        return await create_engine(db_path)

    monkeypatch.setattr(db_engine, "create_async_engine", _guarded_create_async_engine)
    monkeypatch.setattr(sqlite3, "connect", _guarded_sqlite_connect)
    monkeypatch.setattr(core_paths, "get_database_path", _guarded_get_database_path)
    monkeypatch.setattr(db_engine, "create_db_engine", _guarded_kagan_create_db_engine)
    # Patch get_database_path at every import site so callers that bound the name
    # at import time (``from kagan.core.paths import get_database_path``) also
    # pick up the guard.
    monkeypatch.setattr(db_engine, "get_database_path", _guarded_get_database_path)
    monkeypatch.setattr(task_repo_mod, "get_database_path", _guarded_get_database_path)
    monkeypatch.setattr(core_constants, "get_database_path", _guarded_get_database_path)
    monkeypatch.setattr(runtime_mod, "get_database_path", _guarded_get_database_path)
    monkeypatch.setattr(host_mod, "get_database_path", _guarded_get_database_path)
    # MCP server also imports get_database_path; patch if available.
    try:
        from kagan.mcp import server as mcp_server_mod

        monkeypatch.setattr(mcp_server_mod, "get_database_path", _guarded_get_database_path)
    except Exception:  # quality-allow-broad-except: optional resilience boundary
        pass


@pytest.fixture(autouse=True)
def _mock_platform_system(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Handle @pytest.mark.mock_platform_system("Windows") marker."""
    marker = request.node.get_closest_marker("mock_platform_system")
    if marker:
        target_platform = marker.args[0]
        monkeypatch.setattr("platform.system", lambda: target_platform)
        monkeypatch.setattr(
            "kagan.core.command_utils.is_windows", lambda: target_platform == "Windows"
        )


@pytest.fixture(autouse=True)
def _clean_worktree_base() -> Generator[None, None, None]:
    """Ensure worktree temp directories don't leak between tests."""
    from kagan.core.paths import get_worktree_base_dir

    yield
    shutil.rmtree(get_worktree_base_dir(), ignore_errors=True)
