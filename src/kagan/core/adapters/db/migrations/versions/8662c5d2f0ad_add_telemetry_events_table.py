"""add telemetry_events table"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy import inspect as sa_inspect


revision = '8662c5d2f0ad'
down_revision = '6cbe15d02de6'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    return sa_inspect(conn).has_table(name)


def upgrade() -> None:
    if not _has_table('telemetry_events'):
        op.create_table(
            'telemetry_events',
            sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('event_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('payload', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            op.f('ix_telemetry_events_event_type'),
            'telemetry_events',
            ['event_type'],
            unique=False,
        )


def downgrade() -> None:
    if _has_table('telemetry_events'):
        op.drop_index(op.f('ix_telemetry_events_event_type'), table_name='telemetry_events')
        op.drop_table('telemetry_events')
