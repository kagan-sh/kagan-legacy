import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal, cast

from loguru import logger
from sqlalchemy import Engine

from kagan.core import git
from kagan.core._db_helpers import _db_async, _setting_enabled, _utc_now
from kagan.core._prompts import build_conflict_resolution_feedback
from kagan.core._settings import get_settings
from kagan.core._transitions import validate_merge_move
from kagan.core.enums import SessionEventType, TaskStatus
from kagan.core.errors import (
    MergeConflictError,
    NotFoundError,
    PreflightError,
    SessionError,
    WorktreeError,
)
from kagan.core.models import Repository, ReviewVerdict, Task, Worktree

if TYPE_CHECKING:
    from kagan.core.client import KaganCore

# ── Module-level functions (canonical API) ─────────────────────────


async def approve_review(
    engine: Engine,
    task_id: str,
    *,
    get_task: Callable[[str], Awaitable[Task]],
) -> Task:
    await get_task(task_id)

    def op(s) -> Task:
        db_task = cast("Task | None", s.get(Task, task_id))
        if db_task is None:
            raise NotFoundError("Task", task_id)
        db_task.review_approved = True
        db_task.updated_at = _utc_now()
        s.add(db_task)
        s.commit()
        s.refresh(db_task)
        return db_task

    return await _db_async(engine, op)


async def reject_review(
    engine: Engine,
    task_id: str,
    feedback: str,
    *,
    get_task: Callable[[str], Awaitable[Task]],
    add_note: Callable[[str, str], Awaitable[Any]],
    set_status: Callable[[str, TaskStatus], Task],
    emit_event: Callable[[str, SessionEventType, dict], Awaitable[Any]],
) -> Task:
    task = await get_task(task_id)
    await add_note(task_id, f"Review rejected: {feedback}")
    if task.status == TaskStatus.REVIEW:
        moved = await asyncio.to_thread(set_status, task_id, TaskStatus.IN_PROGRESS)
        await emit_event(
            task_id,
            SessionEventType.TASK_STATUS_CHANGED,
            {"from": TaskStatus.REVIEW.value, "to": TaskStatus.IN_PROGRESS.value},
        )
        return moved
    return task


async def set_criterion_verdict(
    engine: Engine,
    task_id: str,
    criterion_index: int,
    verdict: str,
    reason: str,
    *,
    get_task: Callable[[str], Awaitable[Task]],
    emit_event: Callable[[str, SessionEventType, dict], Awaitable[Any]],
) -> Task:
    allowed = {"PASS", "FAIL"}
    if verdict not in allowed:
        raise ValueError(f"verdict must be one of {sorted(allowed)}, got {verdict!r}")

    verdict_typed = cast('Literal["PASS", "FAIL"]', verdict)

    task = await get_task(task_id)
    criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
    if criterion_index < 0 or criterion_index >= len(criteria):
        raise ValueError(
            f"criterion_index {criterion_index} out of range (task has {len(criteria)} criteria)"
        )

    def op(s) -> Task:
        db_task = cast("Task | None", s.get(Task, task_id))
        if db_task is None:
            raise NotFoundError("Task", task_id)
        verdicts: list[ReviewVerdict] = list(db_task.review_verdicts or [])
        # Replace existing verdict for this index if present
        verdicts = [v for v in verdicts if v["criterion_index"] != criterion_index]
        verdicts.append(
            {
                "criterion_index": criterion_index,
                "verdict": verdict_typed,
                "reason": reason,
            }
        )
        verdicts.sort(key=lambda v: v["criterion_index"])
        db_task.review_verdicts = verdicts
        db_task.updated_at = _utc_now()
        s.add(db_task)
        s.commit()
        s.refresh(db_task)
        return db_task

    updated = await _db_async(engine, op)
    await emit_event(
        task_id,
        SessionEventType.CRITERION_VERDICT,
        {
            "criterion_index": criterion_index,
            "verdict": verdict,
            "reason": reason,
        },
    )
    return updated


async def clear_review_verdicts(
    engine: Engine,
    task_id: str,
    *,
    get_task: Callable[[str], Awaitable[Task]],
) -> Task:
    await get_task(task_id)

    def op(s) -> Task:
        db_task = cast("Task | None", s.get(Task, task_id))
        if db_task is None:
            raise NotFoundError("Task", task_id)
        db_task.review_verdicts = []
        db_task.updated_at = _utc_now()
        s.add(db_task)
        s.commit()
        s.refresh(db_task)
        return db_task

    return await _db_async(engine, op)


async def merge_task(
    engine: Engine,
    task_id: str,
    *,
    get_task: Callable[[str], Awaitable[Task]],
    get_worktree: Callable[[str], Awaitable[Worktree | None]],
    get_repo: Callable[[str], Repository | None],
    cleanup_worktree: Callable[[str], Awaitable[None]],
    set_status: Callable[[str, TaskStatus], Task],
    emit_event: Callable[[str, SessionEventType, dict], Awaitable[Any]],
) -> Task:
    task = await get_task(task_id)
    validate_merge_move(task.status, TaskStatus.DONE)

    ws = await get_worktree(task_id)
    if ws is None:
        raise SessionError(None, f"No workspace for task {task_id!r}.")

    repo = await asyncio.to_thread(get_repo, ws.repo_id)
    if repo is None:
        raise SessionError(None, f"Repository not found for workspace of task {task_id!r}.")

    target_branch = task.base_branch or repo.default_branch
    settings = await get_settings(engine)
    require_review_approval = _setting_enabled(
        settings,
        "require_review_approval",
        default=False,
    )
    if require_review_approval and not task.review_approved:
        error = "Cannot merge task branch: review approval is required."
        await emit_event(
            task_id,
            SessionEventType.MERGE_FAILED,
            {
                "error": error,
                "target_branch": target_branch,
                "requires_review_approval": True,
            },
        )
        raise PreflightError(error)

    has_pending_changes = await git.has_pending_changes(ws.worktree_path)
    if has_pending_changes:
        error = "Cannot merge while workspace has uncommitted or untracked changes."
        await emit_event(
            task_id,
            SessionEventType.MERGE_FAILED,
            {
                "error": error,
                "target_branch": target_branch,
                "pending_changes": True,
            },
        )
        raise PreflightError(error)

    has_commits_to_merge = await git.has_commits_since(ws.worktree_path, target_branch)
    if not has_commits_to_merge:
        error = "Cannot merge task branch: no commits ahead of target branch."
        await emit_event(
            task_id,
            SessionEventType.MERGE_FAILED,
            {
                "error": error,
                "target_branch": target_branch,
                "pending_changes": False,
            },
        )
        raise PreflightError(error)

    short_id = task_id[:8]
    commit_message = f"{task.title} (kagan {short_id})"
    user_name, user_email = await git.get_git_user_identity(settings)
    try:
        squash_sha = await git.merge(
            repo.path,
            branch=ws.branch_name,
            target_branch=target_branch,
            commit_message=commit_message,
            user_name=user_name,
            user_email=user_email,
        )
    except MergeConflictError as exc:
        suggested_feedback = build_conflict_resolution_feedback(
            conflict_files=exc.conflict_files,
            target_branch=target_branch,
            task_title=task.title,
        )
        await emit_event(
            task_id,
            SessionEventType.MERGE_FAILED,
            {
                "error": str(exc),
                "target_branch": target_branch,
                "conflict_files": exc.conflict_files,
                "suggested_feedback": suggested_feedback,
            },
        )
        raise

    await cleanup_worktree(task_id)

    done_task = await asyncio.to_thread(set_status, task_id, TaskStatus.DONE)
    await emit_event(
        task_id,
        SessionEventType.TASK_STATUS_CHANGED,
        {"from": task.status.value, "to": TaskStatus.DONE.value},
    )
    await emit_event(
        task_id,
        SessionEventType.MERGE_COMPLETED,
        {
            "target_branch": target_branch,
            "merged_branch": ws.branch_name,
            "commit_sha": squash_sha,
        },
    )
    logger.info("Merge completed for task={}", task_id)
    return done_task


async def rebase_task(
    engine: Engine,
    task_id: str,
    *,
    get_task: Callable[[str], Awaitable[Task]],
    get_worktree: Callable[[str], Awaitable[Worktree | None]],
    get_repo: Callable[[str], Repository | None],
    emit_event: Callable[[str, SessionEventType, dict], Awaitable[Any]],
) -> None:
    ws = await get_worktree(task_id)
    if ws is None:
        raise SessionError(None, f"No workspace for task {task_id!r}.")
    task = await get_task(task_id)
    repo = await asyncio.to_thread(get_repo, ws.repo_id)
    target = task.base_branch or (repo.default_branch if repo else "main")
    try:
        await git.rebase(ws.worktree_path, target_branch=target)
    except WorktreeError as exc:
        await emit_event(
            task_id,
            SessionEventType.AGENT_FAILED,
            {
                "op": "rebase",
                "error": str(exc),
                "target_branch": target,
                "conflict_files": await git.get_conflicted_files(ws.worktree_path),
            },
        )
        raise

    await emit_event(
        task_id,
        SessionEventType.PLAN_UPDATE,
        {"op": "rebase", "status": "completed", "target_branch": target},
    )


async def continue_rebase(
    engine: Engine,
    task_id: str,
    *,
    get_worktree: Callable[[str], Awaitable[Worktree | None]],
) -> None:
    ws = await get_worktree(task_id)
    if ws is None:
        raise SessionError(None, f"No workspace for task {task_id!r}.")
    await git.continue_rebase(ws.worktree_path)


async def get_conflicts(
    engine: Engine,
    task_id: str,
    *,
    get_worktree: Callable[[str], Awaitable[Worktree | None]],
) -> dict[str, Any]:
    ws = await get_worktree(task_id)
    if ws is None:
        return {
            "task_id": task_id,
            "has_workspace": False,
            "is_rebase_in_progress": False,
            "conflict_op": None,
            "conflicted_files": [],
        }
    return {
        "task_id": task_id,
        "has_workspace": True,
        "is_rebase_in_progress": await git.is_rebase_in_progress(ws.worktree_path),
        "conflict_op": await git.detect_conflict_op(ws.worktree_path),
        "conflicted_files": await git.get_conflicted_files(ws.worktree_path),
    }


async def abort_rebase(
    engine: Engine,
    task_id: str,
    *,
    get_worktree: Callable[[str], Awaitable[Worktree | None]],
) -> None:
    ws = await get_worktree(task_id)
    if ws is None:
        return
    await git.abort_rebase(ws.worktree_path)


# ── Class wrapper (backward compat) ───────────────────────────────


class Reviews:
    def __init__(self, engine: Engine, client: "KaganCore") -> None:
        self._engine = engine
        self._client = client

    async def approve(self, task_id: str) -> Task:
        return await approve_review(
            self._engine,
            task_id,
            get_task=self._client.tasks.get,
        )

    async def reject(self, task_id: str, *, feedback: str) -> Task:
        return await reject_review(
            self._engine,
            task_id,
            feedback,
            get_task=self._client.tasks.get,
            add_note=self._client.tasks.add_note,
            set_status=self._client.tasks._set_status,
            emit_event=self._client.tasks.events.emit,
        )

    async def set_criterion_verdict(
        self,
        task_id: str,
        criterion_index: int,
        verdict: str,
        reason: str,
    ) -> Task:
        return await set_criterion_verdict(
            self._engine,
            task_id,
            criterion_index,
            verdict,
            reason,
            get_task=self._client.tasks.get,
            emit_event=self._client.tasks.events.emit,
        )

    async def clear_verdicts(self, task_id: str) -> Task:
        return await clear_review_verdicts(
            self._engine,
            task_id,
            get_task=self._client.tasks.get,
        )

    async def merge(self, task_id: str) -> Task:
        return await merge_task(
            self._engine,
            task_id,
            get_task=self._client.tasks.get,
            get_worktree=self._client.worktrees.get,
            get_repo=self._client.worktrees._get_repo,
            cleanup_worktree=self._client.worktrees.cleanup,
            set_status=self._client.tasks._set_status,
            emit_event=self._client.tasks.events.emit,
        )

    async def rebase(self, task_id: str) -> None:
        await rebase_task(
            self._engine,
            task_id,
            get_task=self._client.tasks.get,
            get_worktree=self._client.worktrees.get,
            get_repo=self._client.worktrees._get_repo,
            emit_event=self._client.tasks.events.emit,
        )

    async def continue_rebase(self, task_id: str) -> None:
        await continue_rebase(
            self._engine,
            task_id,
            get_worktree=self._client.worktrees.get,
        )

    async def conflicts(self, task_id: str) -> dict[str, Any]:
        return await get_conflicts(
            self._engine,
            task_id,
            get_worktree=self._client.worktrees.get,
        )

    async def abort_rebase(self, task_id: str) -> None:
        await abort_rebase(
            self._engine,
            task_id,
            get_worktree=self._client.worktrees.get,
        )


__all__ = [
    "Reviews",
    "abort_rebase",
    "approve_review",
    "clear_review_verdicts",
    "continue_rebase",
    "get_conflicts",
    "merge_task",
    "rebase_task",
    "reject_review",
    "set_criterion_verdict",
]
