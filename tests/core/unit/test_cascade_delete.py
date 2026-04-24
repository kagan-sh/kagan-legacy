"""Unit tests for CASCADE FK deletes (honest review gate migration)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from kagan.core._db import create_db_engine
from kagan.core._db_helpers import _db_sync
from kagan.core.enums import SessionEventType
from kagan.core.models import (
    AcceptanceCriterion,
    Project,
    Repository,
    ReviewVerdict,
    Session,
    SessionEvent,
    Task,
    TaskNote,
    Worktree,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.core]


def _make_engine(tmp_path: Path):
    return create_db_engine(tmp_path / "test.db")


def _seed_full_task(engine) -> str:
    """Create a task with session, worktree, events, notes, criteria, verdicts."""

    def op(s) -> str:
        project = Project(name="Cascade Test Project")
        s.add(project)
        s.flush()

        repo = Repository(
            project_id=project.id,
            name="repo",
            path=f"/tmp/cascade-repo-{project.id}",
        )
        s.add(repo)
        s.flush()

        task = Task(
            project_id=project.id,
            repo_id=repo.id,
            title="Cascade Task",
            status="BACKLOG",
            priority=1,
        )
        s.add(task)
        s.flush()

        session = Session(
            task_id=task.id,
            agent_backend="codex",
            status="COMPLETED",
        )
        s.add(session)
        s.flush()

        worktree = Worktree(
            task_id=task.id,
            repo_id=repo.id,
            worktree_path="/tmp/cascade-wt",
            branch_name="kagan/cascade-test",
        )
        s.add(worktree)

        event = SessionEvent(
            task_id=task.id,
            session_id=session.id,
            event_type=SessionEventType.AGENT_COMPLETED,
            payload={},
        )
        s.add(event)

        note = TaskNote(task_id=task.id, content="test note")
        s.add(note)

        criterion = AcceptanceCriterion(task_id=task.id, ordinal=0, text="Tests pass")
        s.add(criterion)
        s.flush()

        verdict = ReviewVerdict(
            criterion_id=criterion.id,
            session_id=session.id,
            verdict="pass",
            reason="All green",
        )
        s.add(verdict)
        s.commit()
        return task.id

    return _db_sync(engine, op)


def test_delete_task_cascades_to_all_children(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id = _seed_full_task(engine)

    # Verify rows exist before deletion
    def check_before(s):
        assert s.get(Task, task_id) is not None
        sessions = list(s.exec(select(Session).where(Session.task_id == task_id)).all())
        assert len(sessions) == 1
        worktrees = list(s.exec(select(Worktree).where(Worktree.task_id == task_id)).all())
        assert len(worktrees) == 1
        events = list(s.exec(select(SessionEvent).where(SessionEvent.task_id == task_id)).all())
        assert len(events) == 1
        notes = list(s.exec(select(TaskNote).where(TaskNote.task_id == task_id)).all())
        assert len(notes) == 1
        criteria = list(
            s.exec(select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)).all()
        )
        assert len(criteria) == 1

    _db_sync(engine, check_before)

    # Delete the task
    def delete_task(s):
        task = s.get(Task, task_id)
        assert task is not None
        s.delete(task)
        s.commit()

    _db_sync(engine, delete_task, commit=False)

    # Verify all children are gone
    def check_after(s):
        assert s.get(Task, task_id) is None
        sessions = list(s.exec(select(Session).where(Session.task_id == task_id)).all())
        assert sessions == []
        worktrees = list(s.exec(select(Worktree).where(Worktree.task_id == task_id)).all())
        assert worktrees == []
        events = list(s.exec(select(SessionEvent).where(SessionEvent.task_id == task_id)).all())
        assert events == []
        notes = list(s.exec(select(TaskNote).where(TaskNote.task_id == task_id)).all())
        assert notes == []
        criteria = list(
            s.exec(select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)).all()
        )
        assert criteria == []
        # ReviewVerdicts should also be gone (cascaded via AcceptanceCriterion)
        assert list(s.exec(select(ReviewVerdict)).all()) == []

    _db_sync(engine, check_after)
    engine.dispose()
