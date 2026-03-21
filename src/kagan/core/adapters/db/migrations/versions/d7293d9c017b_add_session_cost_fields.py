"""add session cost fields"""

from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "d7293d9c017b"
down_revision = "df51db972cd5"
branch_labels = None
depends_on = None

_COST_COLUMNS = {
    "cost_amount": "REAL",
    "cost_currency": "VARCHAR",
}


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    for col, col_type in _COST_COLUMNS.items():
        if not _column_exists("sessions", col):
            op.execute(f"ALTER TABLE sessions ADD COLUMN {col} {col_type} DEFAULT NULL")


def downgrade() -> None:
    pass
