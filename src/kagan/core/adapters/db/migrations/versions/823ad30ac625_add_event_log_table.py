"""add event_log table

Adds the ``event_log`` table used by ``EventLog`` (kagan.core._event_log).
Each row is one append-only frame keyed by ``(session_id, kind, seq)``.

Schema
------
- ``id``         TEXT PK
- ``session_id`` TEXT (indexed; no FK declared — see note below)
- ``kind``       TEXT (e.g. 'chat', 'task')
- ``seq``        INTEGER — monotonic counter per (session_id, kind)
- ``idx``        INTEGER — entry index per (session_id, kind)
- ``ts``         DATETIME — UTC insertion timestamp
- ``frame``      JSON — arbitrary payload

Constraints / indexes
---------------------
- UNIQUE (session_id, kind, seq)   — uq_event_log_session_kind_seq
- INDEX  (session_id, kind, seq)   — ix_event_log_session_kind_seq  [replay scans]
- INDEX  (session_id)              — ix_event_log_session_id

FK omission note
----------------
The ``session_id`` column intentionally has **no FOREIGN KEY constraint** in
this migration.  A SQLite quirk causes the ``REFERENCES sessions (id)`` text to
be stored as ``REFERENCES sessions_old (id)`` when the CREATE TABLE statement is
executed within the same alembic connection scope that previously ran the
``6f4d63a80a1e`` migration (which renamed ``sessions`` to ``sessions_old``).
At early-alpha, application-level integrity (``EventLog.append`` always receives
a valid session_id) is sufficient.  The FK will be added via a future migration
once the SQLite RENAME TABLE artifact is resolved.

This migration is intentionally narrow — only ``event_log`` is created.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "823ad30ac625"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None

_TABLE = "event_log"


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    return sa_inspect(conn).has_table(name)


def upgrade() -> None:
    if _has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("frame", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "kind",
            "seq",
            name="uq_event_log_session_kind_seq",
        ),
    )
    op.create_index(
        op.f("ix_event_log_session_id"),
        _TABLE,
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_event_log_session_kind_seq",
        _TABLE,
        ["session_id", "kind", "seq"],
        unique=False,
    )


def downgrade() -> None:
    if not _has_table(_TABLE):
        return

    op.drop_index("ix_event_log_session_kind_seq", table_name=_TABLE)
    op.drop_index(op.f("ix_event_log_session_id"), table_name=_TABLE)
    op.drop_table(_TABLE)
