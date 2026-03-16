import asyncio
import sqlite3
from pathlib import Path

import pytest

from kagan.core import KaganCore

pytestmark = [pytest.mark.core]


def _seed_v060_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE repos (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT UNIQUE,
                display_name TEXT,
                default_working_dir TEXT,
                default_branch TEXT,
                scripts TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE project_repos (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                repo_id TEXT,
                is_primary INTEGER,
                display_order INTEGER,
                created_at TEXT
            );

            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                parent_id TEXT,
                title TEXT,
                description TEXT,
                status TEXT,
                priority INTEGER,
                task_type TEXT,
                terminal_backend TEXT,
                agent_backend TEXT,
                base_branch TEXT,
                acceptance_criteria TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE workspaces (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                task_id TEXT,
                branch_name TEXT,
                path TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE workspace_repos (
                id TEXT PRIMARY KEY,
                workspace_id TEXT,
                repo_id TEXT,
                target_branch TEXT,
                worktree_path TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                workspace_id TEXT,
                session_type TEXT,
                status TEXT,
                external_id TEXT,
                started_at TEXT,
                ended_at TEXT
            );
            """
        )

        conn.execute(
            (
                "INSERT INTO projects (id, name, description, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)"
            ),
            ("proj0001", "Legacy Project", "", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO repos (id, name, path, default_branch, scripts, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "repo0001",
                "legacy-repo",
                "/tmp/legacy-repo",
                "main",
                "{}",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.execute(
            (
                "INSERT INTO project_repos (id, project_id, repo_id, is_primary,"
                " display_order, created_at) VALUES (?, ?, ?, ?, ?, ?)"
            ),
            ("pr000001", "proj0001", "repo0001", 1, 0, "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            (
                "INSERT INTO tasks ("
                "id, project_id, title, description, status, priority, task_type,"
                " terminal_backend, agent_backend, base_branch, acceptance_criteria, created_at,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "task0001",
                "proj0001",
                "Legacy Task",
                "",
                "IN_PROGRESS",
                1,
                "AUTO",
                "cursor",
                None,
                "main",
                "[]",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.execute(
            (
                "INSERT INTO workspaces (id, project_id, task_id, branch_name, path, status,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "ws000001",
                "proj0001",
                "task0001",
                "kagan/task0001",
                "/tmp/legacy-worktree",
                "ACTIVE",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO workspace_repos (id, workspace_id, repo_id, target_branch, worktree_path,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "wr000001",
                "ws000001",
                "repo0001",
                "main",
                "/tmp/legacy-worktree",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.execute(
            (
                "INSERT INTO sessions (id, workspace_id, session_type, status, external_id,"
                " started_at, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "sess0001",
                "ws000001",
                "ACP",
                "ACTIVE",
                "legacy-external-id",
                "2026-01-01T00:00:00Z",
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_v060_schema_is_upgraded_without_runtime_breakage(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _seed_v060_schema(db_path)

    client = KaganCore(db_path=db_path)
    try:
        conn = sqlite3.connect(db_path)
        try:
            task_row = conn.execute(
                "SELECT execution_mode, launcher, review_approved FROM tasks WHERE id = ?",
                ("task0001",),
            ).fetchone()
            assert task_row == ("AUTO", "cursor", 0)

            task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            assert "scratchpad" not in task_columns

            repo_row = conn.execute(
                "SELECT project_id FROM repos WHERE id = ?", ("repo0001",)
            ).fetchone()
            assert repo_row == ("proj0001",)

            worktree_row = conn.execute(
                "SELECT repo_id, worktree_path FROM worktrees WHERE id = ?",
                ("ws000001",),
            ).fetchone()
            assert worktree_row == ("repo0001", "/tmp/legacy-worktree")

            session_row = conn.execute(
                "SELECT task_id, mode, status, agent_backend FROM sessions WHERE id = ?",
                ("sess0001",),
            ).fetchone()
            assert session_row == ("task0001", "AUTO", "RUNNING", "codex")
        finally:
            conn.close()

        async def run_smoke() -> None:
            await client.projects.set_active("proj0001")
            tasks = await client.tasks.list()
            assert [task.id for task in tasks] == ["task0001"]
            worktree = await client.worktrees.get("task0001")
            assert worktree is not None
            assert worktree.repo_id == "repo0001"

        asyncio.run(run_smoke())
    finally:
        client.close()


def test_migration_is_idempotent_for_repeated_startup(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-idempotent.db"
    _seed_v060_schema(db_path)

    first = KaganCore(db_path=db_path)
    first.close()

    second = KaganCore(db_path=db_path)
    try:
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE task_id = ?", ("task0001",)
            ).fetchone()
            assert count == (1,)
        finally:
            conn.close()
    finally:
        second.close()


def test_legacy_orphans_are_pruned_without_startup_crash(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-orphans.db"
    _seed_v060_schema(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE workspaces SET task_id = NULL WHERE id = ?", ("ws000001",))
        conn.commit()
    finally:
        conn.close()

    client = KaganCore(db_path=db_path)
    try:
        conn = sqlite3.connect(db_path)
        try:
            worktree_count = conn.execute("SELECT COUNT(*) FROM worktrees").fetchone()
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            assert worktree_count == (0,)
            assert session_count == (0,)
        finally:
            conn.close()

        async def run_smoke() -> None:
            await client.projects.set_active("proj0001")
            tasks = await client.tasks.list()
            assert [task.id for task in tasks] == ["task0001"]

        asyncio.run(run_smoke())
    finally:
        client.close()


def test_known_legacy_alembic_revision_is_remapped_to_head(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-known-rev.db"
    _seed_v060_schema(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", ("5b95758fdb4d",))
        conn.commit()
    finally:
        conn.close()

    client = KaganCore(db_path=db_path)
    try:
        conn = sqlite3.connect(db_path)
        try:
            head = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            assert head == ("df51db972cd5",)
        finally:
            conn.close()
    finally:
        client.close()


def test_unknown_alembic_revision_fails_with_explicit_message(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-unknown-rev.db"
    _seed_v060_schema(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", ("deadbeefdead",))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(RuntimeError, match="Unknown alembic revision 'deadbeefdead'"):
        KaganCore(db_path=db_path)
