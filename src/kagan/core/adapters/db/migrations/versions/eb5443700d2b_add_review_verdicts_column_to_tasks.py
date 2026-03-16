"""add review_verdicts column to tasks"""

from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = 'eb5443700d2b'
down_revision = '0001_v060_to_latest'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("tasks", "review_verdicts"):
        op.execute("ALTER TABLE tasks ADD COLUMN review_verdicts JSON DEFAULT '[]'")


def downgrade() -> None:
    pass
