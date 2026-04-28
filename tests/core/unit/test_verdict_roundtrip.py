"""Unit tests for AcceptanceCriterion + ReviewVerdict table model."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kagan.core._db import create_db_engine
from kagan.core._db_helpers import _db_sync
from kagan.core._reviews import (
    approve_review,
    clear_review_verdicts,
    is_review_approved,
)
from kagan.core.models import (
    AcceptanceCriterion,
    Project,
    Repository,
    ReviewVerdict,
    Task,
)

pytestmark = [pytest.mark.core]


def _make_engine(tmp_path: Path):
    return create_db_engine(tmp_path / "test.db")


def _seed_task_with_criteria(engine, criteria_texts: list[str]) -> tuple[str, list[str]]:
    """Seed a Task with AcceptanceCriterion rows. Returns (task_id, [criterion_id, ...])."""

    def op(s) -> tuple[str, list[str]]:
        project = Project(name="Verdict Test Project")
        s.add(project)
        s.flush()

        repo = Repository(
            project_id=project.id,
            name="repo",
            path=f"/tmp/verdict-repo-{project.id}",
        )
        s.add(repo)
        s.flush()

        task = Task(
            project_id=project.id,
            repo_id=repo.id,
            title="Verdict Task",
            status="REVIEW",
            priority=1,
        )
        s.add(task)
        s.flush()

        crit_ids = []
        for ordinal, text in enumerate(criteria_texts):
            crit = AcceptanceCriterion(task_id=task.id, ordinal=ordinal, text=text)
            s.add(crit)
            s.flush()
            crit_ids.append(crit.id)

        s.commit()
        return task.id, crit_ids

    return _db_sync(engine, op)


def _add_verdict(engine, criterion_id: str, verdict: str, reason: str = "") -> None:
    def op(s):
        v = ReviewVerdict(
            criterion_id=criterion_id,
            session_id=None,
            verdict=verdict,
            reason=reason,
        )
        s.add(v)
        s.commit()

    _db_sync(engine, op)


def _fake_client(engine) -> SimpleNamespace:
    """Minimal fake KaganCore that satisfies the 'client' parameter contract."""

    async def _get_task(task_id: str) -> Task:
        def op(s):
            return s.get(Task, task_id)

        return _db_sync(engine, op)

    tasks_ns = SimpleNamespace(get=_get_task)
    return SimpleNamespace(tasks=tasks_ns)


def test_no_criteria_is_not_approved(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id, _ = _seed_task_with_criteria(engine, [])
    assert is_review_approved(task_id, engine) is False
    engine.dispose()


def test_all_pass_criteria_is_approved(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id, crit_ids = _seed_task_with_criteria(engine, ["Tests pass", "No regressions"])
    for cid in crit_ids:
        _add_verdict(engine, cid, "pass")
    assert is_review_approved(task_id, engine) is True
    engine.dispose()


def test_any_fail_is_not_approved(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id, crit_ids = _seed_task_with_criteria(engine, ["Tests pass", "No regressions"])
    _add_verdict(engine, crit_ids[0], "pass")
    _add_verdict(engine, crit_ids[1], "fail")
    assert is_review_approved(task_id, engine) is False
    engine.dispose()


def test_missing_verdict_for_criterion_is_not_approved(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id, crit_ids = _seed_task_with_criteria(engine, ["Tests pass", "No regressions"])
    # Only verdict on first criterion
    _add_verdict(engine, crit_ids[0], "pass")
    assert is_review_approved(task_id, engine) is False
    engine.dispose()


def test_latest_verdict_wins(tmp_path: Path) -> None:
    """If a criterion has multiple verdicts, the last one (by id) wins."""
    engine = _make_engine(tmp_path)
    task_id, crit_ids = _seed_task_with_criteria(engine, ["Must pass"])
    # First verdict: fail
    _add_verdict(engine, crit_ids[0], "fail", "initial review: bad")
    assert is_review_approved(task_id, engine) is False
    # Second verdict: pass (overwrites)
    _add_verdict(engine, crit_ids[0], "pass", "re-review: fixed")
    assert is_review_approved(task_id, engine) is True
    engine.dispose()


def test_skip_verdict_is_not_approved(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id, crit_ids = _seed_task_with_criteria(engine, ["Tests pass"])
    _add_verdict(engine, crit_ids[0], "skip")
    assert is_review_approved(task_id, engine) is False
    engine.dispose()


# ── approve_review ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_review_with_zero_criteria_is_noop(tmp_path: Path) -> None:
    """A task with no acceptance criteria cannot be approved; approve_review
    should not raise but is_review_approved must continue to return False
    so callers cannot accidentally treat the empty case as success."""
    engine = _make_engine(tmp_path)
    task_id, _ = _seed_task_with_criteria(engine, [])
    client = _fake_client(engine)
    await approve_review(engine, task_id, client=client)
    # No verdicts inserted, no criteria → still not approved.
    assert is_review_approved(task_id, engine) is False

    def _count(s):
        return len(list(s.exec(_select_all_verdicts()).all()))

    assert _db_sync(engine, _count) == 0
    engine.dispose()


@pytest.mark.asyncio
async def test_approve_review_stamps_pass_on_all_criteria(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id, _ = _seed_task_with_criteria(engine, ["A", "B"])
    client = _fake_client(engine)
    await approve_review(engine, task_id, client=client)
    assert is_review_approved(task_id, engine) is True
    engine.dispose()


@pytest.mark.asyncio
async def test_approve_review_returns_post_write_task(tmp_path: Path) -> None:
    """approve_review must return the task object *after* verdicts are committed,
    so callers can rely on is_review_approved being True when they inspect the
    returned task's criteria state via a fresh DB read."""
    engine = _make_engine(tmp_path)
    task_id, _ = _seed_task_with_criteria(engine, ["A", "B"])
    client = _fake_client(engine)
    returned_task = await approve_review(engine, task_id, client=client)
    # The returned task must be the post-write object; verify via round-trip.
    assert returned_task.id == task_id
    assert is_review_approved(task_id, engine) is True
    engine.dispose()


@pytest.mark.asyncio
async def test_approve_review_is_idempotent(tmp_path: Path) -> None:
    """Re-running approve_review when latest verdicts are already pass
    should not insert duplicate rows."""
    engine = _make_engine(tmp_path)
    task_id, _ = _seed_task_with_criteria(engine, ["A", "B"])

    client = _fake_client(engine)
    await approve_review(engine, task_id, client=client)
    await approve_review(engine, task_id, client=client)

    def _count(s):
        return len(list(s.exec(_select_all_verdicts()).all()))

    assert _db_sync(engine, _count) == 2
    engine.dispose()


@pytest.mark.asyncio
async def test_clear_review_verdicts_round_trip(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    task_id, _ = _seed_task_with_criteria(engine, ["A"])
    client = _fake_client(engine)
    await approve_review(engine, task_id, client=client)
    assert is_review_approved(task_id, engine) is True
    await clear_review_verdicts(engine, task_id, client=client)
    assert is_review_approved(task_id, engine) is False
    engine.dispose()


def _select_all_verdicts():
    from sqlmodel import select

    return select(ReviewVerdict)
