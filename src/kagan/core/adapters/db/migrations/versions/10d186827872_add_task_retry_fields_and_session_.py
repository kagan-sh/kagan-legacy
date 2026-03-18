"""add task retry fields and session attempt"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = '10d186827872'
down_revision = 'd7293d9c017b'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = {c["name"] for c in sa_inspect(conn).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("sessions", "attempt"):
        op.add_column('sessions', sa.Column('attempt', sa.Integer(), nullable=False, server_default='1'))
    if not _has_column("tasks", "max_retries"):
        op.add_column('tasks', sa.Column('max_retries', sa.Integer(), nullable=False, server_default='0'))
    if not _has_column("tasks", "success_command"):
        op.add_column('tasks', sa.Column('success_command', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'success_command')
    op.drop_column('tasks', 'max_retries')
    op.drop_column('sessions', 'attempt')
