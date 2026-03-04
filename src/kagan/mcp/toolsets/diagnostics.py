"""kagan.mcp.toolsets.diagnostics — Diagnostics MCP tool (opt-in)."""

import asyncio

from mcp.server.fastmcp import Context, FastMCP
from sqlmodel import Session, select

from kagan.mcp.server import ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register diagnostics tool on mcp — only when enable_instrumentation is True."""
    if not opts.enable_instrumentation:
        return

    @mcp.tool()
    @mcp_error_boundary
    async def diagnostics_get_instrumentation(ctx: Context) -> dict:
        """Return active sessions, DB stats, and agent process status."""
        app = get_context(ctx)

        def _collect() -> tuple[list[dict], dict, list[dict]]:
            from kagan.core.enums import SessionStatus
            from kagan.core.models import Session as CoreRun
            from kagan.core.models import SessionEvent, Task

            with Session(app.client.engine) as session:
                stmt = select(CoreRun).where(
                    (CoreRun.status == SessionStatus.PENDING)
                    | (CoreRun.status == SessionStatus.RUNNING)
                )
                sessions = list(session.exec(stmt).all())
                active = [
                    {
                        "id": s.id,
                        "task_id": s.task_id,
                        "mode": s.mode.value,
                        "status": s.status.value,
                        "pid": s.pid,
                    }
                    for s in sessions
                ]

                db_stats = {
                    "tasks": len(list(session.exec(select(Task)).all())),
                    "events": len(list(session.exec(select(SessionEvent)).all())),
                    "active_sessions": len(active),
                }
                agent_processes = [
                    {"session_id": s.id, "pid": s.pid} for s in sessions if s.pid is not None
                ]
            return active, db_stats, agent_processes

        active_sessions, db_stats, agent_processes = await asyncio.to_thread(_collect)
        return {
            "active_sessions": active_sessions,
            "db_stats": db_stats,
            "agent_processes": agent_processes,
        }
