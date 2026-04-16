"""add task_type and agent_role fields for multi-dimensional analytics"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy import inspect as sa_inspect


revision = '6cbe15d02de6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = {c["name"] for c in sa_inspect(conn).get_columns(table)}
    return column in cols


def upgrade() -> None:
    # Add agent_role to sessions if it doesn't exist
    if not _has_column("sessions", "agent_role"):
        op.add_column('sessions', sa.Column('agent_role', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        op.create_index(op.f('ix_sessions_agent_role'), 'sessions', ['agent_role'], unique=False)

    # Add task_type to tasks if it doesn't exist
    if not _has_column("tasks", "task_type"):
        op.add_column('tasks', sa.Column('task_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        op.create_index(op.f('ix_tasks_task_type'), 'tasks', ['task_type'], unique=False)


def downgrade() -> None:
    # Remove task_type from tasks if it exists
    if _has_column("tasks", "task_type"):
        op.drop_index(op.f('ix_tasks_task_type'), table_name='tasks')
        op.drop_column('tasks', 'task_type')

    # Remove agent_role from sessions if it exists
    if _has_column("sessions", "agent_role"):
        op.drop_index(op.f('ix_sessions_agent_role'), table_name='sessions')
        op.drop_column('sessions', 'agent_role')
