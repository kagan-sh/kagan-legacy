"""Unit tests: chat sessions migration crash-safety.

Verifies that the a3f9d1c2e4b5 migration:
  - runs on a fresh DB without error
  - runs when chat_sessions_v1 setting exists (legacy upgrade path)
  - DROPS the chat_sessions_v1 setting row (no data preserved)
  - is idempotent when run twice

All tests run alembic upgrade programmatically against a temp SQLite DB.
"""

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


def _run_upgrade_to_prev(db_path: Path) -> None:
    from alembic import command

    cfg = _alembic_config(db_path)
    command.upgrade(cfg, _PREV_REVISION)


def _run_upgrade_head(db_path: Path) -> None:
    from alembic import command

    cfg = _alembic_config(db_path)
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migration_runs_on_fresh_db(tmp_path: Path) -> None:
    """Upgrade on a brand-new DB completes without error."""
    db_path = tmp_path / "fresh.db"
    # Should not raise
    _run_upgrade_head(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "chat_sessions" in tables
        assert "chat_messages" in tables
    finally:
        conn.close()


def test_migration_runs_when_chat_sessions_v1_setting_exists(tmp_path: Path) -> None:
    """Upgrade on a DB that already has the legacy chat_sessions_v1 row does not crash."""
    import json

    db_path = tmp_path / "legacy.db"
    _run_upgrade_to_prev(db_path)

    blob = json.dumps(
        {
            "version": 1,
            "sessions": [
                {
                    "id": "sess_x",
                    "label": "Old Session",
                    "source": "repl",
                    "agent_backend": None,
                    "project_id": None,
                    "orchestrator_history": [["user", "hello"]],
                    "messages_rendered": [],
                    "updated_at": "2026-01-01T00:00:00+00:00",
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

    # Must not raise even with legacy data present
    _run_upgrade_head(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "chat_sessions" in tables
        assert "chat_messages" in tables
    finally:
        conn.close()


def test_migration_drops_legacy_chat_sessions_v1_setting(tmp_path: Path) -> None:
    """The chat_sessions_v1 settings row is deleted by the migration."""
    import json

    db_path = tmp_path / "drop.db"
    _run_upgrade_to_prev(db_path)

    blob = json.dumps({"version": 1, "sessions": []}, separators=(",", ":"))
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (_SETTINGS_KEY, blob),
        )
        conn.commit()
    finally:
        conn.close()

    _run_upgrade_head(db_path)

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (_SETTINGS_KEY,),
        ).fetchone()
        assert row is None, "chat_sessions_v1 setting row must be deleted by the migration"
    finally:
        conn.close()


def test_migration_is_idempotent_when_run_twice(tmp_path: Path) -> None:
    """Running upgrade to head twice does not crash and leaves tables intact."""
    db_path = tmp_path / "idem.db"

    _run_upgrade_head(db_path)  # first run
    _run_upgrade_head(db_path)  # second run (no-op — tables already exist)

    conn = sqlite3.connect(db_path)
    try:
        sess_count = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()
        msg_count = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()
        # Tables exist and are empty (no seeded data)
        assert sess_count == (0,)
        assert msg_count == (0,)
    finally:
        conn.close()
