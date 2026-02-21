"""Shared isolated storage setup used by pytest bootstrap and safety fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from platformdirs import user_data_dir

REAL_PRODUCTION_DB_PATH = (Path(user_data_dir("kagan")) / "kagan.db").expanduser().resolve()

TEST_BASE_DIR = Path(tempfile.mkdtemp(prefix="kagan-tests-"))
_TEST_BASE_DIR_RESOLVED = TEST_BASE_DIR.resolve()
TEST_ENV = {
    "KAGAN_STRICT_TEST_ISOLATION": "1",
    "KAGAN_DATA_DIR": str(TEST_BASE_DIR / "data"),
    "KAGAN_CONFIG_DIR": str(TEST_BASE_DIR / "config"),
    "KAGAN_CACHE_DIR": str(TEST_BASE_DIR / "cache"),
    "KAGAN_WORKTREE_BASE": str(TEST_BASE_DIR / "worktrees"),
    "XDG_DATA_HOME": str(TEST_BASE_DIR / "xdg-data"),
    "XDG_CONFIG_HOME": str(TEST_BASE_DIR / "xdg-config"),
    "XDG_CACHE_HOME": str(TEST_BASE_DIR / "xdg-cache"),
    "XDG_STATE_HOME": str(TEST_BASE_DIR / "xdg-state"),
}


def apply_test_env() -> None:
    for env_key, env_value in TEST_ENV.items():
        os.environ[env_key] = env_value


def coerce_db_path(database: object) -> Path | None:
    if isinstance(database, Path):
        return database
    if not isinstance(database, str):
        return None
    if database in {":memory:", "sqlite+aiosqlite:///:memory:", "sqlite:///:memory:"}:
        return None

    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if database.startswith(prefix):
            database = database.removeprefix(prefix)
            break

    if not database or database.startswith("file:"):
        return None
    return Path(database)


def is_production_db_path(path: Path) -> bool:
    return path.expanduser().resolve() == REAL_PRODUCTION_DB_PATH


def is_within_test_base(path: Path) -> bool:
    return path.expanduser().resolve().is_relative_to(_TEST_BASE_DIR_RESOLVED)


def is_safe_test_db_path(path: Path) -> bool:
    """Return True only if *path* is clearly inside the test temp tree or a pytest tmp_path."""
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(_TEST_BASE_DIR_RESOLVED):
        return True
    # pytest tmp_path directories live under the system tempdir
    try:
        tmp_root = Path(tempfile.gettempdir()).resolve()
        if resolved.is_relative_to(tmp_root):
            return True
    except (OSError, ValueError):
        pass
    return False
