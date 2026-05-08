"""drop attached_session_id from chat_sessions

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-05-08 16:23:00.000000

"""

from __future__ import annotations

from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _has_index(index_name: str, table: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table}'"
    ).fetchall()
    return any(row[0] == index_name for row in rows)


def upgrade() -> None:
    if _has_index("ix_chat_sessions_attached_session_id", "chat_sessions"):
        op.drop_index(
            "ix_chat_sessions_attached_session_id", table_name="chat_sessions"
        )
    if _has_column("chat_sessions", "attached_session_id"):
        op.drop_column("chat_sessions", "attached_session_id")


def downgrade() -> None:
    import sqlalchemy as sa

    if not _has_column("chat_sessions", "attached_session_id"):
        op.add_column(
            "chat_sessions",
            sa.Column("attached_session_id", sa.String(), nullable=True),
        )
    if not _has_index("ix_chat_sessions_attached_session_id", "chat_sessions"):
        op.create_index(
            "ix_chat_sessions_attached_session_id",
            "chat_sessions",
            ["attached_session_id"],
            unique=False,
        )
