from __future__ import annotations

from enum import StrEnum
from typing import Any

from kagan.core.scalars import non_empty_str


class CommandCode(StrEnum):
    """Canonical command response codes shared by command handlers."""

    INVALID_PARAMS = "INVALID_PARAMS"
    INVALID_LANE = "INVALID_LANE"
    INVALID_EVENT = "INVALID_EVENT"
    INVALID_JOB_ID = "INVALID_JOB_ID"
    INVALID_TASK_ID = "INVALID_TASK_ID"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_TIMEOUT = "JOB_TIMEOUT"
    QUEUED = "QUEUED"
    QUEUE_EMPTY = "QUEUE_EMPTY"
    MESSAGE_TAKEN = "MESSAGE_TAKEN"
    REMOVED = "REMOVED"
    NOT_FOUND = "NOT_FOUND"
    NO_EXECUTIONS = "NO_EXECUTIONS"


def _code_value(code: CommandCode | str) -> str:
    return code.value if isinstance(code, CommandCode) else code


def error_response(
    *,
    message: str,
    code: CommandCode | str,
    **fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "message": message,
        "code": _code_value(code),
    }
    payload.update(fields)
    return payload


def invalid_params_response(message: str, **fields: Any) -> dict[str, Any]:
    return error_response(message=message, code=CommandCode.INVALID_PARAMS, **fields)


def required_param_response(param_name: str, **fields: Any) -> dict[str, Any]:
    return invalid_params_response(f"{param_name} is required", **fields)


def require_non_empty_param(
    params: dict[str, Any],
    param_name: str,
) -> tuple[str | None, dict[str, Any] | None]:
    value = non_empty_str(params.get(param_name))
    if value is None:
        return None, required_param_response(param_name)
    return value, None


def invalid_job_id_response() -> dict[str, Any]:
    return error_response(
        message="job_id is required. Get the job_id from a previous job_start response.",
        code=CommandCode.INVALID_JOB_ID,
    )


def invalid_task_id_response(job_id: str) -> dict[str, Any]:
    return error_response(
        message="task_id is required. Use task_list to find valid task IDs.",
        code=CommandCode.INVALID_TASK_ID,
        job_id=job_id,
    )


def job_not_found_response(job_id: str, task_id: str) -> dict[str, Any]:
    return error_response(
        message="Job not found. Verify job_id and task_id, or submit a new job with job_start.",
        code=CommandCode.JOB_NOT_FOUND,
        job_id=job_id,
        task_id=task_id,
    )


__all__ = [
    "CommandCode",
    "error_response",
    "invalid_job_id_response",
    "invalid_params_response",
    "invalid_task_id_response",
    "job_not_found_response",
    "require_non_empty_param",
    "required_param_response",
]
