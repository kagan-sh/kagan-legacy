"""add session_type to chat_sessions

Revision ID: f1a2b3c4d5e6
Revises: 7b1f4d96c2e1
Create Date: 2026-05-08 14:42:27.643991

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "7b1f4d96c2e1"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    if not _has_column("chat_sessions", "session_type"):
        op.add_column(
            "chat_sessions",
            sa.Column("session_type", sa.String(), nullable=False, server_default="orchestrator"),
        )
        op.create_index("ix_chat_sessions_session_type", "chat_sessions", ["session_type"])

    # Ensure existing rows are set to 'orchestrator' (server_default handles
    # new rows, but explicit update is defensive for existing DBs).
    bind = op.get_bind()
    bind.exec_driver_sql("UPDATE chat_sessions SET session_type = 'orchestrator' WHERE session_type IS NULL")


def downgrade() -> None:
    if _has_column("chat_sessions", "session_type"):
        op.drop_index("ix_chat_sessions_session_type", table_name="chat_sessions")
        op.drop_column("chat_sessions", "session_type")
