from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection
from sqlmodel import SQLModel

from kagan.core import models as _models  # noqa: F401

revision = "0001_v060_to_latest"
down_revision = None
branch_labels = None
depends_on = None


def _table_names(conn: Connection) -> set[str]:
    inspector = sa.inspect(conn)
    return set(inspector.get_table_names())


def _column_names(conn: Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if table_name not in tables:
        return set()
    return {str(col["name"]) for col in inspector.get_columns(table_name)}


def _add_column_if_missing(conn: Connection, table_name: str, column_name: str, ddl: str) -> None:
    if column_name in _column_names(conn, table_name):
        return
    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


def _ensure_latest_tables(conn: Connection) -> None:
    SQLModel.metadata.create_all(bind=conn)


def _ensure_required_columns(conn: Connection) -> None:
    required_columns: dict[str, tuple[tuple[str, str], ...]] = {
        "repos": (
            ("project_id", "VARCHAR DEFAULT NULL"),
            ("default_branch", "VARCHAR DEFAULT 'main'"),
        ),
        "tasks": (
            ("execution_mode", "VARCHAR DEFAULT 'PAIR'"),
            ("launcher", "VARCHAR DEFAULT NULL"),
            ("review_approved", "BOOLEAN DEFAULT 0"),
            ("scratchpad", "TEXT DEFAULT ''"),
        ),
        "worktrees": (
            ("repo_id", "VARCHAR DEFAULT NULL"),
            ("worktree_path", "TEXT DEFAULT NULL"),
        ),
        "sessions": (
            ("task_id", "VARCHAR DEFAULT NULL"),
            ("mode", "VARCHAR DEFAULT 'PAIR'"),
            ("agent_backend", "VARCHAR DEFAULT 'codex'"),
            ("launcher", "VARCHAR DEFAULT NULL"),
            ("pid", "INTEGER DEFAULT NULL"),
            ("persona", "VARCHAR DEFAULT NULL"),
        ),
    }

    for table_name, columns in required_columns.items():
        if table_name not in _table_names(conn):
            continue
        for column_name, ddl in columns:
            _add_column_if_missing(conn, table_name, column_name, ddl)


def _promote_legacy_workspaces(conn: Connection) -> None:
    tables = _table_names(conn)
    if "workspaces" not in tables:
        return

    workspace_columns = _column_names(conn, "workspaces")
    has_workspace_project = "project_id" in workspace_columns
    has_workspace_path = "path" in workspace_columns

    if "worktrees" not in tables:
        conn.exec_driver_sql("ALTER TABLE workspaces RENAME TO worktrees")
        return

    fallback_repo_expr = (
        "(SELECT r.id FROM repos AS r "
        "JOIN tasks AS t ON t.id = w.task_id "
        "WHERE r.project_id = t.project_id "
        "ORDER BY r.created_at ASC LIMIT 1)"
    )
    if has_workspace_project:
        fallback_repo_expr = (
            "(SELECT r.id FROM repos AS r "
            "WHERE r.project_id = w.project_id "
            "ORDER BY r.created_at ASC LIMIT 1)"
        )

    has_workspace_repos = "workspace_repos" in tables
    if has_workspace_repos:
        repo_expr = "COALESCE((SELECT wr.repo_id FROM workspace_repos AS wr "
        repo_expr += "WHERE wr.workspace_id = w.id ORDER BY wr.created_at ASC LIMIT 1), "
        repo_expr += f"{fallback_repo_expr})"
        path_expr = "(SELECT wr.worktree_path FROM workspace_repos AS wr "
        path_expr += "WHERE wr.workspace_id = w.id AND wr.worktree_path IS NOT NULL "
        path_expr += "ORDER BY wr.created_at ASC LIMIT 1)"
        if has_workspace_path:
            path_expr = f"COALESCE({path_expr}, w.path)"
    else:
        repo_expr = fallback_repo_expr
        path_expr = "w.path" if has_workspace_path else "NULL"

    conn.exec_driver_sql(
        f"""
        INSERT OR IGNORE INTO worktrees (
            id,
            task_id,
            repo_id,
            worktree_path,
            branch_name,
            created_at,
            updated_at
        )
        SELECT
            w.id,
            w.task_id,
            {repo_expr},
            {path_expr},
            w.branch_name,
            w.created_at,
            w.updated_at
        FROM workspaces AS w
        WHERE w.task_id IS NOT NULL
          AND {repo_expr} IS NOT NULL
          AND {path_expr} IS NOT NULL
          AND {path_expr} != ''
        """
    )
    conn.exec_driver_sql("DROP TABLE workspaces")


def _backfill_repos(conn: Connection) -> None:
    tables = _table_names(conn)
    if "repos" not in tables:
        return

    if "project_repos" in tables:
        conn.exec_driver_sql(
            """
            UPDATE repos
            SET project_id = (
                SELECT pr.project_id
                FROM project_repos AS pr
                WHERE pr.repo_id = repos.id
                ORDER BY pr.is_primary DESC, pr.created_at ASC
                LIMIT 1
            )
            WHERE project_id IS NULL
            """
        )
    conn.exec_driver_sql(
        """
        UPDATE repos
        SET project_id = (
            SELECT p.id
            FROM projects AS p
            ORDER BY p.created_at ASC
            LIMIT 1
        )
        WHERE project_id IS NULL
        """
    )
    conn.exec_driver_sql("UPDATE repos SET default_branch = 'main' WHERE default_branch IS NULL")


def _backfill_tasks(conn: Connection) -> None:
    task_columns = _column_names(conn, "tasks")
    if not task_columns:
        return

    if "task_type" in task_columns:
        conn.exec_driver_sql(
            """
            UPDATE tasks
            SET execution_mode = CASE UPPER(COALESCE(task_type, ''))
                WHEN 'AUTO' THEN 'AUTO'
                ELSE 'PAIR'
            END
            WHERE task_type IS NOT NULL
            """
        )
    conn.exec_driver_sql(
        """
        UPDATE tasks
        SET execution_mode = 'PAIR'
        WHERE execution_mode IS NULL OR execution_mode = ''
        """
    )
    if "terminal_backend" in task_columns:
        conn.exec_driver_sql(
            """
            UPDATE tasks
            SET launcher = lower(terminal_backend)
            WHERE (launcher IS NULL OR launcher = '')
              AND terminal_backend IS NOT NULL
            """
        )
    if "acceptance_criteria" in task_columns:
        conn.exec_driver_sql(
            """
            UPDATE tasks
            SET acceptance_criteria = '[]'
            WHERE acceptance_criteria IS NULL
            """
        )
    conn.exec_driver_sql(
        """
        UPDATE tasks
        SET status = CASE UPPER(TRIM(COALESCE(status, '')))
            WHEN 'BACKLOG' THEN 'BACKLOG'
            WHEN 'IN_PROGRESS' THEN 'IN_PROGRESS'
            WHEN 'REVIEW' THEN 'REVIEW'
            WHEN 'DONE' THEN 'DONE'
            ELSE 'BACKLOG'
        END
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE tasks
        SET priority = CASE UPPER(TRIM(CAST(priority AS TEXT)))
            WHEN '0' THEN 'LOW'
            WHEN '1' THEN 'MEDIUM'
            WHEN '2' THEN 'HIGH'
            WHEN '3' THEN 'CRITICAL'
            WHEN 'LOW' THEN 'LOW'
            WHEN 'MEDIUM' THEN 'MEDIUM'
            WHEN 'HIGH' THEN 'HIGH'
            WHEN 'CRITICAL' THEN 'CRITICAL'
            ELSE 'MEDIUM'
        END
        """
    )
    conn.exec_driver_sql("UPDATE tasks SET review_approved = 0 WHERE review_approved IS NULL")
    conn.exec_driver_sql("UPDATE tasks SET scratchpad = '' WHERE scratchpad IS NULL")


def _backfill_worktrees(conn: Connection) -> None:
    tables = _table_names(conn)
    columns = _column_names(conn, "worktrees")
    if not columns:
        return

    if "path" in columns:
        conn.exec_driver_sql(
            """
            UPDATE worktrees
            SET worktree_path = path
            WHERE (worktree_path IS NULL OR worktree_path = '')
              AND path IS NOT NULL
            """
        )
    if "workspace_repos" in tables:
        conn.exec_driver_sql(
            """
            UPDATE worktrees
            SET repo_id = (
                SELECT wr.repo_id
                FROM workspace_repos AS wr
                WHERE wr.workspace_id = worktrees.id
                ORDER BY wr.created_at ASC
                LIMIT 1
            )
            WHERE repo_id IS NULL
            """
        )
        conn.exec_driver_sql(
            """
            UPDATE worktrees
            SET worktree_path = (
                SELECT wr.worktree_path
                FROM workspace_repos AS wr
                WHERE wr.workspace_id = worktrees.id
                  AND wr.worktree_path IS NOT NULL
                ORDER BY wr.created_at ASC
                LIMIT 1
            )
            WHERE worktree_path IS NULL OR worktree_path = ''
            """
        )
    if "project_id" in columns:
        conn.exec_driver_sql(
            """
            UPDATE worktrees
            SET repo_id = (
                SELECT r.id
                FROM repos AS r
                WHERE r.project_id = worktrees.project_id
                ORDER BY r.created_at ASC
                LIMIT 1
            )
            WHERE repo_id IS NULL
            """
        )
    conn.exec_driver_sql(
        """
        UPDATE worktrees
        SET repo_id = (
            SELECT r.id
            FROM repos AS r
            JOIN tasks AS t ON t.id = worktrees.task_id
            WHERE r.project_id = t.project_id
            ORDER BY r.created_at ASC
            LIMIT 1
        )
        WHERE repo_id IS NULL
        """
    )
    conn.exec_driver_sql(
        """
        DELETE FROM worktrees
        WHERE task_id IS NULL
           OR repo_id IS NULL
           OR worktree_path IS NULL
           OR worktree_path = ''
        """
    )


def _migrate_sessions(conn: Connection) -> None:
    columns = _column_names(conn, "sessions")
    if not columns:
        return

    is_legacy = "workspace_id" in columns or "session_type" in columns or "external_id" in columns
    if not is_legacy:
        return

    conn.exec_driver_sql("DROP INDEX IF EXISTS ix_sessions_mode")
    conn.exec_driver_sql("DROP INDEX IF EXISTS ix_sessions_status")
    conn.exec_driver_sql("DROP INDEX IF EXISTS ix_sessions_task_id")
    conn.exec_driver_sql("ALTER TABLE sessions RENAME TO sessions_legacy")

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("agent_backend", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("launcher", sa.String(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("persona", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_sessions_mode ON sessions (mode)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions (status)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_sessions_task_id ON sessions (task_id)")

    conn.exec_driver_sql(
        """
        INSERT OR IGNORE INTO sessions (
            id,
            task_id,
            mode,
            agent_backend,
            status,
            launcher,
            pid,
            started_at,
            ended_at,
            persona
        )
        SELECT
            s.id,
            COALESCE(s.task_id, w.task_id),
            CASE UPPER(COALESCE(s.session_type, ''))
                WHEN 'ACP' THEN 'AUTO'
                ELSE 'PAIR'
            END,
            COALESCE(t.agent_backend, 'codex'),
            CASE UPPER(COALESCE(s.status, ''))
                WHEN 'ACTIVE' THEN 'RUNNING'
                WHEN 'CLOSED' THEN 'COMPLETED'
                WHEN 'FAILED' THEN 'FAILED'
                WHEN 'PENDING' THEN 'PENDING'
                WHEN 'RUNNING' THEN 'RUNNING'
                WHEN 'COMPLETED' THEN 'COMPLETED'
                WHEN 'CANCELLED' THEN 'CANCELLED'
                ELSE 'COMPLETED'
            END,
            t.launcher,
            NULL,
            COALESCE(s.started_at, CURRENT_TIMESTAMP),
            s.ended_at,
            NULL
        FROM sessions_legacy AS s
        LEFT JOIN worktrees AS w ON w.id = s.workspace_id
        LEFT JOIN tasks AS t ON t.id = COALESCE(s.task_id, w.task_id)
        WHERE COALESCE(s.task_id, w.task_id) IS NOT NULL
        """
    )
    conn.exec_driver_sql("DROP TABLE sessions_legacy")


def _backfill_sessions(conn: Connection) -> None:
    columns = _column_names(conn, "sessions")
    if not columns:
        return

    conn.exec_driver_sql(
        """
        UPDATE sessions
        SET mode = (
            SELECT t.execution_mode
            FROM tasks AS t
            WHERE t.id = sessions.task_id
            LIMIT 1
        )
        WHERE mode IS NULL OR mode = '' OR mode = 'PAIR'
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE sessions
        SET mode = 'PAIR'
        WHERE mode IS NULL OR mode = ''
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE sessions
        SET agent_backend = (
            SELECT COALESCE(t.agent_backend, 'codex')
            FROM tasks AS t
            WHERE t.id = sessions.task_id
            LIMIT 1
        )
        WHERE agent_backend IS NULL OR agent_backend = ''
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE sessions
        SET agent_backend = 'codex'
        WHERE agent_backend IS NULL OR agent_backend = ''
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE sessions
        SET launcher = (
            SELECT t.launcher
            FROM tasks AS t
            WHERE t.id = sessions.task_id
            LIMIT 1
        )
        WHERE (launcher IS NULL OR launcher = '')
          AND task_id IS NOT NULL
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE sessions
        SET status = CASE UPPER(COALESCE(status, ''))
            WHEN 'ACTIVE' THEN 'RUNNING'
            WHEN 'CLOSED' THEN 'COMPLETED'
            WHEN 'FAILED' THEN 'FAILED'
            WHEN 'PENDING' THEN 'PENDING'
            WHEN 'RUNNING' THEN 'RUNNING'
            WHEN 'COMPLETED' THEN 'COMPLETED'
            WHEN 'CANCELLED' THEN 'CANCELLED'
            ELSE 'COMPLETED'
        END
        """
    )
    conn.exec_driver_sql("DELETE FROM sessions WHERE task_id IS NULL")


def _drop_legacy_tables(conn: Connection, names: Iterable[str]) -> None:
    existing_tables = _table_names(conn)
    for table_name in names:
        if table_name in existing_tables:
            conn.exec_driver_sql(f"DROP TABLE {table_name}")


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        _ensure_latest_tables(bind)
        _ensure_required_columns(bind)
        _backfill_repos(bind)
        _promote_legacy_workspaces(bind)
        _ensure_required_columns(bind)
        _backfill_tasks(bind)
        _backfill_worktrees(bind)
        _migrate_sessions(bind)
        _ensure_required_columns(bind)
        _backfill_sessions(bind)
        _drop_legacy_tables(bind, ("project_repos", "workspace_repos"))
    finally:
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported for the bootstrap migration")
