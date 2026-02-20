"""Tool registration closures for full-mode and plugin MCP tools.

Extracted from server.py to separate lifecycle/setup from tool registration.
Each tool is a closure capturing SDK/profile dependencies passed as parameters.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from kagan.core.domain.coercion import coerce_task_type
from kagan.core.policy import CapabilityProfile
from kagan.core.scalars import (
    dict_str_keys_or_none,
    str_or_none,
    strict_int_or_none,
)
from kagan.core.settings import build_settings_set_fields
from kagan.mcp._response_models import (
    InstrumentationSnapshotResponse,
    JobActionInput,
    JobEvent,
    JobEventsResponse,
    JobResponse,
    ProjectOpenResponse,
    RejectionActionInput,
    ReviewActionInput,
    ReviewActionResponse,
    SessionActionInput,
    SettingsGetResponse,
    SettingsUpdateResponse,
    TaskCreateResponse,
    TaskDeleteResponse,
    TaskTypeInput,
)
from kagan.mcp._tool_policy import (
    DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
    JOB_NON_TERMINAL_STATUSES,
    PROTOCOL_CALLS,
    is_allowed,
)
from kagan.mcp.tools import (
    mcp_append_task_note,
    mcp_get_instrumentation_snapshot,
    mcp_request_review,
    mcp_update_scratchpad,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcp.server.fastmcp import FastMCP


# Use Any for lifespan context to avoid circular import with server.MCPLifespanContext
MCPContext = Context[ServerSession, Any]


# Local aliases preserve existing call sites while sharing implementation.
_str_or_none = str_or_none
_dict_or_none = dict_str_keys_or_none
_int_or_none = strict_int_or_none


def _normalized_mode(value: str | None) -> str | None:
    """Return 'AUTO' or 'PAIR' if value is a task_type, else None."""
    if value is None:
        return None
    normalized = coerce_task_type(value)
    if normalized is None:
        return None
    return normalized.value


def _register_plugin_tools(
    mcp: FastMCP,
    *,
    effective_profile: str,
    require_transport_fn: Callable[..., Any] | None = None,
    build_plugin_registry_fn: Callable[..., Any] | None = None,
) -> None:
    """Register MCP tools contributed by plugins via McpToolSchema descriptors."""
    from kagan.mcp._response_models import PluginToolResponse

    _MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
    _READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

    _JSON_TYPE_TO_PYTHON: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    if require_transport_fn is None or build_plugin_registry_fn is None:
        from kagan.mcp.server import (
            _build_plugin_registry,
            _require_transport,
        )

        _get_transport = require_transport_fn or _require_transport
        _get_registry = build_plugin_registry_fn or _build_plugin_registry
    else:
        _get_transport = require_transport_fn
        _get_registry = build_plugin_registry_fn

    registry = _get_registry()
    if registry is None:
        return

    _PROFILE_RANK: dict[str, int] = {
        str(CapabilityProfile.VIEWER): 0,
        str(CapabilityProfile.PLANNER): 1,
        str(CapabilityProfile.PAIR_WORKER): 2,
        str(CapabilityProfile.OPERATOR): 3,
        str(CapabilityProfile.MAINTAINER): 4,
    }
    caller_rank = _PROFILE_RANK.get(effective_profile, 0)

    for operation in registry.all_operations():
        schema = operation.mcp_tool_schema
        if schema is None:
            continue

        op_min_rank = _PROFILE_RANK.get(str(operation.minimum_profile), 4)
        if caller_rank < op_min_rank:
            continue

        tool_name = schema.tool_name
        annotation = _READ_ONLY if schema.annotations == "read_only" else _MUTATING
        cap = operation.capability
        method = operation.method
        plugin_id = operation.plugin_id

        def _make_handler(
            _cap: str, _method: str, _plugin_id: str, _params: dict[str, Any]
        ) -> Callable[..., Any]:
            async def handler(ctx: MCPContext | None = None, **kwargs: Any) -> PluginToolResponse:
                op = registry.resolve_operation(_cap, _method)
                if op is None:
                    return PluginToolResponse(
                        success=False,
                        plugin_id=_plugin_id,
                        capability=_cap,
                        method=_method,
                        code="PLUGIN_OPERATION_NOT_REGISTERED",
                        message=f"Plugin operation is not registered: {_cap}.{_method}",
                        hint=(
                            "Restart MCP to refresh plugin discovery, or install/enable "
                            "the plugin that provides this capability."
                        ),
                        data={},
                    )
                transport = _get_transport(ctx)
                raw = await transport.request(op.capability, op.method, kwargs or None)
                return PluginToolResponse(
                    success=bool(raw.get("success", True)),
                    message=raw.get("message"),
                    code=raw.get("code"),
                    hint=raw.get("hint"),
                    next_tool=raw.get("next_tool"),
                    next_arguments=raw.get("next_arguments"),
                    plugin_id=raw.get("plugin_id", op.plugin_id),
                    capability=op.capability,
                    method=op.method,
                    data={k: v for k, v in raw.items() if k not in ("success", "message")},
                )

            sig_params: list[inspect.Parameter] = [
                inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
            ]
            for param_name, param_spec in _params.items():
                py_annotation = _JSON_TYPE_TO_PYTHON.get(param_spec.get("type", ""), str)
                if param_spec.get("required", False):
                    sig_params.append(
                        inspect.Parameter(
                            param_name,
                            inspect.Parameter.KEYWORD_ONLY,
                            annotation=py_annotation,
                        ),
                    )
                else:
                    sig_params.append(
                        inspect.Parameter(
                            param_name,
                            inspect.Parameter.KEYWORD_ONLY,
                            default=None,
                            annotation=py_annotation | None,
                        ),
                    )
            handler.__signature__ = inspect.Signature(  # type: ignore[attr-defined]  # noqa: B023
                sig_params, return_annotation=PluginToolResponse
            )
            return handler  # noqa: B023

        handler = _make_handler(cap, method, plugin_id, schema.parameters)
        handler.__name__ = tool_name
        handler.__qualname__ = tool_name
        handler.__doc__ = schema.description
        mcp.tool(annotations=annotation)(handler)


def _register_full_mode_tools(
    mcp: FastMCP,
    *,
    allows_all: Callable[..., bool],
    effective_profile: str,
    enable_internal_instrumentation: bool = False,
    require_transport_fn: Callable[..., Any] | None = None,
    runtime_state_fn: Callable[..., Any] | None = None,
    build_plugin_registry_fn: Callable[..., Any] | None = None,
) -> None:
    """Register mutating/full-mode-only MCP tools."""
    if require_transport_fn is None or runtime_state_fn is None:
        from kagan.mcp.server import (
            _require_transport,
            _runtime_state_from_raw,
        )

        _get_transport = require_transport_fn or _require_transport
        _get_runtime_state = runtime_state_fn or _runtime_state_from_raw
    else:
        _get_transport = require_transport_fn
        _get_runtime_state = runtime_state_fn

    _READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
    _MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
    _DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)

    _PROTOCOL = PROTOCOL_CALLS

    can_create = allows_all(_PROTOCOL["tasks_create"])
    can_patch_note = allows_all(_PROTOCOL["tasks_update_scratchpad"])
    can_patch_fields = allows_all(_PROTOCOL["tasks_update"])
    can_patch_status = allows_all(_PROTOCOL["tasks_move"])
    can_delete = allows_all(_PROTOCOL["tasks_delete"])
    can_request_review = allows_all(_PROTOCOL["review_request"])

    if can_create:

        @mcp.tool(annotations=_MUTATING)
        async def task_create(
            title: str,
            description: str = "",
            project_id: str | None = None,
            status: str | None = None,
            priority: str | None = None,
            task_type: TaskTypeInput | None = None,
            terminal_backend: str | None = None,
            agent_backend: str | None = None,
            parent_id: str | None = None,
            base_branch: str | None = None,
            acceptance_criteria: list[str] | str | None = None,
            created_by: str | None = None,
            ctx: MCPContext | None = None,
        ) -> TaskCreateResponse:
            """Create a new task."""
            transport = _get_transport(ctx)
            params_create: dict[str, Any] = {"title": title, "description": description}
            if project_id:
                params_create["project_id"] = project_id
            if status is not None:
                params_create["status"] = status
            if priority is not None:
                params_create["priority"] = priority
            if task_type is not None:
                params_create["task_type"] = task_type
            if terminal_backend is not None:
                params_create["terminal_backend"] = terminal_backend
            if agent_backend is not None:
                params_create["agent_backend"] = agent_backend
            if parent_id is not None:
                params_create["parent_id"] = parent_id
            if base_branch is not None:
                params_create["base_branch"] = base_branch
            if acceptance_criteria is not None:
                params_create["acceptance_criteria"] = acceptance_criteria
            if created_by is not None:
                params_create["created_by"] = created_by
            raw = await transport.request("tasks", "create", params_create)
            return TaskCreateResponse(
                success=bool(raw.get("success", True)),
                message=raw.get("message"),
                code=raw.get("code"),
                hint=raw.get("hint"),
                next_tool=raw.get("next_tool"),
                next_arguments=raw.get("next_arguments"),
                task_id=raw.get("task_id", ""),
                title=raw.get("title", title),
                status=raw.get("status", "backlog"),
            )

    if can_patch_note or can_patch_fields or can_patch_status or can_request_review:

        @mcp.tool(annotations=_MUTATING)
        async def task_patch(
            task_id: str,
            set: dict[str, object] | None = None,
            transition: str | None = None,
            append_note: str | None = None,
            ctx: MCPContext | None = None,
        ) -> dict[str, object]:
            """Apply partial task changes, transitions, and scratchpad notes."""
            transport = _get_transport(ctx)
            if set is not None and not isinstance(set, dict):
                return {
                    "success": False,
                    "task_id": task_id,
                    "message": "set must be an object map",
                    "code": "INVALID_SET",
                }

            fields = dict(set) if isinstance(set, dict) else {}

            if append_note is not None:
                if not can_patch_note:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "append_note is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                note_raw = await mcp_update_scratchpad(transport, task_id, append_note)
                if not bool(note_raw.get("success", False)):
                    return {
                        "success": False,
                        "task_id": task_id,
                        "code": note_raw.get("code"),
                        "message": note_raw.get("message"),
                    }

            status_for_move = fields.pop("status", None)

            if transition == "set_status":
                if status_for_move is None:
                    status_for_move = fields.pop("new_status", None)
                if not isinstance(status_for_move, str) or not status_for_move.strip():
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "set_status requires set.status",
                        "code": "INVALID_TRANSITION",
                    }
                mode_value = _normalized_mode(status_for_move)
                if mode_value is not None:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": (
                            f"Invalid status value {status_for_move!r}. "
                            "AUTO/PAIR are task_type values, not status values."
                        ),
                        "code": "TASK_TYPE_VALUE_IN_STATUS",
                        "hint": "Use transition='set_task_type' with set.task_type.",
                        "next_tool": "task_patch",
                        "next_arguments": {
                            "task_id": task_id,
                            "transition": "set_task_type",
                            "set": {"task_type": mode_value},
                        },
                    }
                if not can_patch_status:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "set_status is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await transport.request(
                    "tasks", "move", {"task_id": task_id, "status": status_for_move}
                )
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            if transition == "set_task_type":
                task_type_value = fields.get("task_type")
                if not isinstance(task_type_value, str) or not task_type_value.strip():
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "set_task_type requires set.task_type",
                        "code": "INVALID_TRANSITION",
                    }
                if not can_patch_fields:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": ("set_task_type is not allowed for this capability profile."),
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await transport.request(
                    "tasks", "update", {"task_id": task_id, "task_type": task_type_value}
                )
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            if transition == "request_review":
                if not can_request_review:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": ("request_review is not allowed for this capability profile."),
                        "code": "ACTION_NOT_ALLOWED",
                    }
                summary_raw = fields.pop("summary", "")
                summary = summary_raw if isinstance(summary_raw, str) else ""
                raw = await mcp_request_review(transport, task_id, summary)
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            if transition is not None:
                return {
                    "success": False,
                    "task_id": task_id,
                    "message": (
                        f"Unsupported transition {transition!r}. "
                        "Valid transitions: set_status, set_task_type, request_review."
                    ),
                    "code": "INVALID_TRANSITION",
                }

            if status_for_move is not None:
                if not can_patch_status:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "status patch is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await transport.request(
                    "tasks", "move", {"task_id": task_id, "status": status_for_move}
                )
                if not bool(raw.get("success", False)):
                    return {"success": False, "task_id": task_id, **raw}

            if fields:
                if not can_patch_fields:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "field patch is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await transport.request("tasks", "update", {"task_id": task_id, **fields})
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            return {"success": True, "task_id": task_id, "message": "Patch applied"}

    if can_patch_note:

        @mcp.tool(annotations=_MUTATING)
        async def task_annotate(
            task_id: str,
            note: str,
            ctx: MCPContext | None = None,
        ) -> dict[str, object]:
            """Append a timestamped reasoning note to a task's scratchpad.

            Use during execution to record decisions, tradeoffs, and observations.
            Appends without overwriting existing notes.
            """
            transport = _get_transport(ctx)
            return await mcp_append_task_note(transport, task_id, note)

    if can_delete:

        @mcp.tool(annotations=_DESTRUCTIVE)
        async def task_delete(
            task_id: str,
            ctx: MCPContext | None = None,
        ) -> TaskDeleteResponse:
            """Delete a task."""
            transport = _get_transport(ctx)
            raw = await transport.request("tasks", "delete", {"task_id": task_id})
            return TaskDeleteResponse(
                success=bool(raw.get("success", False)),
                message=raw.get("message"),
                code=raw.get("code"),
                hint=raw.get("hint"),
                next_tool=raw.get("next_tool"),
                next_arguments=raw.get("next_arguments"),
                task_id=task_id,
            )

    # --- Job tools ---

    if allows_all(_PROTOCOL["jobs_submit"]):

        @mcp.tool(annotations=_MUTATING)
        async def job_start(
            task_id: str,
            action: JobActionInput,
            arguments: dict[str, object] | None = None,
            ctx: MCPContext | None = None,
        ) -> JobResponse:
            """Submit an asynchronous core job."""
            transport = _get_transport(ctx)
            params_job: dict[str, Any] = {"task_id": task_id, "action": action}
            if arguments is not None:
                params_job["arguments"] = arguments
            raw = await transport.request("jobs", "submit", params_job)
            job_id = _str_or_none(raw.get("job_id")) or ""
            returned_task_id = _str_or_none(raw.get("task_id")) or task_id
            success = bool(raw.get("success", False))
            next_tool = _str_or_none(raw.get("next_tool"))
            next_arguments = _dict_or_none(raw.get("next_arguments"))
            hint = _str_or_none(raw.get("hint"))
            if success and next_tool is None and job_id:
                next_tool = "job_poll"
                next_arguments = {
                    "job_id": job_id,
                    "task_id": returned_task_id,
                    "wait": True,
                    "timeout_seconds": DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
                }
            return JobResponse(
                success=success,
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=hint,
                next_tool=next_tool,
                next_arguments=next_arguments,
                job_id=job_id,
                task_id=returned_task_id,
                action=_str_or_none(raw.get("action")) or str(action),
                status=_str_or_none(raw.get("status")),
            )

    if (
        allows_all(_PROTOCOL["jobs_get"])
        or allows_all(_PROTOCOL["jobs_wait"])
        or allows_all(_PROTOCOL["jobs_events"])
    ):

        @mcp.tool(annotations=_READ_ONLY)
        async def job_poll(
            job_id: str,
            task_id: str,
            wait: bool = False,
            timeout_seconds: float = DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
            events: bool = False,
            limit: int = 50,
            offset: int = 0,
            ctx: MCPContext | None = None,
        ) -> JobResponse | JobEventsResponse:
            """Read job state, optionally waiting or paging events."""
            transport = _get_transport(ctx)
            if events:
                raw = await transport.query(
                    "jobs",
                    "events",
                    {
                        "job_id": job_id,
                        "task_id": task_id,
                        "limit": limit,
                        "offset": offset,
                    },
                )
                event_items: list[JobEvent] = []
                events_raw = raw.get("events")
                if isinstance(events_raw, list):
                    for raw_event in events_raw:
                        if not isinstance(raw_event, dict):
                            continue
                        event_items.append(
                            JobEvent(
                                job_id=_str_or_none(raw_event.get("job_id")),
                                task_id=_str_or_none(raw_event.get("task_id")),
                                status=_str_or_none(raw_event.get("status")),
                                timestamp=_str_or_none(raw_event.get("timestamp")),
                                message=_str_or_none(raw_event.get("message")),
                                code=_str_or_none(raw_event.get("code")),
                            )
                        )
                total_events = _int_or_none(raw.get("total_events"))
                returned_events = _int_or_none(raw.get("returned_events"))
                page_offset = _int_or_none(raw.get("offset"))
                page_limit = _int_or_none(raw.get("limit"))
                next_offset = _int_or_none(raw.get("next_offset"))
                has_more_val = raw.get("has_more")
                has_more = (
                    has_more_val if isinstance(has_more_val, bool) else next_offset is not None
                )
                return JobEventsResponse(
                    success=bool(raw.get("success", False)),
                    message=_str_or_none(raw.get("message")),
                    code=_str_or_none(raw.get("code")),
                    job_id=_str_or_none(raw.get("job_id")) or job_id,
                    task_id=_str_or_none(raw.get("task_id")) or task_id,
                    events=event_items,
                    total_events=(total_events if total_events is not None else len(event_items)),
                    returned_events=(
                        returned_events if returned_events is not None else len(event_items)
                    ),
                    offset=page_offset if page_offset is not None else offset,
                    limit=page_limit if page_limit is not None else limit,
                    has_more=has_more,
                    next_offset=next_offset,
                )

            if wait:
                params_wait: dict[str, Any] = {"job_id": job_id, "task_id": task_id}
                if timeout_seconds is not None:
                    params_wait["timeout_seconds"] = timeout_seconds
                raw = await transport.query("jobs", "wait", params_wait)
            else:
                raw = await transport.query("jobs", "get", {"job_id": job_id, "task_id": task_id})

            result = _dict_or_none(raw.get("result"))
            success = bool(raw.get("success", False))
            status = _str_or_none(raw.get("status"))
            code = _str_or_none(raw.get("code"))
            if code is None and result is not None:
                code = _str_or_none(result.get("code"))
            message = _str_or_none(raw.get("message"))
            if message is None and result is not None:
                message = _str_or_none(result.get("message"))

            timed_out_val = raw.get("timed_out")
            if not isinstance(timed_out_val, bool) and result is not None:
                timed_out_val = result.get("timed_out")
            timed_out = timed_out_val if isinstance(timed_out_val, bool) else None

            # Derive success for non-terminal/pending states (but not timeouts)
            if not success and not timed_out and status in JOB_NON_TERMINAL_STATUSES:
                success = True
            if (
                not success
                and result is not None
                and _str_or_none(result.get("code")) == "START_PENDING"
            ):
                success = True
                code = "START_PENDING"

            # Timeout metadata
            timeout_metadata: dict[str, object] | None = None
            timeout_fields: dict[str, object] = {}
            for source in (raw, result or {}):
                for key, value in source.items():
                    if key.startswith("timeout_"):
                        timeout_fields[key] = value
            if timeout_fields:
                timeout_metadata = timeout_fields

            next_tool = _str_or_none(raw.get("next_tool"))
            next_arguments = _dict_or_none(raw.get("next_arguments"))
            hint = _str_or_none(raw.get("hint"))

            # Derive recovery for non-terminal / timed-out states
            if next_tool is None and (
                status in JOB_NON_TERMINAL_STATUSES or timed_out or code == "START_PENDING"
            ):
                next_tool = "job_poll"
                next_arguments = {
                    "job_id": job_id,
                    "task_id": task_id,
                    "wait": True,
                    "timeout_seconds": DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
                }

            runtime_raw = _dict_or_none(raw.get("runtime"))
            if runtime_raw is None and result is not None:
                runtime_raw = _dict_or_none(result.get("runtime"))

            return JobResponse(
                success=success,
                message=message,
                code=code,
                hint=hint,
                next_tool=next_tool,
                next_arguments=next_arguments,
                job_id=_str_or_none(raw.get("job_id")) or job_id,
                task_id=_str_or_none(raw.get("task_id")) or task_id,
                action=_str_or_none(raw.get("action")),
                status=status,
                timed_out=timed_out,
                timeout_metadata=timeout_metadata,
                result=result,
                runtime=_get_runtime_state(runtime_raw),
            )

    if allows_all(_PROTOCOL["jobs_cancel"]):

        @mcp.tool(annotations=_MUTATING)
        async def job_cancel(
            job_id: str,
            task_id: str,
            ctx: MCPContext | None = None,
        ) -> JobResponse:
            """Cancel a submitted job."""
            transport = _get_transport(ctx)
            raw = await transport.request("jobs", "cancel", {"job_id": job_id, "task_id": task_id})
            success = bool(raw.get("success", False))
            next_tool = _str_or_none(raw.get("next_tool"))
            next_arguments = _dict_or_none(raw.get("next_arguments"))
            hint = _str_or_none(raw.get("hint"))
            if success and next_tool is None:
                next_tool = "job_poll"
                next_arguments = {
                    "job_id": job_id,
                    "task_id": task_id,
                    "wait": True,
                    "timeout_seconds": DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
                }
            return JobResponse(
                success=success,
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=hint,
                next_tool=next_tool,
                next_arguments=next_arguments,
                job_id=_str_or_none(raw.get("job_id")) or job_id,
                task_id=_str_or_none(raw.get("task_id")) or task_id,
                action=_str_or_none(raw.get("action")),
                status=_str_or_none(raw.get("status")),
            )

    # --- Review tool ---

    if (
        allows_all(_PROTOCOL["review_approve"])
        or allows_all(_PROTOCOL["review_reject"])
        or allows_all(_PROTOCOL["review_merge"])
        or allows_all(_PROTOCOL["review_rebase"])
    ):

        @mcp.tool(annotations=_DESTRUCTIVE)
        async def review_apply(
            task_id: str,
            action: ReviewActionInput,
            feedback: str = "",
            rejection_action: RejectionActionInput = "reopen",
            ctx: MCPContext | None = None,
        ) -> ReviewActionResponse:
            """Perform a review action on a task."""
            transport = _get_transport(ctx)
            if not is_allowed(effective_profile, "review", action):
                return ReviewActionResponse(
                    success=False,
                    task_id=task_id,
                    message=(f"Action '{action}' is not allowed for this capability profile."),
                    code="ACTION_NOT_ALLOWED",
                )
            params_review: dict[str, Any] = {"task_id": task_id}
            if action == "reject":
                params_review["feedback"] = feedback
                params_review["action"] = rejection_action
            raw = await transport.request("review", action, params_review)
            return ReviewActionResponse(
                success=bool(raw.get("success", False)),
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=_str_or_none(raw.get("hint")),
                next_tool=_str_or_none(raw.get("next_tool")),
                next_arguments=_dict_or_none(raw.get("next_arguments")),
                task_id=raw.get("task_id", task_id),
            )

    # --- Diagnostics ---

    if enable_internal_instrumentation and allows_all(_PROTOCOL["diagnostics_instrumentation"]):

        @mcp.tool(annotations=_READ_ONLY)
        async def diagnostics_instrumentation(
            ctx: MCPContext | None = None,
        ) -> InstrumentationSnapshotResponse:
            """Get internal in-memory core instrumentation snapshot."""
            transport = _get_transport(ctx)
            raw = await mcp_get_instrumentation_snapshot(transport)

            counters: dict[str, int] = {}
            counters_raw = raw.get("counters", {})
            if isinstance(counters_raw, dict):
                for key, value in counters_raw.items():
                    if isinstance(value, int):
                        counters[str(key)] = value

            timings: dict[str, dict[str, float | int]] = {}
            timings_raw = raw.get("timings", {})
            if isinstance(timings_raw, dict):
                for metric_name, stats in timings_raw.items():
                    if not isinstance(stats, dict):
                        continue
                    normalized: dict[str, float | int] = {}
                    for field_name, field_value in stats.items():
                        if isinstance(field_value, int | float):
                            normalized[str(field_name)] = field_value
                    timings[str(metric_name)] = normalized

            return InstrumentationSnapshotResponse(
                enabled=bool(raw.get("enabled", False)),
                log_events=bool(raw.get("log_events", False)),
                counters=counters,
                timings=timings,
            )

    # --- Settings ---

    if allows_all(_PROTOCOL["settings_get"]):

        @mcp.tool(annotations=_READ_ONLY)
        async def settings_get(
            ctx: MCPContext | None = None,
        ) -> SettingsGetResponse:
            """Get MCP-exposed settings snapshot."""
            transport = _get_transport(ctx)
            raw = await transport.query("settings", "get", {})
            return SettingsGetResponse(settings=raw.get("settings", {}))

    if allows_all(_PROTOCOL["settings_update"]):

        @mcp.tool(annotations=_MUTATING)
        async def settings_set(
            auto_review: bool | None = None,
            auto_approve: bool | None = None,
            auto_skill_discovery: bool | None = None,
            require_review_approval: bool | None = None,
            serialize_merges: bool | None = None,
            worktree_base_ref_strategy: str | None = None,
            max_concurrent_agents: int | None = None,
            default_worker_agent: str | None = None,
            worker_persona: str | None = None,
            orchestrator_persona: str | None = None,
            pr_reviewer_persona: str | None = None,
            default_pair_terminal_backend: str | None = None,
            doctor_verbosity: str | None = None,
            interaction_verbosity: str | None = None,
            default_model_claude: str | None = None,
            default_model_opencode: str | None = None,
            default_model_codex: str | None = None,
            default_model_gemini: str | None = None,
            default_model_kimi: str | None = None,
            default_model_copilot: str | None = None,
            default_model_goose: str | None = None,
            default_model_openhands: str | None = None,
            default_model_auggie: str | None = None,
            default_model_amp: str | None = None,
            default_model_cagent: str | None = None,
            default_model_stakpak: str | None = None,
            default_model_vibe: str | None = None,
            default_model_vtcode: str | None = None,
            tasks_wait_default_timeout_seconds: int | None = None,
            tasks_wait_max_timeout_seconds: int | None = None,
            skip_pair_instructions: bool | None = None,
            theme: str | None = None,
            ctx: MCPContext | None = None,
        ) -> SettingsUpdateResponse:
            """Update allowlisted settings fields."""
            transport = _get_transport(ctx)
            fields = build_settings_set_fields(locals())
            raw = await transport.request("settings", "update", {"fields": fields})
            return SettingsUpdateResponse(
                success=bool(raw.get("success", False)),
                message=raw.get("message"),
                code=raw.get("code"),
                hint=raw.get("hint"),
                next_tool=raw.get("next_tool"),
                next_arguments=raw.get("next_arguments"),
                updated=raw.get("updated", {}),
                settings=raw.get("settings", {}),
            )

    # --- Session tool ---

    if (
        allows_all(_PROTOCOL["sessions_create"])
        or allows_all(_PROTOCOL["sessions_exists"])
        or allows_all(_PROTOCOL["sessions_kill"])
    ):

        @mcp.tool(annotations=_MUTATING)
        async def session_manage(
            action: SessionActionInput,
            task_id: str,
            reuse_if_exists: bool = True,
            worktree_path: str | None = None,
            ctx: MCPContext | None = None,
        ) -> dict[str, object]:
            """Manage PAIR sessions with a single action-oriented interface."""
            transport = _get_transport(ctx)
            if action == "open":
                params_sess: dict[str, Any] = {
                    "task_id": task_id,
                    "reuse_if_exists": reuse_if_exists,
                }
                if worktree_path is not None:
                    params_sess["worktree_path"] = worktree_path
                raw = await transport.request("sessions", "create", params_sess)
                return {
                    "success": bool(raw.get("success", False)),
                    "action": action,
                    "task_id": raw.get("task_id", task_id),
                    **{k: v for k, v in raw.items() if k != "success"},
                }
            if action == "read":
                raw = await transport.request("sessions", "exists", {"task_id": task_id})
                return {
                    "success": True,
                    "action": action,
                    "task_id": raw.get("task_id", task_id),
                    "exists": raw.get("exists", False),
                }
            if action == "close":
                raw = await transport.request("sessions", "kill", {"task_id": task_id})
                return {
                    "success": bool(raw.get("success", False)),
                    "action": action,
                    "task_id": raw.get("task_id", task_id),
                }
            return {
                "success": False,
                "task_id": task_id,
                "code": "INVALID_ACTION",
                "message": f"Unsupported session action {action!r}.",
            }

    # --- Project open ---

    if allows_all(_PROTOCOL["projects_open"]):

        @mcp.tool(annotations=_MUTATING)
        async def project_open(
            project_id: str,
            ctx: MCPContext | None = None,
        ) -> ProjectOpenResponse:
            """Open/switch to a project."""
            transport = _get_transport(ctx)
            raw = await transport.request("projects", "open", {"project_id": project_id})
            return ProjectOpenResponse(
                success=bool(raw.get("success", True)),
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=_str_or_none(raw.get("hint")),
                next_tool=_str_or_none(raw.get("next_tool")),
                next_arguments=_dict_or_none(raw.get("next_arguments")),
                project_id=raw.get("project_id", project_id),
                name=raw.get("name", ""),
            )

    # --- Plugin tools ---
    if build_plugin_registry_fn is None:
        from kagan.mcp.server import _build_plugin_registry

        build_plugin_registry_fn = _build_plugin_registry

    _register_plugin_tools(
        mcp,
        effective_profile=effective_profile,
        require_transport_fn=_get_transport,
        build_plugin_registry_fn=build_plugin_registry_fn,
    )
