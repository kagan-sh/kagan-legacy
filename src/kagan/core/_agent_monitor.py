"""Agent post-run evaluation — review readiness, post-agent status resolution."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from loguru import logger
from sqlalchemy import Engine
from sqlmodel import select

from kagan.core import git
from kagan.core._db_helpers import _db_async
from kagan.core._events import Events
from kagan.core.enums import (
    BranchRefStrategy,
    SessionEventType,
    TaskStatus,
)
from kagan.core.errors import WorktreeError
from kagan.core.models import Repository, Setting, Task, Worktree


async def evaluate_review_readiness(
    *,
    task_id: str,
    worktree: Path,
    base_branch: str,
    commit_message: str,
    strategy: BranchRefStrategy = BranchRefStrategy.LOCAL_IF_AHEAD,
) -> tuple[bool, bool, bool]:
    pending_before = False
    pending_after = False

    try:
        pending_before = await git.has_pending_changes(worktree)
    except WorktreeError as exc:
        logger.warning("Pending-change check failed for task={}: {}", task_id, exc)
        return False, True, True

    if pending_before:
        try:
            await git.commit_all(worktree, commit_message)
            logger.info("Auto-committed pending changes for task={}", task_id)
        except WorktreeError as exc:
            logger.warning("Auto-commit failed for task={}: {}", task_id, exc)

    try:
        pending_after = await git.has_pending_changes(worktree)
    except WorktreeError as exc:
        logger.warning("Post-commit pending check failed for task={}: {}", task_id, exc)
        pending_after = True

    has_commits = True
    try:
        has_commits = await git.has_commits_since(worktree, base_branch, strategy=strategy)
    except WorktreeError as exc:
        logger.warning(
            "Commit check failed for task={}, assuming commits exist: {}",
            task_id,
            exc,
        )

    ready_for_review = has_commits and not pending_after
    return ready_for_review, pending_before, pending_after


async def resolve_post_agent_status(
    task_id: str,
    engine: Engine,
    get_task: Callable[[str], Awaitable[Task]],
) -> TaskStatus:
    ws = await _db_async(
        engine,
        lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
    )
    if ws is None:
        logger.debug("No workspace for task={}, falling back to BACKLOG", task_id)
        return TaskStatus.BACKLOG

    worktree = Path(ws.worktree_path)
    if not worktree.exists():
        logger.debug("Worktree missing for task={}, falling back to BACKLOG", task_id)
        return TaskStatus.BACKLOG

    repo = await _db_async(
        engine,
        lambda s, repo_id=ws.repo_id: s.get(Repository, repo_id),
    )
    base_branch = (await get_task(task_id)).base_branch or (
        repo.default_branch if repo else "main"
    )

    short_id = task_id[:8]
    strategy = await ref_strategy(engine)
    ready_for_review, pending_before, pending_after = await evaluate_review_readiness(
        task_id=task_id,
        worktree=worktree,
        base_branch=base_branch,
        commit_message=f"chore: finalize detached run changes ({short_id})",
        strategy=strategy,
    )
    if ready_for_review:
        return TaskStatus.REVIEW

    if pending_before or pending_after:
        logger.info("Pending changes remain for task={}, staying IN_PROGRESS", task_id)
        return TaskStatus.IN_PROGRESS

    logger.info("No commits found for task={}, moving to BACKLOG", task_id)
    return TaskStatus.BACKLOG


async def rebase_if_enabled(
    task_id: str,
    engine: Engine,
    get_task: Callable[[str], Awaitable[Task]],
    events: Events,
    *,
    strategy: BranchRefStrategy | None = None,
) -> None:
    if strategy is None:
        strategy = await ref_strategy(engine)
    if strategy != BranchRefStrategy.LOCAL_IF_AHEAD:
        return

    ws = await _db_async(
        engine,
        lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
    )
    if ws is None:
        return

    task = await get_task(task_id)
    repo = await _db_async(
        engine,
        lambda s, repo_id=ws.repo_id: s.get(Repository, repo_id),
    )
    target_branch = task.base_branch or (repo.default_branch if repo else "main")

    try:
        await git.rebase(ws.worktree_path, target_branch=target_branch)
        logger.debug("Rebased task={} onto latest {}", task_id, target_branch)
    except WorktreeError as exc:
        # Log but don't fail - let the agent handle conflicts if they occur
        logger.warning("Rebase failed for task={}: {}", task_id, exc)
        await events.emit(
            task_id,
            SessionEventType.PLAN_UPDATE,
            {
                "op": "rebase",
                "status": "failed",
                "target_branch": target_branch,
                "error": str(exc),
            },
        )


async def ref_strategy(engine: Engine) -> BranchRefStrategy:
    """Read the configured branch-ref resolution strategy from settings."""
    settings = await _db_async(
        engine,
        lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
    )
    value = settings.get("worktree_base_ref_strategy", "local_if_ahead")
    try:
        return BranchRefStrategy(value)
    except ValueError:
        return BranchRefStrategy.LOCAL_IF_AHEAD


__all__ = [
    "evaluate_review_readiness",
    "rebase_if_enabled",
    "ref_strategy",
    "resolve_post_agent_status",
]
