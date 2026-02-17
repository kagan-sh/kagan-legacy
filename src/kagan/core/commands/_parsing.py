from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from kagan.core.domain.enums import PairTerminalBackend, TaskPriority, TaskStatus, TaskType

if TYPE_CHECKING:
    from kagan.core.services.workspaces import RepoWorkspaceInput

DEFAULT_EVENTS_LIMIT = 50
MAX_EVENTS_LIMIT = 100


def require_str(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def optional_str(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized if normalized else None
    return None


def str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for raw in value if (item := str(raw).strip())]
    return []


def str_object_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict) and value:
        return {str(key): val for key, val in value.items()}
    return None


def parse_task_status(value: object) -> TaskStatus:
    if isinstance(value, TaskStatus):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
        if normalized == "INPROGRESS":
            normalized = "IN_PROGRESS"
        if normalized in {"AUTO", "PAIR"}:
            raise ValueError(
                f"Invalid task status value: {value!r}. "
                "AUTO/PAIR are task_type values. "
                "Use task_type='AUTO' or task_type='PAIR' with tasks.update."
            )
        try:
            return TaskStatus(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid task status value: {value!r}. "
                "Expected one of: BACKLOG, IN_PROGRESS, REVIEW, DONE."
            ) from exc
    raise ValueError(
        f"Invalid task status value: {value!r}. "
        "Expected one of: BACKLOG, IN_PROGRESS, REVIEW, DONE."
    )


def parse_task_priority(value: object) -> TaskPriority:
    if isinstance(value, TaskPriority):
        return value
    if isinstance(value, int):
        return TaskPriority(value)
    if isinstance(value, str):
        cleaned = value.strip().upper()
        if cleaned.isdigit():
            return TaskPriority(int(cleaned))
        aliases = {
            "LOW": TaskPriority.LOW,
            "MED": TaskPriority.MEDIUM,
            "MEDIUM": TaskPriority.MEDIUM,
            "HIGH": TaskPriority.HIGH,
        }
        if cleaned in aliases:
            return aliases[cleaned]
    raise ValueError(f"Invalid task priority value: {value!r}. Expected one of: LOW, MEDIUM, HIGH.")


def parse_task_type(value: object) -> TaskType:
    if isinstance(value, TaskType):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        try:
            return TaskType(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid task type value: {value!r}. Expected one of: AUTO, PAIR."
            ) from exc
    raise ValueError(f"Invalid task type value: {value!r}. Expected one of: AUTO, PAIR.")


def parse_terminal_backend(value: object) -> PairTerminalBackend | None:
    if value is None or isinstance(value, PairTerminalBackend):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        try:
            return PairTerminalBackend(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid terminal backend value: {value!r}. Expected one of: tmux, vscode, cursor."
            ) from exc
    raise ValueError(
        f"Invalid terminal backend value: {value!r}. Expected one of: tmux, vscode, cursor."
    )


def parse_acceptance_criteria(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("acceptance_criteria must be a string or list of strings")


def build_task_update_fields(params: dict[str, Any]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key in {"title", "description", "project_id", "parent_id", "base_branch"}:
        if key in params:
            fields[key] = params[key]

    if "status" in params:
        fields["status"] = parse_task_status(params["status"])
    if "priority" in params:
        fields["priority"] = parse_task_priority(params["priority"])
    if "task_type" in params:
        fields["task_type"] = parse_task_type(params["task_type"])
    if "terminal_backend" in params:
        fields["terminal_backend"] = parse_terminal_backend(params["terminal_backend"])
    if "agent_backend" in params:
        fields["agent_backend"] = params["agent_backend"]
    if "acceptance_criteria" in params:
        fields["acceptance_criteria"] = parse_acceptance_criteria(params["acceptance_criteria"])
    return fields


def parse_workspace_repo_inputs(value: object) -> list[RepoWorkspaceInput] | str:
    from kagan.core.services.workspaces import RepoWorkspaceInput

    if not isinstance(value, list) or not value:
        return "repos must be a non-empty list"

    parsed: list[RepoWorkspaceInput] = []
    for item in value:
        if not isinstance(item, dict):
            return "Each repos item must be an object with repo_id, repo_path, and target_branch"
        repo_id = optional_str(item.get("repo_id"))
        repo_path = optional_str(item.get("repo_path"))
        target_branch = optional_str(item.get("target_branch"))
        if repo_id is None or repo_path is None or target_branch is None:
            return "Each repos item must include non-empty repo_id, repo_path, and target_branch"
        parsed.append(
            RepoWorkspaceInput(
                repo_id=repo_id,
                repo_path=repo_path,
                target_branch=target_branch,
            )
        )
    return parsed


def parse_timeout_seconds(value: object) -> float | None | str:
    if value is None:
        return None
    if isinstance(value, bool):
        return "timeout_seconds must be a non-negative number"
    if not isinstance(value, int | float):
        return "timeout_seconds must be a non-negative number"
    timeout = float(value)
    if timeout < 0:
        return "timeout_seconds must be >= 0"
    return timeout


def parse_events_limit(value: object) -> int | str:
    if value is None:
        return DEFAULT_EVENTS_LIMIT
    if isinstance(value, bool) or not isinstance(value, int):
        return f"limit must be an integer between 1 and {MAX_EVENTS_LIMIT}"
    if value < 1 or value > MAX_EVENTS_LIMIT:
        return f"limit must be an integer between 1 and {MAX_EVENTS_LIMIT}"
    return value


def parse_events_offset(value: object) -> int | str:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        return "offset must be an integer >= 0"
    if value < 0:
        return "offset must be an integer >= 0"
    return value


def parse_wait_timeout_seconds(
    value: object,
    *,
    default_timeout: int,
    max_timeout: int,
) -> float | str:
    if value is None:
        return float(default_timeout)
    if isinstance(value, bool):
        return "timeout_seconds must be a positive number"

    timeout_seconds: float
    if isinstance(value, int | float):
        timeout_seconds = float(value)
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return "timeout_seconds must be a positive number"
        try:
            timeout_seconds = float(normalized)
        except ValueError:
            return "timeout_seconds must be a positive number"
    else:
        return "timeout_seconds must be a positive number"

    if timeout_seconds <= 0:
        return "timeout_seconds must be > 0"
    if timeout_seconds > max_timeout:
        return f"timeout_seconds exceeds server maximum of {max_timeout}s"
    return timeout_seconds


def parse_wait_for_status_filter(value: object) -> set[str] | str | None:
    if value is None:
        return None

    values: list[object]
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.startswith("[") and normalized.endswith("]"):
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError:
                return "wait_for_status JSON string must decode to a list of statuses"
            if not isinstance(parsed, list):
                return "wait_for_status JSON string must decode to a list of statuses"
            values = parsed
        else:
            values = [part for part in normalized.split(",") if part.strip()]
    else:
        return "wait_for_status must be a list of status strings"

    valid_statuses = {status.value for status in TaskStatus}
    parsed_statuses: set[str] = set()
    for raw_value in values:
        status = str(raw_value).strip().upper().replace("-", "_").replace(" ", "_")
        if status == "INPROGRESS":
            status = "IN_PROGRESS"
        if status not in valid_statuses:
            return (
                f"Invalid status filter value: {raw_value!r}. "
                f"Expected one of: {', '.join(sorted(valid_statuses))}"
            )
        parsed_statuses.add(status)

    if not parsed_statuses:
        return None
    return parsed_statuses


def parse_queue_lane(value: object) -> str:
    if value is None:
        return "implementation"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"implementation", "review", "planner"}:
            return normalized
    return "lane must be one of: implementation, review, planner"


def parse_runtime_session_event(value: object):
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


def parse_proposal_status(value: object):
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


def parse_json_dict_list(value: object, *, field_name: str) -> list[dict[str, Any]] | str:
    if not isinstance(value, list):
        return f"{field_name} must be a list"
    parsed: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            return f"{field_name} items must be objects"
        parsed.append({str(key): val for key, val in item.items()})
    return parsed


__all__ = [
    "DEFAULT_EVENTS_LIMIT",
    "MAX_EVENTS_LIMIT",
    "build_task_update_fields",
    "optional_str",
    "parse_acceptance_criteria",
    "parse_events_limit",
    "parse_events_offset",
    "parse_task_priority",
    "parse_task_status",
    "parse_task_type",
    "parse_terminal_backend",
    "parse_timeout_seconds",
    "parse_wait_for_status_filter",
    "parse_wait_timeout_seconds",
    "parse_workspace_repo_inputs",
    "require_str",
    "str_list",
    "str_object_dict",
]
