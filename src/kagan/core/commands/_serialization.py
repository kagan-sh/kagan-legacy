from __future__ import annotations

import dataclasses
import shlex
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import kagan.core.domain.models as domain_models
from kagan.core.commands._responses import (
    CommandCode,
    invalid_job_id_response,
    invalid_task_id_response,
    job_not_found_response,
)
from kagan.core.commands._transport_truncation import (
    DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
    truncate_for_transport,
)
from kagan.core.scalars import non_empty_str
from kagan.core.services.jobs import JobStatus
from kagan.core.services.runtime import runtime_snapshot_for_task

if TYPE_CHECKING:
    from kagan.core.adapters.db.schema import Project, Task
    from kagan.core.bootstrap import AppContext
    from kagan.core.services.jobs import JobRecord
    from kagan.core.services.runtime import RuntimeSnapshotSource

TMUX_DOCS_URL = "https://github.com/tmux/tmux/wiki"
NVIM_DOCS_URL = "https://neovim.io"
SESSION_PROMPT_PATH = Path(".kagan/start_prompt.md")


def task_to_dict(
    task: Task,
    *,
    runtime_service: RuntimeSnapshotSource | None = None,
) -> dict[str, Any]:
    """Convert a Task domain object to the canonical payload via shared model."""
    from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType

    status = task.status or TaskStatus.BACKLOG
    priority = task.priority or TaskPriority.MEDIUM
    task_type = task.task_type or TaskType.PAIR
    payload = domain_models.Task(
        id=task.id,
        project_id=task.project_id,
        parent_id=task.parent_id,
        title=task.title,
        description=task.description,
        status=status.value,
        priority=priority.value,
        task_type=task_type.value,
        terminal_backend=task.terminal_backend.value if task.terminal_backend else None,
        agent_backend=task.agent_backend,
        acceptance_criteria=list(task.acceptance_criteria),
        base_branch=task.base_branch,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
        runtime=runtime_snapshot_for_task(
            task_id=task.id,
            runtime_service=runtime_service,
        ),
    )
    return payload.model_dump(mode="json", exclude={"short_id"})


def project_to_dict(project: Project) -> dict[str, Any]:
    """Convert a Project domain object to the canonical payload via shared model."""
    payload = domain_models.Project(
        id=project.id,
        name=project.name,
        description=project.description,
        last_opened_at=project.last_opened_at,
    )
    return payload.model_dump(mode="json", exclude_none=True)


def resolve_pair_backend(ctx: AppContext, task: object | None) -> str:
    """Resolve the PAIR terminal backend from task -> config -> default (tmux)."""
    from kagan.core.domain.enums import resolve_pair_backend

    task_backend = getattr(task, "terminal_backend", None)
    config_backend = getattr(ctx.config.general, "default_pair_terminal_backend", None)
    return resolve_pair_backend(task_backend, config_backend)


def build_handoff_payload(
    *,
    task_id: str,
    backend: str,
    session_name: str,
    worktree_path: Path,
    already_exists: bool,
) -> dict[str, Any]:
    """Build the rich handoff dict with terminal commands/links/instructions."""
    worktree_str = str(worktree_path)
    prompt_path = worktree_path / SESSION_PROMPT_PATH
    prompt_str = str(prompt_path)
    quoted_worktree = shlex.quote(worktree_str)
    quoted_prompt = shlex.quote(prompt_str)

    links: dict[str, str] = {
        "worktree_file_url": worktree_path.as_uri(),
        "prompt_file_url": prompt_path.as_uri(),
    }

    if backend == "tmux":
        primary_command = f"tmux attach-session -t {session_name}"
        commands = [
            primary_command,
            "Detach and return to Kagan: Ctrl+b d",
        ]
        links["tmux_docs"] = TMUX_DOCS_URL
        instructions = (
            "Open a terminal and run the attach command. "
            "When finished, detach with Ctrl+b d and continue in Kagan."
        )
    elif backend == "nvim":
        primary_command = f"nvim {quoted_prompt}"
        commands = [
            primary_command,
            "Inside Neovim, use your preferred AI chat: :CodeCompanionChat / :AvanteChat / "
            ":CopilotChat / :ClaudeCode",
        ]
        links["nvim_docs"] = NVIM_DOCS_URL
        instructions = (
            "Open Neovim with the startup prompt file, then paste prompt content into your AI chat "
            "plugin."
        )
    elif backend == "vscode":
        primary_command = f"code --new-window {quoted_worktree} {quoted_prompt}"
        commands = [
            primary_command,
            f"Open startup prompt: cat {quoted_prompt}",
        ]
        links["vscode_prompt_uri"] = f"vscode://file/{quote(prompt_path.as_posix())}"
        instructions = (
            "Open VS Code with the command above, then paste the startup prompt into chat."
        )
    elif backend == "cursor":
        primary_command = f"cursor --new-window {quoted_worktree} {quoted_prompt}"
        commands = [
            primary_command,
            f"Open startup prompt: cat {quoted_prompt}",
        ]
        links["cursor_prompt_uri"] = f"cursor://file/{quote(prompt_path.as_posix())}"
        instructions = (
            "Open Cursor with the command above, then paste the startup prompt into chat."
        )
    else:
        primary_command = f"Open worktree: {worktree_str}"
        commands = [primary_command]
        instructions = "Open the worktree and continue coding in your preferred terminal/editor."

    return {
        "success": True,
        "task_id": task_id,
        "session_name": session_name,
        "backend": backend,
        "already_exists": already_exists,
        "worktree_path": worktree_str,
        "prompt_path": prompt_str,
        "primary_command": primary_command,
        "commands": commands,
        "links": links,
        "instructions": instructions,
        "next_step": "Reply 'ready' when attached so the agent can continue orchestration.",
    }


def parse_requested_worktree(
    *,
    task_id: str,
    raw_worktree: object,
) -> tuple[Path | None, dict[str, Any] | None]:
    if raw_worktree is not None and not isinstance(raw_worktree, str):
        return None, {
            "success": False,
            "task_id": task_id,
            "message": (
                "worktree_path must be a string path. "
                "Omit this parameter to use the default worktree location."
            ),
            "code": "INVALID_WORKTREE_PATH",
        }
    if isinstance(raw_worktree, str) and raw_worktree.strip():
        return Path(raw_worktree.strip()).expanduser().resolve(strict=False), None
    return None, None


def session_create_error_response(task_id: str, exc: Exception) -> dict[str, Any]:
    from kagan.core.api import (
        InvalidWorktreePathError,
        SessionCreateFailedError,
        TaskTypeMismatchError,
        WorkspaceNotFoundError,
    )

    if isinstance(exc, TaskTypeMismatchError):
        from kagan.core.domain.enums import TaskType

        return {
            "success": False,
            "task_id": task_id,
            "message": str(exc),
            "code": "TASK_TYPE_MISMATCH",
            "hint": "Set task_type to PAIR before opening a PAIR session.",
            "next_tool": "task_patch",
            "next_arguments": {
                "task_id": task_id,
                "transition": "set_task_type",
                "set": {"task_type": TaskType.PAIR.value},
            },
            "current_task_type": exc.current_task_type,
        }
    if isinstance(exc, WorkspaceNotFoundError):
        return {
            "success": False,
            "task_id": task_id,
            "message": f"No workspace found for task {task_id}",
            "code": "WORKSPACE_NOT_FOUND",
            "hint": "Create/activate a workspace for this task before creating a PAIR session.",
        }
    if isinstance(exc, InvalidWorktreePathError):
        return {
            "success": False,
            "task_id": task_id,
            "message": str(exc),
            "code": "INVALID_WORKTREE_PATH",
            "hint": "Use session_manage(action='read') to inspect expected worktree_path.",
            "next_tool": "session_manage",
            "next_arguments": {"action": "read", "task_id": task_id},
        }
    if isinstance(exc, SessionCreateFailedError):
        return {
            "success": False,
            "task_id": task_id,
            "message": str(exc),
            "code": "SESSION_CREATE_FAILED",
            "hint": "Confirm workspace path and terminal backend, then retry session_manage(open).",
        }
    msg = f"Unsupported session_create exception: {type(exc).__name__}"
    raise TypeError(msg)


def build_job_response(job: JobRecord, *, timed_out: bool = False) -> dict[str, Any]:
    is_terminal = job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}

    result: dict[str, Any] = {
        "success": True,
        "job_id": job.job_id,
        "task_id": job.task_id,
        "action": job.action,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "message": job.message,
        "code": CommandCode.JOB_TIMEOUT.value if timed_out and not is_terminal else job.code,
        "timed_out": timed_out and not is_terminal,
    }
    if job.result is not None:
        result["result"] = job.result
    return result


def build_audit_list_response(
    events: list[object],
    *,
    field_char_limit: int = DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
) -> dict[str, Any]:
    """Serialize audit events into a transport-safe response envelope."""
    result_events: list[dict[str, Any]] = []
    truncated = False

    for event in events:
        payload_raw = str(getattr(event, "payload_json", "") or "")
        result_raw = str(getattr(event, "result_json", "") or "")
        payload, payload_truncated = truncate_for_transport(payload_raw, limit=field_char_limit)
        result, result_truncated = truncate_for_transport(result_raw, limit=field_char_limit)
        if payload_truncated or result_truncated:
            truncated = True

        occurred_at_raw = getattr(event, "occurred_at", None)
        occurred_at = (
            occurred_at_raw.isoformat()
            if hasattr(occurred_at_raw, "isoformat") and callable(occurred_at_raw.isoformat)
            else None
        )

        result_events.append(
            {
                "id": getattr(event, "id", None),
                "occurred_at": occurred_at,
                "actor_type": getattr(event, "actor_type", None),
                "actor_id": getattr(event, "actor_id", None),
                "session_id": getattr(event, "session_id", None),
                "capability": getattr(event, "capability", None),
                "command_name": getattr(event, "command_name", None),
                "payload_json": payload,
                "result_json": result,
                "success": bool(getattr(event, "success", False)),
            }
        )

    return {"events": result_events, "count": len(result_events), "truncated": truncated}


def _isoformat(value: object) -> str | None:
    if isinstance(value, str):
        return value
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        serialized = isoformat()
        if isinstance(serialized, str):
            return serialized
    return None


def _enum_value(value: object) -> str | None:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, str):
        return value
    return None


def workspace_to_dict(workspace: object) -> dict[str, Any]:
    return {
        "id": str(getattr(workspace, "id", "")),
        "project_id": non_empty_str(getattr(workspace, "project_id", None)),
        "task_id": non_empty_str(getattr(workspace, "task_id", None)),
        "branch_name": str(getattr(workspace, "branch_name", "")),
        "path": str(getattr(workspace, "path", "")),
        "status": _enum_value(getattr(workspace, "status", None)),
        "created_at": _isoformat(getattr(workspace, "created_at", None)),
        "updated_at": _isoformat(getattr(workspace, "updated_at", None)),
    }


def execution_to_dict(execution: object) -> dict[str, Any]:
    payload = domain_models.Execution.model_validate(
        {
            "id": str(getattr(execution, "id", "")),
            "session_id": non_empty_str(getattr(execution, "session_id", None)),
            "run_reason": _enum_value(getattr(execution, "run_reason", None)),
            "executor_action": dict(getattr(execution, "executor_action", {}) or {}),
            "status": _enum_value(getattr(execution, "status", None)),
            "exit_code": getattr(execution, "exit_code", None),
            "dropped": bool(getattr(execution, "dropped", False)),
            "started_at": _isoformat(getattr(execution, "started_at", None)),
            "completed_at": _isoformat(getattr(execution, "completed_at", None)),
            "created_at": _isoformat(getattr(execution, "created_at", None)),
            "updated_at": _isoformat(getattr(execution, "updated_at", None)),
            "error": non_empty_str(getattr(execution, "error", None)),
            "metadata": dict(getattr(execution, "metadata_", {}) or {}),
        }
    )
    return payload.model_dump(mode="json")


def execution_log_entry_to_dict(entry: object) -> dict[str, Any]:
    payload = domain_models.ExecutionLogEntry.model_validate(
        {
            "id": str(getattr(entry, "id", "")),
            "execution_process_id": non_empty_str(getattr(entry, "execution_process_id", None)),
            "logs": str(getattr(entry, "logs", "")),
            "byte_size": int(getattr(entry, "byte_size", 0) or 0),
            "inserted_at": _isoformat(getattr(entry, "inserted_at", None)),
        }
    )
    return payload.model_dump(mode="json")


def runtime_context_to_dict(state: object) -> dict[str, Any]:
    payload = domain_models.RuntimeContext.model_validate(
        {
            "project_id": non_empty_str(getattr(state, "project_id", None)),
            "repo_id": non_empty_str(getattr(state, "repo_id", None)),
        }
    )
    return payload.model_dump(mode="json")


def startup_decision_to_dict(decision: object) -> dict[str, Any]:
    project_id = non_empty_str(getattr(decision, "project_id", None))
    preferred_repo_id = non_empty_str(getattr(decision, "preferred_repo_id", None))
    preferred_path_value = getattr(decision, "preferred_path", None)
    preferred_path = str(preferred_path_value) if preferred_path_value is not None else None
    suggest_cwd = bool(getattr(decision, "suggest_cwd", False))
    cwd_path = non_empty_str(getattr(decision, "cwd_path", None))
    cwd_is_git_repo = bool(getattr(decision, "cwd_is_git_repo", False))
    should_open_project_raw = getattr(decision, "should_open_project", None)
    should_open_project = (
        bool(should_open_project_raw)
        if should_open_project_raw is not None
        else project_id is not None
    )
    payload = domain_models.StartupDecision.model_validate(
        {
            "project_id": project_id,
            "preferred_repo_id": preferred_repo_id,
            "preferred_path": preferred_path,
            "suggest_cwd": suggest_cwd,
            "cwd_path": cwd_path,
            "cwd_is_git_repo": cwd_is_git_repo,
            "should_open_project": should_open_project,
        }
    )
    return payload.model_dump(mode="json")


def runtime_view_to_dict(
    *,
    task_id: str,
    view: object | None,
    runtime_service: object | None,
) -> dict[str, Any]:
    snapshot = runtime_snapshot_for_task(
        task_id=task_id,
        runtime_service=runtime_service,
    )
    run_count_raw = getattr(view, "run_count", 0) if view is not None else 0
    run_count = (
        run_count_raw
        if isinstance(run_count_raw, int) and not isinstance(run_count_raw, bool)
        else 0
    )
    payload = domain_models.RuntimeView.model_validate(
        {
            "task_id": task_id,
            "phase": _enum_value(getattr(view, "phase", None)),
            "execution_id": non_empty_str(getattr(view, "execution_id", None)),
            "run_count": run_count,
            "has_running_agent": getattr(view, "running_agent", None) is not None,
            "has_review_agent": getattr(view, "review_agent", None) is not None,
            "runtime": dict(snapshot),
        }
    )
    return payload.model_dump(mode="json")


def serialize_tui_value(value: object, *, ctx: AppContext | None = None) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value

    from enum import Enum

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): serialize_tui_value(val, ctx=ctx) for key, val in value.items()}
    if isinstance(value, list | tuple):
        return [serialize_tui_value(item, ctx=ctx) for item in value]
    if isinstance(value, set):
        return sorted(serialize_tui_value(item, ctx=ctx) for item in value)

    if ctx is not None:
        from kagan.core.adapters.db.schema import (
            ExecutionProcess,
            ExecutionProcessLog,
            Project,
            Task,
            Workspace,
        )
        from kagan.core.services.runtime import (
            AutoOutputReadiness,
            RuntimeContextState,
            RuntimeTaskView,
            StartupSessionDecision,
        )
        from kagan.core.services.workspaces.service import JanitorResult

        runtime_service = getattr(ctx, "runtime_service", None)
        if isinstance(value, Task):
            return task_to_dict(value, runtime_service=runtime_service)
        if isinstance(value, Project):
            return project_to_dict(value)
        if isinstance(value, Workspace):
            return workspace_to_dict(value)
        if isinstance(value, ExecutionProcess):
            return execution_to_dict(value)
        if isinstance(value, ExecutionProcessLog):
            return execution_log_entry_to_dict(value)
        if isinstance(value, RuntimeTaskView):
            return runtime_view_to_dict(
                task_id=value.task_id,
                view=value,
                runtime_service=runtime_service,
            )
        if isinstance(value, AutoOutputReadiness):
            return {
                "can_open_output": value.can_open_output,
                "execution_id": value.execution_id,
                "is_running": value.is_running,
                "recovered_stale_execution": value.recovered_stale_execution,
                "message": value.message,
                "output_mode": value.output_mode.value,
                "running_agent": None,
            }
        if isinstance(value, RuntimeContextState):
            return runtime_context_to_dict(value)
        if isinstance(value, StartupSessionDecision):
            return startup_decision_to_dict(value)
        if isinstance(value, JanitorResult):
            return {
                "worktrees_pruned": value.worktrees_pruned,
                "branches_deleted": [str(item) for item in value.branches_deleted],
                "repos_processed": [str(item) for item in value.repos_processed],
                "total_cleaned": value.total_cleaned,
            }

    if dataclasses.is_dataclass(value):
        return serialize_tui_value(dataclasses.asdict(value), ctx=ctx)

    try:
        from pydantic import BaseModel
    except ImportError:  # pragma: no cover
        BaseModel = None  # type: ignore[assignment]

    if BaseModel is not None and isinstance(value, BaseModel):
        return serialize_tui_value(value.model_dump(mode="json"), ctx=ctx)

    raise ValueError(f"Unsupported TUI transport value type: {type(value).__name__}")


__all__ = [
    "SESSION_PROMPT_PATH",
    "build_audit_list_response",
    "build_handoff_payload",
    "build_job_response",
    "execution_log_entry_to_dict",
    "execution_to_dict",
    "invalid_job_id_response",
    "invalid_task_id_response",
    "job_not_found_response",
    "parse_requested_worktree",
    "project_to_dict",
    "resolve_pair_backend",
    "runtime_context_to_dict",
    "runtime_view_to_dict",
    "serialize_tui_value",
    "session_create_error_response",
    "startup_decision_to_dict",
    "task_to_dict",
    "workspace_to_dict",
]
