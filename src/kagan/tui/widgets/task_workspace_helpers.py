from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from kagan.core import git
from kagan.core.enums import SessionEventType, TaskStatus
from kagan.core.errors import KaganError, SessionError, WorktreeError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kagan.core.models import Task
    from kagan.tui.widgets.task_diff_pane import TaskDiffPane

type MergedDiffFallback = tuple[str, dict[str, int], str, str, str]


def changed_files(diff_text: str) -> list[str]:
    return git.parse_diff_changed_files(diff_text)


def diff_totals(diff_text: str) -> tuple[int, int, int]:
    return git.parse_diff_totals(diff_text)


def workspace_snapshot_text(
    worktree_path: str,
    files: list[str],
    stats: dict[str, Any],
) -> str:
    n_files = int(stats.get("files", 0))
    ins = int(stats.get("insertions", 0))
    dels = int(stats.get("deletions", 0))
    return f"Workspace · {n_files} files · +{ins} / -{dels} · {len(files)} changed\n{worktree_path}"


def merged_snapshot_text(
    repo_path: str,
    short_sha: str,
    target_branch: str,
    files: list[str],
    stats: dict[str, Any],
) -> str:
    n_files = int(stats.get("files", 0))
    ins = int(stats.get("insertions", 0))
    dels = int(stats.get("deletions", 0))
    return (
        f"Merged {short_sha} -> {target_branch} · {n_files} files · +{ins} / -{dels} · "
        f"{len(files)} changed\n{repo_path}"
    )


async def merged_commit_diff_fallback(
    *,
    task_id: str,
    task: Task | None,
    get_task: Callable[[str], Awaitable[Task]],
    latest_merge_event: Callable[[str], Awaitable[Any]],
    resolve_repo_path: Callable[[str], Awaitable[tuple[str | None, str]]],
) -> MergedDiffFallback | None:
    current_task = task
    if current_task is None:
        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
            current_task = await get_task(task_id)
    if current_task is None or current_task.status is not TaskStatus.DONE:
        return None

    merge_event = await latest_merge_event(task_id)
    if merge_event is None:
        return None

    payload = merge_event.payload or {}
    commit_sha = str(payload.get("commit_sha") or "").strip()
    if not commit_sha:
        return None

    repo_path, default_branch = await resolve_repo_path(current_task.project_id)
    if repo_path is None:
        return None

    diff_text = ""
    with contextlib.suppress(WorktreeError):
        diff_text = await git.show_commit_diff(repo_path, commit_sha=commit_sha)
    if not diff_text.strip():
        return None

    files, insertions, deletions = diff_totals(diff_text)
    target_branch = str(
        payload.get("target_branch") or current_task.base_branch or default_branch or "main"
    )
    target_branch = target_branch.strip() or "main"
    return (
        diff_text,
        {"files": files, "insertions": insertions, "deletions": deletions},
        repo_path,
        commit_sha[:8],
        target_branch,
    )


async def hydrate_workspace_panels(
    *,
    task_id: str | None,
    active_tab: str,
    diff_pane: TaskDiffPane,
    get_workspace: Callable[[str], Awaitable[Any]],
    get_workspace_diff: Callable[[str], Awaitable[str]],
    get_workspace_stats: Callable[[str], Awaitable[dict[str, Any]]],
    resolve_merged_fallback: Callable[[], Awaitable[MergedDiffFallback | None]],
) -> None:
    if task_id is None:
        return

    workspace = await get_workspace(task_id)
    diff_view = diff_pane.get_diff_view()

    if workspace is None:
        merged_fallback = await resolve_merged_fallback()
        if merged_fallback is None:
            diff_pane.update_workspace_bar(
                "No worktree provisioned", loading=False, no_workspace=True
            )
            diff_pane.update_diff("")
            return

        diff_text, stats, repo_path, short_sha, target_branch = merged_fallback
        files = changed_files(diff_text)
        diff_pane.update_workspace_bar(
            merged_snapshot_text(repo_path, short_sha, target_branch, files, stats),
            loading=False,
            no_workspace=False,
        )
        diff_pane.update_diff(diff_text)
        if files:
            diff_view.set_selected_file(files[0])
        return

    diff_text = ""
    with contextlib.suppress(SessionError, WorktreeError):
        diff_text = await get_workspace_diff(task_id)
    stats: dict[str, Any] = {"files": 0, "insertions": 0, "deletions": 0}
    with contextlib.suppress(SessionError, WorktreeError):
        stats = await get_workspace_stats(task_id)

    files = changed_files(diff_text)
    diff_pane.update_workspace_bar(
        workspace_snapshot_text(workspace.worktree_path, files, stats),
        loading=False,
        no_workspace=False,
    )

    if active_tab == "changes":
        selected_path = diff_view.current_file_path()
        diff_pane.update_diff(diff_text)
        if selected_path is not None and selected_path in files:
            diff_view.set_selected_file(selected_path)


async def resolve_latest_merge_event(events_service: Any, task_id: str) -> Any:
    return await events_service.latest(task_id, event_type=SessionEventType.MERGE_COMPLETED)
