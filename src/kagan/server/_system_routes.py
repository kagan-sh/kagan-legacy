from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kagan.cli.doctor import run_doctor_checks
from kagan.core import TaskStatus, detect_dotfile_overrides
from kagan.server._access import AccessTier
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    require_context,
)
from kagan.server._presence import (
    MAX_PRESENCE_CLIENT_ID,
    MAX_PRESENCE_CLIENT_TYPE,
    MAX_PRESENCE_TASK_ID,
    MAX_PRESENCE_USER_LABEL,
    sanitize_presence_text,
)
from kagan.server._sse import _sse_event_generator, sse_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

_DEFAULT_WIP_LIMITS = {
    TaskStatus.BACKLOG.value: 0,
    TaskStatus.IN_PROGRESS.value: 4,
    TaskStatus.REVIEW.value: 2,
    TaskStatus.DONE.value: 0,
}


def _parse_wip_limits(raw: str | None) -> dict[str, int]:
    if not raw:
        return dict(_DEFAULT_WIP_LIMITS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return dict(_DEFAULT_WIP_LIMITS)
    if not isinstance(parsed, dict):
        return dict(_DEFAULT_WIP_LIMITS)

    limits = dict(_DEFAULT_WIP_LIMITS)
    for key, value in parsed.items():
        if key not in limits:
            continue
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            continue
        limits[key] = max(0, parsed_value)
    return limits


async def _resolve_project_repo_path(client: Any, settings: dict[str, str]) -> Path | None:
    return await client.projects.resolve_repo_path(settings=settings)


def register_system_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/settings", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_settings(_request: Request, *, ctx: Any) -> JSONResponse:
        settings = await ctx.client.settings.get()
        return _ok(settings)

    @mcp.custom_route("/api/settings", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def set_settings(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Settings changes", minimum_tier=AccessTier.ADMIN
        )
        if forbidden is not None:
            return forbidden
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        updates = {str(key): "" if value is None else str(value) for key, value in payload.items()}
        await ctx.client.settings.set(updates)
        return _ok(await ctx.client.settings.get())

    @mcp.custom_route("/api/settings/resolved", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_resolved_settings(_request: Request, *, ctx: Any) -> JSONResponse:
        settings = await ctx.client.settings.get()

        from kagan.core.git import get_git_user_identity

        git_name, git_email = await get_git_user_identity(settings)

        project_path = await _resolve_project_repo_path(ctx.client, settings)
        overrides = detect_dotfile_overrides(project_path)

        return _ok(
            {
                "git_user_name": git_name,
                "git_user_email": git_email,
                "dotfile_overrides": {
                    "orchestrator": (
                        str(overrides["orchestrator"]) if "orchestrator" in overrides else None
                    ),
                    "execution": (
                        str(overrides["execution"]) if "execution" in overrides else None
                    ),
                    "review": str(overrides["review"]) if "review" in overrides else None,
                },
                "workflow": {"wip_limits": _parse_wip_limits(settings.get("workflow.wip_limits"))},
                "chat_last_active_session": settings.get("chat_last_active_session", ""),
            }
        )

    @mcp.custom_route("/api/fs/browse", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def browse_filesystem(request: Request, *, ctx: Any) -> JSONResponse:
        import asyncio

        raw_path = request.query_params.get("path", "~")

        def _list_dir(raw: str) -> dict[str, Any]:
            target = Path(raw).expanduser().resolve()
            if not target.is_relative_to(Path.home()):
                raise ValueError("Path outside allowed boundaries")
            if not target.is_dir():
                raise ValueError("Invalid path: not a directory")

            entries: list[dict[str, Any]] = []
            try:
                with os.scandir(target) as it:
                    for entry in it:
                        if entry.name.startswith("."):
                            continue
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        if not is_dir:
                            continue
                        full_path = str(Path(entry.path).resolve())
                        is_git = (Path(entry.path) / ".git").exists()
                        entries.append(
                            {
                                "name": entry.name,
                                "path": full_path,
                                "is_dir": True,
                                "is_git_repo": is_git,
                            }
                        )
            except PermissionError:
                pass

            entries.sort(key=lambda e: (not e["is_git_repo"], e["name"].lower()))
            return {"path": str(target), "entries": entries}

        result = await asyncio.to_thread(_list_dir, raw_path)
        return _ok(result)

    @mcp.custom_route("/api/doctor", methods=["GET"])
    @handle_errors
    async def get_doctor(_request: Request) -> JSONResponse:
        import asyncio

        from kagan.server.responses import DoctorCheckResponse, DoctorReportResponse

        checks = await asyncio.to_thread(run_doctor_checks)
        check_responses = [
            DoctorCheckResponse(
                name=c.name,
                status=c.status,
                message=c.message,
                fix_hint=c.fix_hint,
                verify_hint=c.verify_hint,
                # category is added by task 623a6f913a0047db; fall back gracefully
                category=getattr(c, "category", "core"),
                is_blocking=c.status == "fail",
            )
            for c in checks
        ]
        fail_count = sum(1 for cr in check_responses if cr.status == "fail")
        warn_count = sum(1 for cr in check_responses if cr.status == "warn")
        report = DoctorReportResponse(
            checks=check_responses,
            ok=fail_count == 0,
            fail_count=fail_count,
            warn_count=warn_count,
        )
        return _ok(report.model_dump())

    @mcp.custom_route("/api/preflight", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_preflight(request: Request, *, ctx: Any) -> JSONResponse:
        agent_backend = request.query_params.get("agent_backend")
        checks = await ctx.client.preflight(agent_backend=agent_backend)
        serialized = [
            {
                "name": check.name,
                "status": check.status.value,
                "message": check.message,
                "fix_hint": check.fix_hint,
                "is_blocking": check.is_blocking,
            }
            for check in checks
        ]
        return _ok({"checks": serialized, "ok": all(not check.is_blocking for check in checks)})

    @mcp.custom_route("/api/events/stream", methods=["GET"])
    @require_context(mcp)
    async def event_stream(request: Request, *, ctx: Any) -> Response:
        """SSE endpoint — streams board + session events to the client."""
        client_type = (
            sanitize_presence_text(
                request.query_params.get("client_type", "web"),
                max_length=MAX_PRESENCE_CLIENT_TYPE,
            )
            or "web"
        )
        client_id = (
            sanitize_presence_text(
                request.query_params.get("client_id", ""),
                max_length=MAX_PRESENCE_CLIENT_ID,
            )
            or None
        )
        return sse_response(_sse_event_generator(mcp, client_type=client_type, client_id=client_id))

    # ── Presence ───────────────────────────────────────────────────────────

    @mcp.custom_route("/api/presence", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_presence(_request: Request, *, ctx: Any) -> JSONResponse:
        """List connected clients with recent heartbeats."""
        tracker = getattr(ctx, "presence", None)
        if tracker is None:
            return _ok([])
        return _ok(tracker.to_wire())

    @mcp.custom_route("/api/presence/heartbeat", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def presence_heartbeat(request: Request, *, ctx: Any) -> JSONResponse:
        """Register or update a client's presence."""
        tracker = getattr(ctx, "presence", None)
        if tracker is None:
            return _ok(None)
        body = await request.json()
        client_id = sanitize_presence_text(body.get("client_id"), max_length=MAX_PRESENCE_CLIENT_ID)
        client_type = sanitize_presence_text(
            body.get("client_type"),
            max_length=MAX_PRESENCE_CLIENT_TYPE,
        )
        if not client_id or not client_type:
            return _err("client_id and client_type are required", status=400)
        tracker.register(
            client_id=client_id,
            client_type=client_type,
            user_label=sanitize_presence_text(
                body.get("user_label"),
                max_length=MAX_PRESENCE_USER_LABEL,
            ),
            active_task_id=sanitize_presence_text(
                body.get("active_task_id"),
                max_length=MAX_PRESENCE_TASK_ID,
            )
            or None,
        )
        return _ok(None)
