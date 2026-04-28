"""Unit tests: chat_sessions_v1 JSON blob -> table migration.

The migration drops the legacy settings row rather than migrating data.
These tests verify the DROP behaviour and that the new tables are created
correctly.  Detailed crash-safety scenarios live in
test_chat_migration_crash_safety.py.
"""

import json
import sqlite3
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_MIGRATION_REVISION = "a3f9d1c2e4b5"
_PREV_REVISION = "6f4d63a80a1e"
_SETTINGS_KEY = "chat_sessions_v1"


# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------


def _alembic_config(db_path: Path):  # type: ignore[return]
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", "kagan:core/adapters/db/migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _run_upgrade_only(db_path: Path) -> None:
    """Run upgrade head (idempotency-safe)."""
    from alembic import command

    cfg = _alembic_config(db_path)
    command.upgrade(cfg, "head")


def _seed_base_schema(db_path: Path, *, with_blob: bool = True) -> None:
    """Create schema at the revision just before our migration, then seed a blob."""
    from alembic import command

    cfg = _alembic_config(db_path)
    command.upgrade(cfg, _PREV_REVISION)

    if with_blob:
        blob = json.dumps(
            {
                "version": 1,
                "sessions": [
                    {
                        "id": "sess_aaa",
                        "label": "Session Alpha",
                        "source": "repl",
                        "agent_backend": "claude-code",
                        "project_id": None,
                        "orchestrator_history": [
                            ["user", "Hello"],
                            ["assistant", "Hi there"],
                        ],
                        "messages_rendered": [],
                        "updated_at": "2026-01-15T10:00:00+00:00",
                    }
                ],
            },
            separators=(",", ":"),
        )
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (_SETTINGS_KEY, blob),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migration_drops_legacy_blob_not_migrates(tmp_path: Path) -> None:
    """The migration deletes chat_sessions_v1; it does NOT copy rows to the new tables."""
    db_path = tmp_path / "drop.db"
    _seed_base_schema(db_path, with_blob=True)

    _run_upgrade_only(db_path)

    conn = sqlite3.connect(db_path)
    try:
        # Legacy setting must be gone
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (_SETTINGS_KEY,)
        ).fetchone()
        assert row is None, "chat_sessions_v1 must be deleted by migration"

        # New tables exist but contain no rows (data NOT migrated)
        sess_count = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()
        assert sess_count == (0,)
    finally:
        conn.close()


def test_migration_creates_tables_on_fresh_db(tmp_path: Path) -> None:
    """When there is no legacy blob, tables are still created correctly."""
    db_path = tmp_path / "fresh.db"
    _seed_base_schema(db_path, with_blob=False)

    _run_upgrade_only(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "chat_sessions" in tables
        assert "chat_messages" in tables
    finally:
        conn.close()


def test_migration_is_idempotent_when_run_twice(tmp_path: Path) -> None:
    """Running upgrade twice does not crash and tables remain empty."""
    db_path = tmp_path / "idem.db"
    _seed_base_schema(db_path, with_blob=True)

    _run_upgrade_only(db_path)  # first upgrade
    _run_upgrade_only(db_path)  # second upgrade (no-op)

    conn = sqlite3.connect(db_path)
    try:
        sess_count = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()
        msg_count = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()
        assert sess_count == (0,)
        assert msg_count == (0,)
    finally:
        conn.close()
