"""chat_session_attach_target

Adds attached_session_id and attached_role to chat_sessions so a chat session
can be pinned to a specific agent session.

Note: the 0001_v060_to_latest migration runs SQLModel.metadata.create_all()
which already creates these columns on fresh-ish databases. This migration
is therefore written idempotently: it only adds the column/index when absent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "25420575c1aa"
down_revision = "5041f8573a34"
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
    if not _has_column("chat_sessions", "attached_session_id"):
        op.add_column(
            "chat_sessions",
            sa.Column("attached_session_id", sa.String(), nullable=True),
        )
    if not _has_column("chat_sessions", "attached_role"):
        op.add_column(
            "chat_sessions",
            sa.Column("attached_role", sa.String(), nullable=True),
        )
    if not _has_index("ix_chat_sessions_attached_session_id", "chat_sessions"):
        op.create_index(
            "ix_chat_sessions_attached_session_id",
            "chat_sessions",
            ["attached_session_id"],
            unique=False,
        )


def downgrade() -> None:
    if _has_index("ix_chat_sessions_attached_session_id", "chat_sessions"):
        op.drop_index(
            "ix_chat_sessions_attached_session_id", table_name="chat_sessions"
        )
    if _has_column("chat_sessions", "attached_role"):
        op.drop_column("chat_sessions", "attached_role")
    if _has_column("chat_sessions", "attached_session_id"):
        op.drop_column("chat_sessions", "attached_session_id")
