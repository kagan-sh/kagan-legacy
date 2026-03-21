"""add session token fields"""

from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "df51db972cd5"
down_revision = "4de4526589c8"
branch_labels = None
depends_on = None

_TOKEN_COLUMNS = [
    "input_tokens",
    "output_tokens",
    "context_window_used",
    "context_window_size",
]


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    for col in _TOKEN_COLUMNS:
        if not _column_exists("sessions", col):
            op.execute(f"ALTER TABLE sessions ADD COLUMN {col} INTEGER DEFAULT NULL")


def downgrade() -> None:
    pass
