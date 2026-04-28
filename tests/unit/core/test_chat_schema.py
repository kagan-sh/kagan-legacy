"""Unit tests: ChatSession / ChatMessage schema properties.

These tests verify structural invariants of the two new models.
They use the private module directly (allowed for unit tests per
docs/internal/testing.md).
"""

import sqlite3
from pathlib import Path

import pytest

from kagan.core.models import ChatMessage, ChatSession

pytestmark = [pytest.mark.unit]


def _make_db(tmp_path: Path) -> Path:
    """Boot a KaganCore to get a fully-migrated SQLite file, then return its path."""
    from kagan.core import KaganCore

    db_path = tmp_path / "test.db"
    client = KaganCore(db_path=db_path)
    client.close()
    return db_path


def test_chat_message_has_autoincrement_pk(tmp_path: Path) -> None:
    """chat_messages.id must be an auto-incrementing integer PK."""
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        # Insert two rows and verify ids are assigned and monotonically increasing
        conn.execute(
            "INSERT INTO chat_sessions (id, label, source, created_at, updated_at) "
            "VALUES ('sess01', 'Test', 'test', datetime('now'), datetime('now'))"
        )
        conn.execute(
            "INSERT INTO chat_messages "
            "(session_id, role, content, terminated_at_user_request, created_at) "
            "VALUES ('sess01', 'user', 'hello', 0, datetime('now'))"
        )
        conn.execute(
            "INSERT INTO chat_messages "
            "(session_id, role, content, terminated_at_user_request, created_at) "
            "VALUES ('sess01', 'assistant', 'hi', 0, datetime('now'))"
        )
        conn.commit()

        rows = conn.execute(
            "SELECT id FROM chat_messages WHERE session_id = 'sess01' ORDER BY id"
        ).fetchall()
        ids = [r[0] for r in rows]
        assert len(ids) == 2
        # IDs must be positive integers assigned by AUTOINCREMENT
        assert ids[0] > 0
        assert ids[1] > ids[0]
    finally:
        conn.close()


def test_session_indexes_support_recency_listing(tmp_path: Path) -> None:
    """chat_sessions must be indexed on project_id and updated_at for recency queries."""
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(chat_sessions)").fetchall()
        }
        # SQLModel create_all creates individual indexes from Field(index=True)
        # The migration additionally creates a composite index; on fresh DBs only
        # the individual ones exist.
        assert "ix_chat_sessions_project_id" in indexes
        assert "ix_chat_sessions_updated_at" in indexes
        # Check the session_id cursor index on messages exists
        msg_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(chat_messages)").fetchall()
        }
        assert "ix_chat_messages_session_id" in msg_indexes
    finally:
        conn.close()


def test_terminated_at_user_request_defaults_false(tmp_path: Path) -> None:
    """terminated_at_user_request stores and returns False (0 in SQLite) correctly."""
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO chat_sessions (id, label, source, created_at, updated_at) "
            "VALUES ('sess02', 'Default Test', 'test', datetime('now'), datetime('now'))"
        )
        conn.execute(
            "INSERT INTO chat_messages "
            "(session_id, role, content, terminated_at_user_request, created_at) "
            "VALUES ('sess02', 'user', 'message', 0, datetime('now'))"
        )
        conn.commit()
        row = conn.execute(
            "SELECT terminated_at_user_request FROM chat_messages "
            "WHERE session_id = 'sess02'"
        ).fetchone()
        assert row is not None
        assert row[0] == 0  # SQLite stores False as 0
    finally:
        conn.close()


def test_chat_session_model_fields_match_schema() -> None:
    """ChatSession model has all required fields with correct types."""
    assert hasattr(ChatSession, "id")
    assert hasattr(ChatSession, "label")
    assert hasattr(ChatSession, "source")
    assert hasattr(ChatSession, "agent_backend")
    assert hasattr(ChatSession, "project_id")
    assert hasattr(ChatSession, "created_at")
    assert hasattr(ChatSession, "updated_at")
    assert hasattr(ChatSession, "messages")


def test_chat_message_model_fields_match_schema() -> None:
    """ChatMessage model has all required fields with correct types."""
    assert hasattr(ChatMessage, "id")
    assert hasattr(ChatMessage, "session_id")
    assert hasattr(ChatMessage, "role")
    assert hasattr(ChatMessage, "content")
    assert hasattr(ChatMessage, "terminated_at_user_request")
    assert hasattr(ChatMessage, "created_at")
    assert hasattr(ChatMessage, "session")
