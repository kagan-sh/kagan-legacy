"""chat sessions to tables

Create ``chat_sessions`` and ``chat_messages`` tables and DROP the legacy
``chat_sessions_v1`` JSON blob from the settings table.

Beta users lose in-progress chat data — this is accepted.  The migration
is idempotent: CREATE TABLE IF NOT EXISTS guards ensure a partial prior run
does not crash the upgrade.

Downgrade drops both tables.  No data is restored on downgrade.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "a3f9d1c2e4b5"
down_revision = "6f4d63a80a1e"
branch_labels = None
depends_on = None

_SETTINGS_KEY = "chat_sessions_v1"


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    return sa_inspect(conn).has_table(name)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Create chat_sessions (idempotent) ──────────────────────────────
    if not _has_table("chat_sessions"):
        bind.exec_driver_sql(
            """
            CREATE TABLE chat_sessions (
                id      VARCHAR NOT NULL,
                label   VARCHAR NOT NULL,
                source  VARCHAR NOT NULL,
                agent_backend VARCHAR,
                project_id    VARCHAR,
                created_at    DATETIME NOT NULL,
                updated_at    DATETIME NOT NULL,
                PRIMARY KEY (id),
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL
            )
            """
        )
        bind.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chat_sessions_project_id_updated_at "
            "ON chat_sessions (project_id, updated_at DESC)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chat_sessions_created_at "
            "ON chat_sessions (created_at)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chat_sessions_updated_at "
            "ON chat_sessions (updated_at)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chat_sessions_project_id "
            "ON chat_sessions (project_id)"
        )

    # ── 2. Create chat_messages (idempotent) ──────────────────────────────
    if not _has_table("chat_messages"):
        bind.exec_driver_sql(
            """
            CREATE TABLE chat_messages (
                id          INTEGER NOT NULL,
                session_id  VARCHAR NOT NULL,
                role        VARCHAR NOT NULL,
                content     TEXT    NOT NULL,
                terminated_at_user_request BOOLEAN NOT NULL DEFAULT 0,
                created_at  DATETIME NOT NULL,
                PRIMARY KEY (id),
                FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
            )
            """
        )
        bind.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id "
            "ON chat_messages (session_id)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id_id "
            "ON chat_messages (session_id, id)"
        )
        bind.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_chat_messages_created_at "
            "ON chat_messages (created_at)"
        )

    # ── 3. DROP legacy settings blob (no data preserved) ─────────────────
    bind.exec_driver_sql(
        "DELETE FROM settings WHERE key = ?",
        (_SETTINGS_KEY,),
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    bind = op.get_bind()

    # Drop tables (messages first due to FK)
    if _has_table("chat_messages"):
        bind.exec_driver_sql("DROP INDEX IF EXISTS ix_chat_messages_session_id")
        bind.exec_driver_sql("DROP INDEX IF EXISTS ix_chat_messages_session_id_id")
        bind.exec_driver_sql("DROP INDEX IF EXISTS ix_chat_messages_created_at")
        bind.exec_driver_sql("DROP TABLE chat_messages")

    if _has_table("chat_sessions"):
        bind.exec_driver_sql(
            "DROP INDEX IF EXISTS ix_chat_sessions_project_id_updated_at"
        )
        bind.exec_driver_sql("DROP INDEX IF EXISTS ix_chat_sessions_created_at")
        bind.exec_driver_sql("DROP INDEX IF EXISTS ix_chat_sessions_updated_at")
        bind.exec_driver_sql("DROP INDEX IF EXISTS ix_chat_sessions_project_id")
        bind.exec_driver_sql("DROP TABLE chat_sessions")
