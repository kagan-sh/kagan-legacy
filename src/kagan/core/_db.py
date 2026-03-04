"""Database engine creation for kagan.core — WAL mode, FK enforcement, tables on first use."""

import os
import sqlite3
from pathlib import Path
from typing import Final

from loguru import logger
from sqlalchemy import Engine, event, inspect, text
from sqlalchemy.engine.reflection import Inspector
from sqlmodel import SQLModel, create_engine

from kagan.core.models import (  # noqa: F401
    AuditEntry,
    Project,
    Repository,
    Session,
    SessionEvent,
    Setting,
    Task,
    TaskNote,
    Worktree,
)

_REQUIRED_COLUMNS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
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

_ALPHA_MIGRATION_SHIM_TODO: Final[str] = (
    "TODO(prod-migrations): remove startup compatibility shim and switch to "
    "first-class Alembic upgrade path for stable releases"
)


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector: Inspector, table_name: str) -> set[str]:
    tables = _table_names(inspector)
    if table_name not in tables:
        return set()
    return {str(col["name"]) for col in inspector.get_columns(table_name)}


def _add_column_if_missing(engine: Engine, table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    if column_name in _column_names(inspector, table_name):
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    logger.debug("Migration: added {}.{}", table_name, column_name)


def _promote_legacy_workspaces(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = _table_names(inspector)
    if "workspaces" not in tables:
        return

    workspace_columns = _column_names(inspector, "workspaces")
    has_workspace_project = "project_id" in workspace_columns
    has_workspace_path = "path" in workspace_columns

    if "worktrees" not in tables:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE workspaces RENAME TO worktrees"))
        logger.debug("Migration: renamed workspaces -> worktrees")
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

    with engine.begin() as conn:
        conn.execute(
            text(
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
        )
        conn.execute(text("DROP TABLE workspaces"))
    logger.debug("Migration: copied compatible workspaces rows into worktrees")


def _ensure_required_columns(engine: Engine) -> None:
    for table_name, columns in _REQUIRED_COLUMNS.items():
        for column_name, ddl in columns:
            _add_column_if_missing(engine, table_name, column_name, ddl)


def _backfill_repos(engine: Engine) -> None:
    inspector = inspect(engine)
    if "repos" not in _table_names(inspector):
        return

    has_project_repos = "project_repos" in _table_names(inspector)
    with engine.begin() as conn:
        if has_project_repos:
            conn.execute(
                text(
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
            )
        conn.execute(
            text(
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
        )
        conn.execute(text("UPDATE repos SET default_branch = 'main' WHERE default_branch IS NULL"))


def _backfill_tasks(engine: Engine) -> None:
    inspector = inspect(engine)
    task_columns = _column_names(inspector, "tasks")
    if not task_columns:
        return

    with engine.begin() as conn:
        if "task_type" in task_columns:
            conn.execute(
                text(
                    """
                    UPDATE tasks
                    SET execution_mode = CASE UPPER(COALESCE(task_type, ''))
                        WHEN 'AUTO' THEN 'AUTO'
                        ELSE 'PAIR'
                    END
                    WHERE task_type IS NOT NULL
                    """
                )
            )
        conn.execute(
            text(
                """
                UPDATE tasks
                SET execution_mode = 'PAIR'
                WHERE execution_mode IS NULL OR execution_mode = ''
                """
            )
        )
        if "terminal_backend" in task_columns:
            conn.execute(
                text(
                    """
                    UPDATE tasks
                    SET launcher = lower(terminal_backend)
                    WHERE (launcher IS NULL OR launcher = '')
                      AND terminal_backend IS NOT NULL
                    """
                )
            )
        if "acceptance_criteria" in task_columns:
            conn.execute(
                text(
                    """
                    UPDATE tasks
                    SET acceptance_criteria = '[]'
                    WHERE acceptance_criteria IS NULL
                    """
                )
            )
        conn.execute(
            text(
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
        )
        conn.execute(
            text(
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
        )
        conn.execute(text("UPDATE tasks SET review_approved = 0 WHERE review_approved IS NULL"))
        conn.execute(text("UPDATE tasks SET scratchpad = '' WHERE scratchpad IS NULL"))


def _backfill_worktrees(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = _table_names(inspector)
    columns = _column_names(inspector, "worktrees")
    if not columns:
        return

    with engine.begin() as conn:
        if "path" in columns:
            conn.execute(
                text(
                    """
                    UPDATE worktrees
                    SET worktree_path = path
                    WHERE (worktree_path IS NULL OR worktree_path = '')
                      AND path IS NOT NULL
                    """
                )
            )
        if "workspace_repos" in tables:
            conn.execute(
                text(
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
            )
            conn.execute(
                text(
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
            )
        if "project_id" in columns:
            conn.execute(
                text(
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
            )
        conn.execute(
            text(
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
        )
        conn.execute(
            text(
                """
                DELETE FROM worktrees
                WHERE task_id IS NULL
                   OR repo_id IS NULL
                   OR worktree_path IS NULL
                   OR worktree_path = ''
                """
            )
        )


def _backfill_sessions(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = _column_names(inspector, "sessions")
    if not columns:
        return

    with engine.begin() as conn:
        if "workspace_id" in columns:
            conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET task_id = (
                        SELECT w.task_id
                        FROM worktrees AS w
                        WHERE w.id = sessions.workspace_id
                        LIMIT 1
                    )
                    WHERE task_id IS NULL
                    """
                )
            )
        if "session_type" in columns:
            conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET mode = CASE UPPER(COALESCE(session_type, ''))
                        WHEN 'ACP' THEN 'AUTO'
                        ELSE 'PAIR'
                    END
                    WHERE session_type IS NOT NULL AND session_type != ''
                    """
                )
            )
        conn.execute(
            text(
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
        )
        conn.execute(
            text(
                """
                UPDATE sessions
                SET mode = 'PAIR'
                WHERE mode IS NULL OR mode = ''
                """
            )
        )
        conn.execute(
            text(
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
        )
        conn.execute(
            text(
                """
                UPDATE sessions
                SET agent_backend = 'codex'
                WHERE agent_backend IS NULL OR agent_backend = ''
                """
            )
        )
        conn.execute(
            text(
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
        )
        conn.execute(
            text(
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
        )
        conn.execute(text("DELETE FROM sessions WHERE task_id IS NULL"))


def _apply_schema_migrations(engine: Engine) -> None:
    _ensure_required_columns(engine)
    _backfill_repos(engine)
    _promote_legacy_workspaces(engine)
    _backfill_tasks(engine)
    _backfill_worktrees(engine)
    _backfill_sessions(engine)


def default_db_path() -> Path:
    """Return the default database path, respecting XDG and KAGAN_DATA_DIR overrides."""
    kagan_override = os.environ.get("KAGAN_DATA_DIR")
    if kagan_override:
        return Path(kagan_override) / "kagan.db"
    from platformdirs import user_data_dir

    return Path(user_data_dir("kagan", "kagan")) / "kagan.db"


def create_db_engine(db_path: str | Path | None = None) -> Engine:
    """Create a sync SQLModel engine with WAL mode, FK enforcement, and all tables."""
    resolved = str(db_path) if db_path is not None else str(default_db_path())
    logger.debug("Using database path: {}", resolved)

    if resolved != ":memory:":
        db_file = Path(resolved)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        url = f"sqlite:///{db_file}"
    else:
        url = "sqlite:///:memory:"

    engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    _apply_schema_migrations(engine)

    logger.debug("Database engine created, tables ensured")
    return engine


def get_db_version(engine: Engine) -> int:
    """Return SQLite data_version — increments on every write transaction from any connection."""
    with engine.connect() as conn:
        if isinstance(value := conn.exec_driver_sql("PRAGMA data_version").scalar(), int):
            return value
    if value is None:
        raise RuntimeError("SQLite PRAGMA data_version returned no value")
    return int(value)


__all__ = ["create_db_engine", "default_db_path", "get_db_version"]
