"""add task github_issue

Adds ``tasks.github_issue`` (nullable TEXT) and backfills it from any
``integration.github.<slug>.sync_map`` settings entries so already-imported
tasks keep their link.

"""

import json

import sqlalchemy as sa
import sqlmodel  # noqa: F401

from alembic import op

revision = "d0378306ab3d"
down_revision = "a3f9d1c2e4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the new column (nullable, no server default needed).
    op.add_column(
        "tasks",
        sa.Column("github_issue", sa.Text(), nullable=True),
    )
    op.create_index(op.f("ix_tasks_github_issue"), "tasks", ["github_issue"], unique=False)

    # 2. Backfill from sync_map settings — single transaction, idempotent.
    conn = op.get_bind()

    # Read all sync_map settings rows.
    rows = conn.execute(
        sa.text("SELECT key, value FROM settings WHERE key LIKE 'integration.github.%.sync_map'")
    ).fetchall()

    for key, value in rows:
        # key is "integration.github.<slug>.sync_map"
        # slug is between the second and last dots (may contain a slash).
        prefix = "integration.github."
        suffix = ".sync_map"
        if not (key.startswith(prefix) and key.endswith(suffix)):
            continue
        slug = key[len(prefix) : -len(suffix)]

        try:
            sync_map: dict = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(sync_map, dict):
            continue

        for number, task_id in sync_map.items():
            if not task_id or not number:
                continue
            link = f"{slug}#{number}"
            conn.execute(
                sa.text(
                    "UPDATE tasks SET github_issue = :link WHERE id = :task_id"
                    " AND github_issue IS NULL"
                ),
                {"link": link, "task_id": task_id},
            )


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_github_issue"), table_name="tasks")
    op.drop_column("tasks", "github_issue")
