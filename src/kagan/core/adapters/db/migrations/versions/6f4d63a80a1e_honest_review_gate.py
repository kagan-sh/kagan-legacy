"""honest review gate

- CASCADE FK deletes on Session, Worktree, SessionEvent, TaskNote → tasks
- CASCADE FK deletes on SessionEvent → sessions, ReviewVerdict → sessions
- New AcceptanceCriterion table (migrates Task.acceptance_criteria JSON)
- New ReviewVerdict table with `created_at` for portable insertion ordering
  (migrates Task.review_verdicts JSON)
- Drop Task.review_approved, Task.review_verdicts, Task.acceptance_criteria
- Drop Task.execution_mode (auto/pair distinction now lives in settings)
- Add Session.fail_reason column
"""

from __future__ import annotations

import json

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "6f4d63a80a1e"
down_revision = "8662c5d2f0ad"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    return sa_inspect(conn).has_table(name)


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:16]


def _recreate_sessions(bind: sa.engine.Connection) -> None:
    """Recreate sessions table with CASCADE FK and drop stale columns.

    We do this via raw SQL because batch_alter_table cannot handle the case
    where existing indexes reference columns we're dropping.
    """
    if not _has_table("sessions"):
        return
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_sessions_mode")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_sessions_selected_backend_reason")
    bind.exec_driver_sql("ALTER TABLE sessions RENAME TO sessions_old")

    bind.exec_driver_sql(
        """
        CREATE TABLE sessions (
            id VARCHAR NOT NULL,
            task_id VARCHAR NOT NULL,
            agent_backend VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            launcher VARCHAR,
            pid INTEGER,
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            persona VARCHAR,
            attempt INTEGER NOT NULL DEFAULT 1,
            input_tokens INTEGER,
            output_tokens INTEGER,
            context_window_used INTEGER,
            context_window_size INTEGER,
            cost_amount FLOAT,
            cost_currency VARCHAR,
            agent_role VARCHAR,
            fail_reason VARCHAR,
            PRIMARY KEY (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
        )
        """
    )

    # Copy data, excluding dropped columns
    has_agent_role = _has_column_in("sessions_old", "agent_role", bind)
    has_task_id = _has_column_in("sessions_old", "task_id", bind)
    agent_role_expr = "agent_role" if has_agent_role else "NULL"

    if has_task_id:
        bind.exec_driver_sql(
            f"""
            INSERT INTO sessions (
                id, task_id, agent_backend, status, launcher, pid,
                started_at, ended_at, persona, attempt,
                input_tokens, output_tokens, context_window_used, context_window_size,
                cost_amount, cost_currency, agent_role, fail_reason
            )
            SELECT
                id, task_id, agent_backend, status, launcher, pid,
                started_at, ended_at, persona,
                COALESCE(attempt, 1),
                input_tokens, output_tokens, context_window_used, context_window_size,
                cost_amount, cost_currency, {agent_role_expr}, NULL
            FROM sessions_old
            WHERE task_id IS NOT NULL
            """
        )
    # If sessions_old has no task_id column (e.g. very old v060 schema stamped
    # as migrated without actually running 0001_v060_to_latest), skip the copy.
    # Any rows without a valid task_id FK would be orphans anyway.
    bind.exec_driver_sql("DROP TABLE sessions_old")
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sessions_task_id ON sessions (task_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions (status)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sessions_agent_role ON sessions (agent_role)"
    )


def _has_column_in(table: str, column: str, bind: sa.engine.Connection) -> bool:
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _recreate_worktrees(bind: sa.engine.Connection) -> None:
    """Recreate worktrees with CASCADE FK on task_id."""
    if not _has_table("worktrees"):
        # worktrees table doesn't exist yet (very old schema) — nothing to migrate.
        return
    bind.exec_driver_sql("ALTER TABLE worktrees RENAME TO worktrees_old")
    bind.exec_driver_sql(
        """
        CREATE TABLE worktrees (
            id VARCHAR NOT NULL,
            task_id VARCHAR NOT NULL,
            repo_id VARCHAR NOT NULL,
            worktree_path TEXT NOT NULL,
            branch_name VARCHAR NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
            FOREIGN KEY (repo_id) REFERENCES repos (id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO worktrees SELECT * FROM worktrees_old
        """
    )
    bind.exec_driver_sql("DROP TABLE worktrees_old")
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_worktrees_task_id ON worktrees (task_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_worktrees_repo_id ON worktrees (repo_id)"
    )


def _recreate_task_events(bind: sa.engine.Connection) -> None:
    """Recreate task_events with CASCADE FK on task_id, SET NULL on session_id."""
    if not _has_table("task_events"):
        return
    bind.exec_driver_sql("ALTER TABLE task_events RENAME TO task_events_old")
    bind.exec_driver_sql(
        """
        CREATE TABLE task_events (
            id VARCHAR NOT NULL,
            task_id VARCHAR NOT NULL,
            session_id VARCHAR,
            event_type VARCHAR NOT NULL,
            payload JSON,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE SET NULL
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO task_events SELECT * FROM task_events_old
        """
    )
    bind.exec_driver_sql("DROP TABLE task_events_old")
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_task_events_task_id ON task_events (task_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_task_events_session_id ON task_events (session_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_task_events_event_type ON task_events (event_type)"
    )


def _recreate_notes(bind: sa.engine.Connection) -> None:
    """Recreate notes with CASCADE FK on task_id."""
    if not _has_table("notes"):
        return
    bind.exec_driver_sql("ALTER TABLE notes RENAME TO notes_old")
    bind.exec_driver_sql(
        """
        CREATE TABLE notes (
            id VARCHAR NOT NULL,
            task_id VARCHAR NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql("INSERT INTO notes SELECT * FROM notes_old")
    bind.exec_driver_sql("DROP TABLE notes_old")
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_notes_task_id ON notes (task_id)"
    )


def _drop_tasks_stale_columns(bind: sa.engine.Connection) -> None:
    """Drop stale columns from tasks using ALTER TABLE DROP COLUMN (SQLite ≥ 3.35).

    This avoids table recreation which would cause SQLite to rewrite FK references
    in all child tables (sessions, worktrees, task_events, notes, acceptance_criteria)
    to point to the renamed 'tasks_old' table.
    """
    stale = {"acceptance_criteria", "review_approved", "review_verdicts", "execution_mode"}
    old_cols = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()}
    for col in stale & old_cols:
        bind.exec_driver_sql(f"ALTER TABLE tasks DROP COLUMN {col}")


def _drop_and_recreate_review_verdicts(bind: sa.engine.Connection) -> None:
    """Drop and recreate review_verdicts, preserving data.

    This is required because SQLite rewrites FK references when a parent table
    is renamed (e.g. sessions → sessions_old in _recreate_sessions). After
    sessions_old is dropped the FK in review_verdicts becomes dangling.
    We fix it by saving the data, dropping, and recreating with correct FKs.
    """
    if not _has_table("review_verdicts"):
        return
    has_created_at = _has_column_in("review_verdicts", "created_at", bind)
    select_cols = (
        "id, criterion_id, session_id, verdict, reason, created_at"
        if has_created_at
        else "id, criterion_id, session_id, verdict, reason, NULL AS created_at"
    )
    saved = bind.exec_driver_sql(
        f"SELECT {select_cols} FROM review_verdicts"
    ).fetchall()
    # Drop indexes and table
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_review_verdicts_session_id")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_review_verdicts_criterion_id")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_review_verdicts_created_at")
    bind.exec_driver_sql("DROP TABLE review_verdicts")
    # Recreate with correct FK references
    bind.exec_driver_sql(
        """
        CREATE TABLE review_verdicts (
            id VARCHAR NOT NULL,
            criterion_id VARCHAR NOT NULL,
            session_id VARCHAR,
            verdict VARCHAR NOT NULL,
            reason VARCHAR NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            FOREIGN KEY (criterion_id) REFERENCES acceptance_criteria (id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_review_verdicts_criterion_id "
        "ON review_verdicts (criterion_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_review_verdicts_session_id "
        "ON review_verdicts (session_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_review_verdicts_created_at "
        "ON review_verdicts (created_at)"
    )
    # Restore saved rows (omit any whose session_id no longer exists; preserve
    # original created_at when present so insertion order survives the rebuild)
    for row_id, criterion_id, session_id, verdict, reason, created_at in saved:
        if session_id is not None:
            exists = bind.exec_driver_sql(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not exists:
                session_id = None
        if created_at is None:
            bind.exec_driver_sql(
                "INSERT INTO review_verdicts "
                "(id, criterion_id, session_id, verdict, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (row_id, criterion_id, session_id, verdict, reason or ""),
            )
        else:
            bind.exec_driver_sql(
                "INSERT INTO review_verdicts "
                "(id, criterion_id, session_id, verdict, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (row_id, criterion_id, session_id, verdict, reason or "", created_at),
            )


def _drop_and_recreate_acceptance_criteria(bind: sa.engine.Connection) -> None:
    """Drop and recreate acceptance_criteria to ensure correct CASCADE FK to tasks.

    Needed because 0001_v060_to_latest may have created this table via
    SQLModel.metadata.create_all before tasks was confirmed stable.
    In practice the tasks FK is not rewritten (tasks is never renamed), but we
    recreate for consistency and to guarantee ON DELETE CASCADE is set.
    """
    if not _has_table("acceptance_criteria"):
        return
    saved = bind.exec_driver_sql(
        "SELECT id, task_id, ordinal, text FROM acceptance_criteria"
    ).fetchall()
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_acceptance_criteria_task_id")
    bind.exec_driver_sql("DROP TABLE acceptance_criteria")
    bind.exec_driver_sql(
        """
        CREATE TABLE acceptance_criteria (
            id VARCHAR NOT NULL,
            task_id VARCHAR NOT NULL,
            ordinal INTEGER NOT NULL DEFAULT 0,
            text VARCHAR(500) NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_acceptance_criteria_task_id "
        "ON acceptance_criteria (task_id)"
    )
    for row_id, task_id, ordinal, text in saved:
        bind.exec_driver_sql(
            "INSERT INTO acceptance_criteria (id, task_id, ordinal, text) "
            "VALUES (?, ?, ?, ?)",
            (row_id, task_id, ordinal or 0, text),
        )


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")

    # Drop any *_old tables left behind by a crashed prior run of this migration.
    # Without this the second attempt dies at "ALTER TABLE X RENAME TO X_old"
    # with "there is already another table or index with this name: X_old".
    for stale in ("sessions_old", "worktrees_old", "task_events_old", "notes_old"):
        bind.exec_driver_sql(f"DROP TABLE IF EXISTS {stale}")

    try:
        # ── 1. Recreate sessions with CASCADE FK + stale column removal ────────
        # NOTE: _recreate_sessions renames sessions → sessions_old. SQLite will
        # auto-rewrite any FK references in pre-existing tables (e.g.
        # review_verdicts created by 0001_v060_to_latest) to point to
        # sessions_old. We fix this in step 6 by dropping and recreating
        # review_verdicts after sessions is properly established.
        _recreate_sessions(bind)

        # ── 2. Recreate worktrees with CASCADE FK on task_id ──────────────────
        _recreate_worktrees(bind)

        # ── 3. Recreate task_events with CASCADE + SET NULL FKs ───────────────
        _recreate_task_events(bind)

        # ── 4. Recreate notes with CASCADE FK on task_id ──────────────────────
        _recreate_notes(bind)

        # ── 5. Ensure acceptance_criteria exists with correct CASCADE FK ───────
        # Drop-and-recreate if already present (0001 may have created it via
        # create_all); otherwise create fresh.
        if _has_table("acceptance_criteria"):
            _drop_and_recreate_acceptance_criteria(bind)
        else:
            bind.exec_driver_sql(
                """
                CREATE TABLE acceptance_criteria (
                    id VARCHAR NOT NULL,
                    task_id VARCHAR NOT NULL,
                    ordinal INTEGER NOT NULL DEFAULT 0,
                    text VARCHAR(500) NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
                )
                """
            )
            bind.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_acceptance_criteria_task_id "
                "ON acceptance_criteria (task_id)"
            )

        # ── 6. Ensure review_verdicts exists with correct CASCADE FKs ─────────
        # Drop-and-recreate if already present (0001 may have created it via
        # create_all, and its session FK will have been rewritten to sessions_old
        # by _recreate_sessions above). Recreating now fixes the dangling FK.
        if _has_table("review_verdicts"):
            _drop_and_recreate_review_verdicts(bind)
        else:
            bind.exec_driver_sql(
                """
                CREATE TABLE review_verdicts (
                    id VARCHAR NOT NULL,
                    criterion_id VARCHAR NOT NULL,
                    session_id VARCHAR,
                    verdict VARCHAR NOT NULL,
                    reason VARCHAR NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    FOREIGN KEY (criterion_id) REFERENCES acceptance_criteria (id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
                """
            )
            bind.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_review_verdicts_criterion_id "
                "ON review_verdicts (criterion_id)"
            )
            bind.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_review_verdicts_session_id "
                "ON review_verdicts (session_id)"
            )
            bind.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_review_verdicts_created_at "
                "ON review_verdicts (created_at)"
            )

        # ── 7. Migrate Task.acceptance_criteria JSON → table rows ──────────────
        if _has_column_in("tasks", "acceptance_criteria", bind):
            rows = bind.exec_driver_sql(
                "SELECT id, acceptance_criteria FROM tasks "
                "WHERE acceptance_criteria IS NOT NULL"
            ).fetchall()
            for task_id, raw in rows:
                try:
                    criteria = (
                        json.loads(raw) if isinstance(raw, str) else (raw or [])
                    )
                except (json.JSONDecodeError, TypeError):
                    criteria = []
                for ordinal, text in enumerate(criteria):
                    if not text or not str(text).strip():
                        continue
                    # Only insert if not already migrated (idempotency)
                    existing = bind.exec_driver_sql(
                        "SELECT 1 FROM acceptance_criteria "
                        "WHERE task_id = ? AND ordinal = ?",
                        (task_id, ordinal),
                    ).fetchone()
                    if existing is None:
                        bind.exec_driver_sql(
                            "INSERT INTO acceptance_criteria "
                            "(id, task_id, ordinal, text) VALUES (?, ?, ?, ?)",
                            (_new_id(), task_id, ordinal, str(text).strip()[:500]),
                        )

        # ── 8. Migrate Task.review_verdicts JSON → table rows ──────────────────
        if _has_column_in("tasks", "review_verdicts", bind):
            rows = bind.exec_driver_sql(
                "SELECT id, review_verdicts FROM tasks "
                "WHERE review_verdicts IS NOT NULL"
            ).fetchall()
            for task_id, raw in rows:
                try:
                    verdicts = (
                        json.loads(raw) if isinstance(raw, str) else (raw or [])
                    )
                except (json.JSONDecodeError, TypeError):
                    verdicts = []
                for v in verdicts:
                    if not isinstance(v, dict):
                        continue
                    criterion_index = v.get("criterion_index")
                    verdict_val = str(v.get("verdict", "")).lower()
                    reason = str(v.get("reason", ""))
                    if criterion_index is None or verdict_val not in (
                        "pass",
                        "fail",
                        "skip",
                    ):
                        continue
                    crit_row = bind.exec_driver_sql(
                        "SELECT id FROM acceptance_criteria "
                        "WHERE task_id = ? AND ordinal = ?",
                        (task_id, criterion_index),
                    ).fetchone()
                    if crit_row is None:
                        continue
                    bind.exec_driver_sql(
                        "INSERT INTO review_verdicts "
                        "(id, criterion_id, session_id, verdict, reason) "
                        "VALUES (?, ?, NULL, ?, ?)",
                        (_new_id(), crit_row[0], verdict_val, reason),
                    )

        # ── 9. Drop stale columns from tasks (ALTER TABLE DROP COLUMN — SQLite ≥ 3.35) ──
        _drop_tasks_stale_columns(bind)

    finally:
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")

    try:
        # Restore data from acceptance_criteria rows → JSON before dropping table.
        # Track ordinals per task so we can map verdicts back to criterion_index.
        task_crit: dict[str, list[str]] = {}
        criterion_to_task_ord: dict[str, tuple[str, int]] = {}
        if _has_table("acceptance_criteria"):
            rows = bind.exec_driver_sql(
                "SELECT id, task_id, ordinal, text FROM acceptance_criteria "
                "ORDER BY task_id, ordinal"
            ).fetchall()
            for crit_id, task_id, ordinal, text in rows:
                task_crit.setdefault(task_id, []).append(text)
                criterion_to_task_ord[crit_id] = (task_id, int(ordinal or 0))

        # Restore review_verdicts → tasks.review_verdicts JSON before dropping the table.
        task_verdicts: dict[str, list[dict[str, object]]] = {}
        if _has_table("review_verdicts"):
            verdict_rows = bind.exec_driver_sql(
                "SELECT criterion_id, verdict, reason FROM review_verdicts"
            ).fetchall()
            for criterion_id, verdict, reason in verdict_rows:
                mapping = criterion_to_task_ord.get(criterion_id)
                if mapping is None:
                    continue
                task_id, ordinal = mapping
                task_verdicts.setdefault(task_id, []).append(
                    {
                        "criterion_index": ordinal,
                        "verdict": verdict,
                        "reason": reason or "",
                    }
                )

        # Drop new tables first (while acceptance_criteria data is still read)
        if _has_table("review_verdicts"):
            op.drop_index(
                op.f("ix_review_verdicts_created_at"), table_name="review_verdicts"
            )
            op.drop_index(
                op.f("ix_review_verdicts_session_id"), table_name="review_verdicts"
            )
            op.drop_index(
                op.f("ix_review_verdicts_criterion_id"), table_name="review_verdicts"
            )
            op.drop_table("review_verdicts")
        if _has_table("acceptance_criteria"):
            op.drop_index(
                op.f("ix_acceptance_criteria_task_id"),
                table_name="acceptance_criteria",
            )
            op.drop_table("acceptance_criteria")

        # Restore stale columns using ADD COLUMN (avoids FK reference rewrite on rename)
        task_cols = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()}
        if "acceptance_criteria" not in task_cols:
            bind.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN acceptance_criteria JSON DEFAULT '[]'"
            )
        if "review_approved" not in task_cols:
            bind.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN review_approved BOOLEAN NOT NULL DEFAULT 0"
            )
        if "review_verdicts" not in task_cols:
            bind.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN review_verdicts JSON DEFAULT '[]'"
            )

        # Backfill acceptance_criteria JSON from the data we read earlier
        for task_id, texts in task_crit.items():
            bind.exec_driver_sql(
                "UPDATE tasks SET acceptance_criteria = ? WHERE id = ?",
                (json.dumps(texts), task_id),
            )

        # Backfill review_verdicts JSON so a downgrade does not silently
        # discard human review history.
        for task_id, verdicts in task_verdicts.items():
            bind.exec_driver_sql(
                "UPDATE tasks SET review_verdicts = ? WHERE id = ?",
                (json.dumps(verdicts), task_id),
            )

    finally:
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")
