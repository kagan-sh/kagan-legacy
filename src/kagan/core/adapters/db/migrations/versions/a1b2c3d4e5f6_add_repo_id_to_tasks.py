"""add repo_id to tasks"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = 'a1b2c3d4e5f6'
down_revision = '10d186827872'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = {c["name"] for c in sa_inspect(conn).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("tasks", "repo_id"):
        op.add_column('tasks', sa.Column('repo_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        op.create_index(op.f('ix_tasks_repo_id'), 'tasks', ['repo_id'])


def downgrade() -> None:
    if _has_column('tasks', 'repo_id'):
        op.drop_index(op.f('ix_tasks_repo_id'), 'tasks')
        op.drop_column('tasks', 'repo_id')
