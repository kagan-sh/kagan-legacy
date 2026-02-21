from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeGuard

from kagan.core.domain.coercion import (
    TASK_STATUS_VALUES,
    coerce_task_priority,
    coerce_task_status,
    coerce_task_type,
    is_task_type_token,
    normalize_acceptance_criteria,
)
from kagan.core.domain.enums import (
    PairTerminalBackend,
    QueueLane,
    TaskPriority,
    TaskStatus,
    TaskType,
    coerce_pair_backend,
    coerce_queue_lane,
)
from kagan.core.protocol_constants import DEFAULT_EVENTS_LIMIT, MAX_EVENTS_LIMIT
from kagan.core.scalars import dict_str_keys_or_none, float_or_none, non_empty_str

if TYPE_CHECKING:
    from kagan.core.services.workspaces import RepoWorkspaceInput

PAIR_TERMINAL_BACKEND_OPTIONS = ", ".join(backend.value for backend in PairTerminalBackend)
QUEUE_LANE_OPTIONS = ", ".join(lane.value for lane in QueueLane)


@dataclass(frozen=True, slots=True)
class ParseError:
    message: str
    code: str = "INVALID_PARAMS"


def is_parse_error(v: object) -> TypeGuard[ParseError]:
    return isinstance(v, ParseError)


def require_str(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def optional_str(value: object) -> str | None:
    return non_empty_str(value)


def str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for raw in value if (item := str(raw).strip())]
    return []


def str_object_dict(value: object) -> dict[str, object] | None:
    parsed = dict_str_keys_or_none(value)
    return parsed or None


def parse_task_status(value: object) -> TaskStatus:
    if (status := coerce_task_status(value)) is not None:
        return status
    if is_task_type_token(value):
        raise ValueError(
            f"Invalid task status value: {value!r}. "
            "AUTO/PAIR are task_type values. "
            "Use task_type='AUTO' or task_type='PAIR' with tasks.update."
        )
    raise ValueError(
        f"Invalid task status value: {value!r}. "
        "Expected one of: BACKLOG, IN_PROGRESS, REVIEW, DONE."
    )


def parse_task_priority(value: object) -> TaskPriority:
    if isinstance(value, int):
        return TaskPriority(value)
    if (priority := coerce_task_priority(value)) is not None:
        return priority
    raise ValueError(f"Invalid task priority value: {value!r}. Expected one of: LOW, MEDIUM, HIGH.")


def parse_task_type(value: object) -> TaskType:
    if (task_type := coerce_task_type(value)) is not None:
        return task_type
    raise ValueError(f"Invalid task type value: {value!r}. Expected one of: AUTO, PAIR.")


def parse_terminal_backend(value: object) -> PairTerminalBackend | None:
    if value is None:
        return None
    if isinstance(value, PairTerminalBackend):
        return value
    if coerced := coerce_pair_backend(value):
        return PairTerminalBackend(coerced)
    raise ValueError(
        "Invalid terminal backend value: "
        f"{value!r}. Expected one of: {PAIR_TERMINAL_BACKEND_OPTIONS}."
    )


def parse_acceptance_criteria(value: object) -> list[str]:
    normalized = normalize_acceptance_criteria(value)
    if normalized is not None:
        return normalized
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


def parse_workspace_repo_inputs(value: object) -> list[RepoWorkspaceInput] | ParseError:
    from kagan.core.services.workspaces import RepoWorkspaceInput

    if not isinstance(value, list) or not value:
        return ParseError("repos must be a non-empty list")

    parsed: list[RepoWorkspaceInput] = []
    for item in value:
        if not isinstance(item, dict):
            return ParseError(
                "Each repos item must be an object with repo_id, repo_path, and target_branch"
            )
        repo_id = optional_str(item.get("repo_id"))
        repo_path = optional_str(item.get("repo_path"))
        target_branch = optional_str(item.get("target_branch"))
        if repo_id is None or repo_path is None or target_branch is None:
            return ParseError(
                "Each repos item must include non-empty repo_id, repo_path, and target_branch"
            )
        parsed.append(
            RepoWorkspaceInput(
                repo_id=repo_id,
                repo_path=repo_path,
                target_branch=target_branch,
            )
        )
    return parsed


def parse_timeout_seconds(value: object) -> float | None | ParseError:
    if value is None:
        return None
    timeout = float_or_none(value)
    if timeout is None:
        return ParseError("timeout_seconds must be a non-negative number", code="INVALID_TIMEOUT")
    if timeout < 0:
        return ParseError("timeout_seconds must be >= 0", code="INVALID_TIMEOUT")
    return timeout


def parse_events_limit(value: object) -> int | ParseError:
    if value is None:
        return DEFAULT_EVENTS_LIMIT
    if isinstance(value, bool) or not isinstance(value, int):
        return ParseError(f"limit must be an integer between 1 and {MAX_EVENTS_LIMIT}")
    if value < 1 or value > MAX_EVENTS_LIMIT:
        return ParseError(f"limit must be an integer between 1 and {MAX_EVENTS_LIMIT}")
    return value


def parse_events_offset(value: object) -> int | ParseError:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        return ParseError("offset must be an integer >= 0")
    if value < 0:
        return ParseError("offset must be an integer >= 0")
    return value


def parse_wait_timeout_seconds(
    value: object,
    *,
    default_timeout: int,
    max_timeout: int,
) -> float | ParseError:
    if value is None:
        return float(default_timeout)
    timeout_seconds = float_or_none(value)
    if timeout_seconds is None:
        return ParseError("timeout_seconds must be a positive number", code="INVALID_TIMEOUT")

    if timeout_seconds <= 0:
        return ParseError("timeout_seconds must be > 0", code="INVALID_TIMEOUT")
    if timeout_seconds > max_timeout:
        return ParseError(
            f"timeout_seconds exceeds server maximum of {max_timeout}s", code="INVALID_TIMEOUT"
        )
    return timeout_seconds


def parse_wait_for_status_filter(value: object) -> set[str] | ParseError | None:
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
                return ParseError("wait_for_status JSON string must decode to a list of statuses")
            if not isinstance(parsed, list):
                return ParseError("wait_for_status JSON string must decode to a list of statuses")
            values = parsed
        else:
            values = [part for part in normalized.split(",") if part.strip()]
    else:
        return ParseError("wait_for_status must be a list of status strings")

    valid_statuses = frozenset(TASK_STATUS_VALUES)
    parsed_statuses: set[str] = set()
    for raw_value in values:
        status = coerce_task_status(raw_value)
        if status is None:
            return ParseError(
                f"Invalid status filter value: {raw_value!r}. "
                f"Expected one of: {', '.join(sorted(valid_statuses))}"
            )
        parsed_statuses.add(status.value)

    if not parsed_statuses:
        return None
    return parsed_statuses


def parse_queue_lane(value: object) -> QueueLane:
    if value is None:
        return QueueLane.IMPLEMENTATION
    if (lane := coerce_queue_lane(value)) is not None:
        return lane
    raise ValueError(f"lane must be one of: {QUEUE_LANE_OPTIONS}")


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


def parse_json_dict_list(value: object, *, field_name: str) -> list[dict[str, Any]] | ParseError:
    if not isinstance(value, list):
        return ParseError(f"{field_name} must be a list")
    parsed: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            return ParseError(f"{field_name} items must be objects")
        parsed.append({str(key): val for key, val in item.items()})
    return parsed


__all__ = [
    "DEFAULT_EVENTS_LIMIT",
    "MAX_EVENTS_LIMIT",
    "ParseError",
    "build_task_update_fields",
    "is_parse_error",
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
