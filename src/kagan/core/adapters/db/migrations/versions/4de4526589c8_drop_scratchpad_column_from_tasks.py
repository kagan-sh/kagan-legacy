"""drop scratchpad column from tasks"""

from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "4de4526589c8"
down_revision = "eb5443700d2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _column_exists("tasks", "scratchpad"):
        op.drop_column("tasks", "scratchpad")


def downgrade() -> None:
    if not _column_exists("tasks", "scratchpad"):
        op.execute("ALTER TABLE tasks ADD COLUMN scratchpad VARCHAR DEFAULT '' NOT NULL")


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    return column in {c["name"] for c in inspector.get_columns(table)}
