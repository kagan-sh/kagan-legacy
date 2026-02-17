"""Backward-compatible handler exports backed by CommandRouter command functions.

This compatibility surface exists for unit tests and transitional imports.
Runtime request dispatch now goes through ``CommandRouter`` in ``host.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from kagan.core.commands import automation, projects, tasks, workspaces

if TYPE_CHECKING:
    from kagan.core.api import KaganAPI

_DEFAULT_AUDIT_FIELD_CHAR_LIMIT = automation._DEFAULT_AUDIT_FIELD_CHAR_LIMIT
_MAX_WAIT_WINDOW_SECONDS = automation._MAX_WAIT_WINDOW_SECONDS


def _ctx(api: KaganAPI) -> Any:
    ctx = getattr(api, "_ctx", None)
    if ctx is None:
        raise ValueError("API context is not initialized")
    if getattr(ctx, "api", None) is None:
        ctx.api = api
    return ctx


async def handle_task_get(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.get_task(_ctx(api), params)


async def handle_task_list(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.list_tasks(_ctx(api), params)


async def handle_task_search(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.search_tasks(_ctx(api), params)


async def handle_task_scratchpad(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.get_scratchpad(_ctx(api), params)


async def handle_task_context(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.get_task_context(_ctx(api), params)


async def handle_task_logs(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.get_task_logs(_ctx(api), params)


async def handle_task_create(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.create_task(_ctx(api), params)


async def handle_task_update(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.update_task(_ctx(api), params)


async def handle_task_move(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.move_task(_ctx(api), params)


async def handle_task_delete(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.delete_task(_ctx(api), params)


async def handle_task_update_scratchpad(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await tasks.update_scratchpad(_ctx(api), params)


async def handle_task_wait(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    automation._MAX_WAIT_WINDOW_SECONDS = _MAX_WAIT_WINDOW_SECONDS
    return await automation.handle_task_wait(_ctx(api), params)


async def handle_review_request(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    from kagan.core.api import ReviewGuardrailBlockedError

    task_id = params["task_id"]
    summary = params.get("summary", "")
    try:
        task = await cast("Any", api).request_review(task_id, summary)
    except ReviewGuardrailBlockedError as exc:
        response: dict[str, Any] = {
            "success": False,
            "task_id": task_id,
            "code": exc.code,
            "message": exc.message,
        }
        if exc.hint is not None and exc.hint.strip():
            response["hint"] = exc.hint
        return response
    if task is None:
        return {
            "success": False,
            "task_id": task_id,
            "message": f"Task {task_id} not found. Check task_id with task_list.",
            "code": "TASK_NOT_FOUND",
        }
    return {
        "success": True,
        "task_id": task.id,
        "status": task.status.value,
        "code": "REVIEW_REQUESTED",
    }


async def handle_review_approve(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    from kagan.core.api import ReviewApprovalContextMissingError
    from kagan.core.domain.enums import TaskStatus

    task_id = params["task_id"]
    current_task = await cast("Any", api).get_task(task_id)
    if current_task is None:
        return {
            "success": False,
            "task_id": task_id,
            "message": f"Task {task_id} not found. Check task_id with task_list.",
            "code": "TASK_NOT_FOUND",
        }
    if current_task.status is not TaskStatus.REVIEW:
        return {
            "success": False,
            "task_id": task_id,
            "message": (
                f"Task is not in REVIEW (current: {current_task.status.value}). "
                "Move task to REVIEW before approving."
            ),
            "code": "REVIEW_NOT_READY",
            "hint": "Use task_patch with transition='request_review' to move task to REVIEW.",
        }

    try:
        task = await cast("Any", api).approve_task(task_id)
    except ReviewApprovalContextMissingError as exc:
        response: dict[str, Any] = {
            "success": False,
            "task_id": task_id,
            "code": exc.code,
            "message": exc.message,
        }
        if exc.hint is not None and exc.hint.strip():
            response["hint"] = exc.hint
        return response
    if task is None:
        return {
            "success": False,
            "task_id": task_id,
            "message": f"Task {task_id} not found. Check task_id with task_list.",
            "code": "TASK_NOT_FOUND",
        }
    return {
        "success": True,
        "task_id": task.id,
        "status": "approved",
        "task_status": task.status.value,
        "code": "APPROVED",
    }


async def handle_review_reject(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    feedback = params.get("feedback", "")
    action = params.get("action", "reopen")
    task = await cast("Any", api).reject_task(task_id, feedback, action)
    if task is None:
        return {
            "success": False,
            "task_id": task_id,
            "message": f"Task {task_id} not found. Check task_id with task_list.",
            "code": "TASK_NOT_FOUND",
        }
    return {"success": True, "task_id": task.id, "status": task.status.value, "code": "REJECTED"}


async def handle_review_merge(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_review_merge(_ctx(api), params)


async def handle_review_rebase(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_review_rebase(_ctx(api), params)


async def handle_job_submit(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_job_submit(_ctx(api), params)


async def handle_job_cancel(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_job_cancel(_ctx(api), params)


async def handle_job_get(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_job_get(_ctx(api), params)


async def handle_job_wait(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_job_wait(_ctx(api), params)


async def handle_job_events(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_job_events(_ctx(api), params)


async def handle_session_create(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_session_create(_ctx(api), params)


async def handle_session_attach(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_session_attach(_ctx(api), params)


async def handle_session_exists(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_session_exists(_ctx(api), params)


async def handle_session_kill(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await automation.handle_session_kill(_ctx(api), params)


async def handle_project_create(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.create_project(_ctx(api), params)


async def handle_project_open(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.open_project(_ctx(api), params)


async def handle_project_add_repo(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.add_repo(_ctx(api), params)


async def handle_project_get(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.get_project(_ctx(api), params)


async def handle_project_list(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.list_projects(_ctx(api), params)


async def handle_project_repos(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.get_project_repos(_ctx(api), params)


async def handle_project_find_by_repo_path(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.find_project_by_repo_path(_ctx(api), params)


async def handle_project_repo_details(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    ctx = _ctx(api)
    project_id = params["project_id"]
    repos = await cast("Any", ctx.api).get_project_repo_details(project_id)
    return {"repos": repos, "count": len(repos)}


async def handle_settings_get(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.get_settings(_ctx(api), params)


async def handle_settings_update(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.update_settings(_ctx(api), params)


async def handle_audit_list(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await projects.list_audit_events(_ctx(api), params)


async def handle_diagnostics_instrumentation(
    api: KaganAPI,
    params: dict[str, Any],
) -> dict[str, Any]:
    return await automation.handle_diagnostics_instrumentation(_ctx(api), params)


async def handle_tui_api_call(api: KaganAPI, params: dict[str, Any]) -> dict[str, Any]:
    return await workspaces.handle_tui_api_call(_ctx(api), params)


__all__ = [
    "_DEFAULT_AUDIT_FIELD_CHAR_LIMIT",
    "_MAX_WAIT_WINDOW_SECONDS",
    "handle_audit_list",
    "handle_diagnostics_instrumentation",
    "handle_job_cancel",
    "handle_job_events",
    "handle_job_get",
    "handle_job_submit",
    "handle_job_wait",
    "handle_project_add_repo",
    "handle_project_create",
    "handle_project_find_by_repo_path",
    "handle_project_get",
    "handle_project_list",
    "handle_project_open",
    "handle_project_repo_details",
    "handle_project_repos",
    "handle_review_approve",
    "handle_review_merge",
    "handle_review_rebase",
    "handle_review_reject",
    "handle_review_request",
    "handle_session_attach",
    "handle_session_create",
    "handle_session_exists",
    "handle_session_kill",
    "handle_settings_get",
    "handle_settings_update",
    "handle_task_context",
    "handle_task_create",
    "handle_task_delete",
    "handle_task_get",
    "handle_task_list",
    "handle_task_logs",
    "handle_task_move",
    "handle_task_scratchpad",
    "handle_task_search",
    "handle_task_update",
    "handle_task_update_scratchpad",
    "handle_task_wait",
    "handle_tui_api_call",
]
