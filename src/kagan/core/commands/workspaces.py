from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kagan.core.commands._parsing import (
    build_task_update_fields,
    parse_task_status,
    parse_timeout_seconds,
    parse_workspace_repo_inputs,
    str_object_dict,
)
from kagan.core.commands._serialization import project_to_dict, task_to_dict
from kagan.core.commands.plugins import (
    invoke_plugin_with_actionable_errors,
    require_plugin_operation_registered,
)
from kagan.core.policy import command
from kagan.core.services.runtime import runtime_snapshot_for_task

if TYPE_CHECKING:
    from kagan.core.api import KaganAPI
    from kagan.core.bootstrap import AppContext
    from kagan.core.domain.enums import TaskStatus

_TUI_ALLOWED_API_METHODS: frozenset[str] = frozenset(
    {
        "abort_workspace_rebase",
        "add_repo",
        "apply_rejection_feedback",
        "attach_session",
        "cancel_job",
        "cleanup_orphan_workspaces",
        "close_exploratory",
        "count_executions_for_task",
        "create_project",
        "create_session",
        "create_task",
        "decide_startup",
        "delete_task",
        "dispatch_runtime_session",
        "find_project_by_repo_path",
        "get_all_diffs",
        "get_execution",
        "get_execution_log_entries",
        "get_latest_execution_for_task",
        "get_project",
        "get_project_repo_details",
        "get_project_repos",
        "get_queue_status",
        "get_queued_messages",
        "get_running_task_ids",
        "get_runtime_view",
        "get_scratchpad",
        "get_task",
        "get_workspace_commit_log",
        "get_workspace_diff",
        "get_workspace_diff_stats",
        "get_workspace_path",
        "get_workspace_repos",
        "get_repo_diff",
        "has_no_changes",
        "invoke_plugin",
        "is_automation_running",
        "kill_session",
        "list_pending_planner_drafts",
        "list_projects",
        "list_tasks",
        "list_workspaces",
        "merge_repo",
        "merge_task_direct",
        "move_task",
        "open_project",
        "plugin_ui_catalog",
        "plugin_ui_invoke",
        "prepare_auto_output",
        "provision_workspace",
        "queue_message",
        "rebase_workspace",
        "reconcile_running_tasks",
        "recover_stale_auto_output",
        "remove_queued_message",
        "resolve_task_base_branch",
        "run_workspace_janitor",
        "runtime_state",
        "save_planner_draft",
        "search_tasks",
        "session_exists",
        "submit_job",
        "take_queued_message",
        "update_planner_draft_status",
        "update_repo_default_branch",
        "update_task",
        "wait_job",
    }
)


def _api(ctx: AppContext) -> KaganAPI:
    api = getattr(ctx, "api", None)
    if api is None:
        raise ValueError("API context is not initialized")
    return api


def _non_empty_str(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized if normalized else None
    return None


def _str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := str(item).strip())]
    return []


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


def _workspace_to_dict(workspace: object) -> dict[str, Any]:
    return {
        "id": str(getattr(workspace, "id", "")),
        "project_id": _non_empty_str(getattr(workspace, "project_id", None)),
        "task_id": _non_empty_str(getattr(workspace, "task_id", None)),
        "branch_name": str(getattr(workspace, "branch_name", "")),
        "path": str(getattr(workspace, "path", "")),
        "status": _enum_value(getattr(workspace, "status", None)),
        "created_at": _isoformat(getattr(workspace, "created_at", None)),
        "updated_at": _isoformat(getattr(workspace, "updated_at", None)),
    }


def _execution_to_dict(execution: object) -> dict[str, Any]:
    return {
        "id": str(getattr(execution, "id", "")),
        "session_id": _non_empty_str(getattr(execution, "session_id", None)),
        "run_reason": _enum_value(getattr(execution, "run_reason", None)),
        "executor_action": dict(getattr(execution, "executor_action", {}) or {}),
        "status": _enum_value(getattr(execution, "status", None)),
        "exit_code": getattr(execution, "exit_code", None),
        "dropped": bool(getattr(execution, "dropped", False)),
        "started_at": _isoformat(getattr(execution, "started_at", None)),
        "completed_at": _isoformat(getattr(execution, "completed_at", None)),
        "created_at": _isoformat(getattr(execution, "created_at", None)),
        "updated_at": _isoformat(getattr(execution, "updated_at", None)),
        "error": _non_empty_str(getattr(execution, "error", None)),
        "metadata": dict(getattr(execution, "metadata_", {}) or {}),
    }


def _execution_log_entry_to_dict(entry: object) -> dict[str, Any]:
    return {
        "id": str(getattr(entry, "id", "")),
        "execution_process_id": _non_empty_str(getattr(entry, "execution_process_id", None)),
        "logs": str(getattr(entry, "logs", "")),
        "byte_size": int(getattr(entry, "byte_size", 0) or 0),
        "inserted_at": _isoformat(getattr(entry, "inserted_at", None)),
    }


def _runtime_context_to_dict(state: object) -> dict[str, Any]:
    return {
        "project_id": _non_empty_str(getattr(state, "project_id", None)),
        "repo_id": _non_empty_str(getattr(state, "repo_id", None)),
    }


def _startup_decision_to_dict(decision: object) -> dict[str, Any]:
    project_id = _non_empty_str(getattr(decision, "project_id", None))
    preferred_repo_id = _non_empty_str(getattr(decision, "preferred_repo_id", None))
    preferred_path_value = getattr(decision, "preferred_path", None)
    preferred_path = str(preferred_path_value) if preferred_path_value is not None else None
    suggest_cwd = bool(getattr(decision, "suggest_cwd", False))
    cwd_path = _non_empty_str(getattr(decision, "cwd_path", None))
    cwd_is_git_repo = bool(getattr(decision, "cwd_is_git_repo", False))
    should_open_project_raw = getattr(decision, "should_open_project", None)
    should_open_project = (
        bool(should_open_project_raw)
        if should_open_project_raw is not None
        else project_id is not None
    )
    return {
        "project_id": project_id,
        "preferred_repo_id": preferred_repo_id,
        "preferred_path": preferred_path,
        "suggest_cwd": suggest_cwd,
        "cwd_path": cwd_path,
        "cwd_is_git_repo": cwd_is_git_repo,
        "should_open_project": should_open_project,
    }


def _runtime_view_to_dict(
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
    return {
        "task_id": task_id,
        "phase": _enum_value(getattr(view, "phase", None)),
        "execution_id": _non_empty_str(getattr(view, "execution_id", None)),
        "run_count": run_count,
        "has_running_agent": getattr(view, "running_agent", None) is not None,
        "has_review_agent": getattr(view, "review_agent", None) is not None,
        "runtime": dict(snapshot),
    }


def _normalize_tui_kwargs(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("kwargs must be an object")
    return {str(key): val for key, val in value.items()}


def _parse_tui_api_call_params(params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    method_name = _non_empty_str(params.get("method"))
    if method_name is None:
        raise ValueError("method is required. Provide the API method name to call.")
    return method_name, _normalize_tui_kwargs(params.get("kwargs"))


def _required_non_empty(kwargs: dict[str, Any], key: str) -> str:
    value = _non_empty_str(kwargs.get(key))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_string_sequence(
    kwargs: dict[str, Any],
    key: str,
) -> list[str] | None:
    raw = kwargs.get(key)
    if raw is None:
        return None
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError(f"{key} must be a list of strings")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"{key} must be a list of strings")
        values.append(item)
    return values


def _optional_non_negative_int(
    kwargs: dict[str, Any],
    key: str,
    *,
    default: int,
) -> int:
    raw = kwargs.get(key)
    if raw is None:
        return default
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{key} must be an integer >= 0")
    if raw < 0:
        raise ValueError(f"{key} must be an integer >= 0")
    return raw


def _parse_merge_strategy(value: object) -> Any:
    from kagan.core.services.workspaces import MergeStrategy

    if isinstance(value, MergeStrategy):
        return value
    if not isinstance(value, str):
        raise ValueError("strategy must be one of: direct, pr")
    normalized = value.strip().lower()
    if normalized in {"pr", "pull_request"}:
        return MergeStrategy.PULL_REQUEST
    if normalized == "direct":
        return MergeStrategy.DIRECT
    raise ValueError("strategy must be one of: direct, pr")


def _parse_tui_lane(value: object) -> str:
    lane = _parse_queue_lane(value)
    if lane not in {"implementation", "review", "planner"}:
        raise ValueError(lane)
    return lane


def _parse_queue_lane(value: object) -> str:
    if value is None:
        return "implementation"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"implementation", "review", "planner"}:
            return normalized
    return "lane must be one of: implementation, review, planner"


def _parse_jsonable_task_ids(value: object, *, field_name: str) -> set[str]:
    if not isinstance(value, list | tuple | set):
        raise ValueError(f"{field_name} must be a list of task/workspace IDs")
    return {str(item).strip() for item in value if str(item).strip()}


def _parse_runtime_session_event(value: object):
    from kagan.core.services.runtime import RuntimeSessionEvent

    if isinstance(value, RuntimeSessionEvent):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "project_selected": RuntimeSessionEvent.PROJECT_SELECTED,
            "repo_selected": RuntimeSessionEvent.REPO_SELECTED,
            "repo_cleared": RuntimeSessionEvent.REPO_CLEARED,
            "reset": RuntimeSessionEvent.RESET,
        }
        if normalized in aliases:
            return aliases[normalized]
    return None


def _parse_proposal_status(value: object):
    from kagan.core.domain.enums import ProposalStatus

    if isinstance(value, ProposalStatus):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        try:
            return ProposalStatus(normalized)
        except ValueError:
            return None
    return None


def _parse_json_dict_list(value: object, *, field_name: str) -> list[dict[str, Any]] | str:
    if not isinstance(value, list):
        return f"{field_name} must be a list"
    parsed: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            return f"{field_name} items must be objects"
        parsed.append({str(key): val for key, val in item.items()})
    return parsed


async def _resolve_task_for_tui_method(
    api: KaganAPI,
    kwargs: dict[str, Any],
) -> Any:
    raw_task_id = kwargs.get("task_id")
    task_id = _non_empty_str(raw_task_id)
    if task_id is None:
        raw_task = kwargs.get("task")
        if isinstance(raw_task, dict):
            task_id = _non_empty_str(raw_task.get("id"))
        elif isinstance(raw_task, str):
            task_id = _non_empty_str(raw_task)
    if task_id is None:
        raise ValueError("task_id is required")
    task = await api.get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found. Check task_id with task_list.")
    return task


def _serialize_tui_value(value: object, *, api: KaganAPI | None = None) -> Any:
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
        return {str(key): _serialize_tui_value(val, api=api) for key, val in value.items()}
    if isinstance(value, list | tuple):
        return [_serialize_tui_value(item, api=api) for item in value]
    if isinstance(value, set):
        return sorted(_serialize_tui_value(item, api=api) for item in value)

    if api is not None:
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

        runtime_service = getattr(getattr(api, "_ctx", None), "runtime_service", None)
        if isinstance(value, Task):
            return task_to_dict(value, runtime_service=runtime_service)
        if isinstance(value, Project):
            return project_to_dict(value)
        if isinstance(value, Workspace):
            return _workspace_to_dict(value)
        if isinstance(value, ExecutionProcess):
            return _execution_to_dict(value)
        if isinstance(value, ExecutionProcessLog):
            return _execution_log_entry_to_dict(value)
        if isinstance(value, RuntimeTaskView):
            return _runtime_view_to_dict(
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
            return _runtime_context_to_dict(value)
        if isinstance(value, StartupSessionDecision):
            return _startup_decision_to_dict(value)
        if isinstance(value, JanitorResult):
            return {
                "worktrees_pruned": value.worktrees_pruned,
                "branches_deleted": [str(item) for item in value.branches_deleted],
                "repos_processed": [str(item) for item in value.repos_processed],
                "total_cleaned": value.total_cleaned,
            }

    if dataclasses.is_dataclass(value):
        return _serialize_tui_value(dataclasses.asdict(value), api=api)

    try:
        from pydantic import BaseModel
    except ImportError:  # pragma: no cover
        BaseModel = None  # type: ignore[assignment]

    if BaseModel is not None and isinstance(value, BaseModel):
        return _serialize_tui_value(value.model_dump(mode="json"), api=api)

    raise ValueError(f"Unsupported TUI transport value type: {type(value).__name__}")


async def _dispatch_tui_api_call(
    api: KaganAPI,
    method_name: str,
    kwargs: dict[str, Any],
) -> Any:
    if method_name not in _TUI_ALLOWED_API_METHODS:
        raise ValueError(f"Unsupported TUI API method: {method_name}")

    match method_name:
        case "create_task":
            title = _required_non_empty(kwargs, "title")
            description = str(kwargs.get("description", ""))
            project_id = _non_empty_str(kwargs.get("project_id"))
            created_by = _non_empty_str(kwargs.get("created_by"))
            fields = build_task_update_fields(kwargs)
            fields.pop("title", None)
            fields.pop("description", None)
            fields.pop("project_id", None)
            return await api.create_task(
                title,
                description,
                project_id=project_id,
                created_by=created_by,
                **fields,
            )
        case "update_task":
            task_id = _required_non_empty(kwargs, "task_id")
            fields = build_task_update_fields(kwargs)
            return await api.update_task(task_id, **fields)
        case "delete_task":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.delete_task(task_id)
        case "move_task":
            task_id = _required_non_empty(kwargs, "task_id")
            status = parse_task_status(kwargs.get("status"))
            return await api.move_task(task_id, status)
        case "list_tasks":
            project_id = _non_empty_str(kwargs.get("project_id"))
            status: TaskStatus | None = None
            if "status" in kwargs:
                status = parse_task_status(kwargs["status"])
            elif "filter" in kwargs:
                filter_value = _non_empty_str(kwargs.get("filter"))
                if filter_value is not None:
                    status = parse_task_status(filter_value)
            return await api.list_tasks(project_id=project_id, status=status)
        case "search_tasks":
            return await api.search_tasks(str(kwargs.get("query", "")))
        case "create_project":
            name = _required_non_empty(kwargs, "name")
            description = str(kwargs.get("description", ""))
            repo_paths = _optional_string_sequence(kwargs, "repo_paths")
            return await api.create_project(name, description=description, repo_paths=repo_paths)
        case "add_repo":
            project_id = _required_non_empty(kwargs, "project_id")
            repo_path = _required_non_empty(kwargs, "repo_path")
            is_primary = bool(kwargs.get("is_primary", False))
            return await api.add_repo(project_id, repo_path, is_primary=is_primary)
        case "list_projects":
            limit = _optional_non_negative_int(kwargs, "limit", default=10)
            return await api.list_projects(limit=limit)
        case "get_project":
            project_id = _required_non_empty(kwargs, "project_id")
            return await api.get_project(project_id)
        case "open_project":
            project_id = _required_non_empty(kwargs, "project_id")
            return await api.open_project(project_id)
        case "get_project_repos":
            project_id = _required_non_empty(kwargs, "project_id")
            return await api.get_project_repos(project_id)
        case "get_project_repo_details":
            project_id = _required_non_empty(kwargs, "project_id")
            repos = await api.get_project_repo_details(project_id)
            return {"repos": repos, "count": len(repos)}
        case "find_project_by_repo_path":
            repo_path = _required_non_empty(kwargs, "repo_path")
            return await api.find_project_by_repo_path(repo_path)
        case "decide_startup":
            cwd = _required_non_empty(kwargs, "cwd")
            return await api.decide_startup(Path(cwd))
        case "dispatch_runtime_session":
            event = _parse_runtime_session_event(kwargs.get("event"))
            if event is None:
                raise ValueError(
                    "event must be one of: project_selected, repo_selected, repo_cleared, reset"
                )
            return await api.dispatch_runtime_session(
                event,
                project_id=_non_empty_str(kwargs.get("project_id")),
                repo_id=_non_empty_str(kwargs.get("repo_id")),
            )
        case "runtime_state":
            return api.runtime_state
        case "get_runtime_view":
            task_id = _required_non_empty(kwargs, "task_id")
            return api.get_runtime_view(task_id)
        case "get_running_task_ids":
            return api.get_running_task_ids()
        case "get_task":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.get_task(task_id)
        case "get_scratchpad":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.get_scratchpad(task_id)
        case "get_execution":
            execution_id = _required_non_empty(kwargs, "execution_id")
            return await api.get_execution(execution_id)
        case "get_execution_log_entries":
            execution_id = _required_non_empty(kwargs, "execution_id")
            return await api.get_execution_log_entries(execution_id)
        case "get_latest_execution_for_task":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.get_latest_execution_for_task(task_id)
        case "count_executions_for_task":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.count_executions_for_task(task_id)
        case "reconcile_running_tasks":
            task_ids = _parse_jsonable_task_ids(kwargs.get("task_ids", []), field_name="task_ids")
            return await api.reconcile_running_tasks(sorted(task_ids))
        case "is_automation_running":
            task_id = _required_non_empty(kwargs, "task_id")
            return api.is_automation_running(task_id)
        case "submit_job":
            task_id = _required_non_empty(kwargs, "task_id")
            action = _required_non_empty(kwargs, "action")
            arguments_raw = kwargs.get("arguments")
            if arguments_raw is not None and not isinstance(arguments_raw, dict):
                raise ValueError("arguments must be an object when provided")
            arguments = dict(arguments_raw) if isinstance(arguments_raw, dict) else None
            return await api.submit_job(task_id, action, arguments=arguments)
        case "wait_job":
            job_id = _required_non_empty(kwargs, "job_id")
            task_id = _required_non_empty(kwargs, "task_id")
            timeout = parse_timeout_seconds(kwargs.get("timeout_seconds"))
            if isinstance(timeout, str):
                raise ValueError(timeout)
            return await api.wait_job(job_id, task_id=task_id, timeout_seconds=timeout)
        case "cancel_job":
            job_id = _required_non_empty(kwargs, "job_id")
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.cancel_job(job_id, task_id=task_id)
        case "create_session":
            task_id = _required_non_empty(kwargs, "task_id")
            reuse_if_exists = bool(kwargs.get("reuse_if_exists", True))
            worktree_value = _non_empty_str(kwargs.get("worktree_path"))
            worktree_path = (
                Path(worktree_value).expanduser().resolve(strict=False)
                if worktree_value is not None
                else None
            )
            return await api.create_session(
                task_id,
                worktree_path=worktree_path,
                reuse_if_exists=reuse_if_exists,
            )
        case "attach_session":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.attach_session(task_id)
        case "session_exists":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.session_exists(task_id)
        case "kill_session":
            task_id = _required_non_empty(kwargs, "task_id")
            await api.kill_session(task_id)
            return None
        case "queue_message":
            session_id = _required_non_empty(kwargs, "session_id")
            content = _required_non_empty(kwargs, "content")
            lane = _parse_tui_lane(kwargs.get("lane"))
            author = _non_empty_str(kwargs.get("author"))
            metadata = str_object_dict(kwargs.get("metadata"))
            return await api.queue_message(
                session_id,
                content,
                lane=lane,
                author=author,
                metadata=metadata,
            )
        case "get_queue_status":
            session_id = _required_non_empty(kwargs, "session_id")
            lane = _parse_tui_lane(kwargs.get("lane"))
            return await api.get_queue_status(session_id, lane=lane)
        case "get_queued_messages":
            session_id = _required_non_empty(kwargs, "session_id")
            lane = _parse_tui_lane(kwargs.get("lane"))
            return await api.get_queued_messages(session_id, lane=lane)
        case "take_queued_message":
            session_id = _required_non_empty(kwargs, "session_id")
            lane = _parse_tui_lane(kwargs.get("lane"))
            return await api.take_queued_message(session_id, lane=lane)
        case "remove_queued_message":
            session_id = _required_non_empty(kwargs, "session_id")
            lane = _parse_tui_lane(kwargs.get("lane"))
            index_raw = kwargs.get("index")
            if not isinstance(index_raw, int) or isinstance(index_raw, bool):
                raise ValueError("index must be an integer")
            return await api.remove_queued_message(session_id, index_raw, lane=lane)
        case "provision_workspace":
            task_id = _required_non_empty(kwargs, "task_id")
            parsed_repos = parse_workspace_repo_inputs(kwargs.get("repos"))
            if isinstance(parsed_repos, str):
                raise ValueError(parsed_repos)
            return await api.provision_workspace(task_id=task_id, repos=parsed_repos)
        case "run_workspace_janitor":
            valid_workspace_ids = _parse_jsonable_task_ids(
                kwargs.get("valid_workspace_ids", []),
                field_name="valid_workspace_ids",
            )
            return await api.run_workspace_janitor(
                valid_workspace_ids,
                prune_worktrees=bool(kwargs.get("prune_worktrees", True)),
                gc_branches=bool(kwargs.get("gc_branches", True)),
            )
        case "list_workspaces":
            task_id = _non_empty_str(kwargs.get("task_id"))
            return await api.list_workspaces(task_id=task_id)
        case "get_workspace_path":
            task_id = _required_non_empty(kwargs, "task_id")
            return await api.get_workspace_path(task_id)
        case "get_workspace_repos":
            workspace_id = _required_non_empty(kwargs, "workspace_id")
            return await api.get_workspace_repos(workspace_id)
        case "get_workspace_diff":
            task_id = _required_non_empty(kwargs, "task_id")
            base_branch = _required_non_empty(kwargs, "base_branch")
            return await api.get_workspace_diff(task_id, base_branch=base_branch)
        case "get_workspace_commit_log":
            task_id = _required_non_empty(kwargs, "task_id")
            base_branch = _required_non_empty(kwargs, "base_branch")
            return await api.get_workspace_commit_log(task_id, base_branch=base_branch)
        case "get_workspace_diff_stats":
            task_id = _required_non_empty(kwargs, "task_id")
            base_branch = _required_non_empty(kwargs, "base_branch")
            return await api.get_workspace_diff_stats(task_id, base_branch=base_branch)
        case "rebase_workspace":
            task_id = _required_non_empty(kwargs, "task_id")
            base_branch = _required_non_empty(kwargs, "base_branch")
            return await api.rebase_workspace(task_id, base_branch)
        case "abort_workspace_rebase":
            task_id = _required_non_empty(kwargs, "task_id")
            await api.abort_workspace_rebase(task_id)
            return None
        case "get_all_diffs":
            workspace_id = _required_non_empty(kwargs, "workspace_id")
            return await api.get_all_diffs(workspace_id)
        case "get_repo_diff":
            workspace_id = _required_non_empty(kwargs, "workspace_id")
            repo_id = _required_non_empty(kwargs, "repo_id")
            return await api.get_repo_diff(workspace_id, repo_id)
        case "merge_repo":
            workspace_id = _required_non_empty(kwargs, "workspace_id")
            repo_id = _required_non_empty(kwargs, "repo_id")
            strategy = _parse_merge_strategy(kwargs.get("strategy"))
            pr_title = _non_empty_str(kwargs.get("pr_title"))
            pr_body = _non_empty_str(kwargs.get("pr_body"))
            commit_message = _non_empty_str(kwargs.get("commit_message"))
            return await api.merge_repo(
                workspace_id,
                repo_id,
                strategy=strategy,
                pr_title=pr_title,
                pr_body=pr_body,
                commit_message=commit_message,
            )
        case "cleanup_orphan_workspaces":
            valid_task_ids = _parse_jsonable_task_ids(
                kwargs.get("valid_task_ids", []),
                field_name="valid_task_ids",
            )
            return await api.cleanup_orphan_workspaces(valid_task_ids)
        case "save_planner_draft":
            project_id = _required_non_empty(kwargs, "project_id")
            repo_id = _non_empty_str(kwargs.get("repo_id"))
            tasks_json = _parse_json_dict_list(kwargs.get("tasks_json"), field_name="tasks_json")
            if isinstance(tasks_json, str):
                raise ValueError(tasks_json)
            todos_json_raw = kwargs.get("todos_json")
            todos_json: list[dict[str, Any]] | None = None
            if todos_json_raw is not None:
                parsed_todos = _parse_json_dict_list(todos_json_raw, field_name="todos_json")
                if isinstance(parsed_todos, str):
                    raise ValueError(parsed_todos)
                todos_json = parsed_todos
            return await api.save_planner_draft(
                project_id=project_id,
                repo_id=repo_id,
                tasks_json=tasks_json,
                todos_json=todos_json,
            )
        case "list_pending_planner_drafts":
            project_id = _required_non_empty(kwargs, "project_id")
            repo_id = _non_empty_str(kwargs.get("repo_id"))
            return await api.list_pending_planner_drafts(project_id, repo_id=repo_id)
        case "update_planner_draft_status":
            proposal_id = _required_non_empty(kwargs, "proposal_id")
            status = _parse_proposal_status(kwargs.get("status"))
            if status is None:
                raise ValueError("status must be one of: draft, approved, rejected")
            return await api.update_planner_draft_status(proposal_id, status)
        case "has_no_changes":
            task = await _resolve_task_for_tui_method(api, kwargs)
            return await api.has_no_changes(task)
        case "close_exploratory":
            task = await _resolve_task_for_tui_method(api, kwargs)
            return await api.close_exploratory(task)
        case "merge_task_direct":
            task = await _resolve_task_for_tui_method(api, kwargs)
            return await api.merge_task_direct(task)
        case "apply_rejection_feedback":
            task = await _resolve_task_for_tui_method(api, kwargs)
            feedback = _non_empty_str(kwargs.get("feedback"))
            action = _non_empty_str(kwargs.get("action")) or "reopen"
            return await api.apply_rejection_feedback(task, feedback, action)
        case "resolve_task_base_branch":
            task = await _resolve_task_for_tui_method(api, kwargs)
            return await api.resolve_task_base_branch(task)
        case "prepare_auto_output":
            task = await _resolve_task_for_tui_method(api, kwargs)
            return await api.prepare_auto_output(task)
        case "recover_stale_auto_output":
            task = await _resolve_task_for_tui_method(api, kwargs)
            return await api.recover_stale_auto_output(task)
        case "update_repo_default_branch":
            repo_id = _required_non_empty(kwargs, "repo_id")
            branch = _required_non_empty(kwargs, "branch")
            mark_configured = bool(kwargs.get("mark_configured", False))
            return await api.update_repo_default_branch(
                repo_id,
                branch,
                mark_configured=mark_configured,
            )
        case "invoke_plugin":
            capability = _required_non_empty(kwargs, "capability")
            method = _required_non_empty(kwargs, "method")
            plugin_params = kwargs.get("params")
            if plugin_params is not None and not isinstance(plugin_params, dict):
                raise ValueError("params must be an object when provided")
            normalized_params = dict(plugin_params) if isinstance(plugin_params, dict) else None
            require_plugin_operation_registered(api, capability=capability, method=method)
            return await invoke_plugin_with_actionable_errors(
                api,
                capability=capability,
                method=method,
                params=normalized_params,
            )
        case "plugin_ui_catalog":
            project_id = _required_non_empty(kwargs, "project_id")
            repo_id = _non_empty_str(kwargs.get("repo_id"))
            return await api.plugin_ui_catalog(project_id=project_id, repo_id=repo_id)
        case "plugin_ui_invoke":
            project_id = _required_non_empty(kwargs, "project_id")
            plugin_id = _required_non_empty(kwargs, "plugin_id")
            action_id = _required_non_empty(kwargs, "action_id")
            repo_id = _non_empty_str(kwargs.get("repo_id"))
            inputs_raw = kwargs.get("inputs")
            if inputs_raw is not None and not isinstance(inputs_raw, dict):
                raise ValueError("inputs must be an object when provided")
            inputs: dict[str, Any] | None = (
                dict(inputs_raw) if isinstance(inputs_raw, dict) else None
            )
            return await api.plugin_ui_invoke(
                project_id=project_id,
                plugin_id=plugin_id,
                action_id=action_id,
                repo_id=repo_id,
                inputs=inputs,
            )
        case _:
            raise ValueError(f"Unsupported TUI API method: {method_name}")


@command("tui", "api_call", profile="maintainer", description="Dispatch TUI API operation.")
async def handle_tui_api_call(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    try:
        method_name, kwargs = _parse_tui_api_call_params(params)
    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
            "code": "INVALID_PARAMS",
        }

    try:
        value = await _dispatch_tui_api_call(api, method_name, kwargs)
        serialized_value = _serialize_tui_value(value, api=api)
    except ValueError as exc:
        return {
            "success": False,
            "method": method_name,
            "message": str(exc),
            "code": "INVALID_PARAMS",
        }

    return {
        "success": True,
        "method": method_name,
        "value": serialized_value,
    }


__all__ = ["handle_tui_api_call"]
