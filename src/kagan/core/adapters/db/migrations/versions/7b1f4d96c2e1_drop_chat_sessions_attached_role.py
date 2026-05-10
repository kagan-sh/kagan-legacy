"""drop chat_sessions.attached_role

The attached role is derived from sessions.agent_role through
chat_sessions.attached_session_id. Persisting both values allowed them to drift.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "7b1f4d96c2e1"
down_revision = "25420575c1aa"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    if _has_column("chat_sessions", "attached_role"):
        op.drop_column("chat_sessions", "attached_role")


def downgrade() -> None:
    if not _has_column("chat_sessions", "attached_role"):
        op.add_column(
            "chat_sessions",
            sa.Column("attached_role", sa.String(), nullable=True),
        )
