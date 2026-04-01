"""kagan.server.mcp.toolsets.diagnostics — Diagnostics MCP tool (opt-in)."""

from mcp.server.fastmcp import Context, FastMCP

from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register diagnostics tool on mcp — only when enable_instrumentation is True."""
    if not opts.enable_instrumentation:
        return

    @mcp.tool()
    @mcp_error_boundary
    async def diagnostics_get_instrumentation(ctx: Context) -> dict:
        """Return active sessions, DB stats, and agent process status."""
        app = get_context(ctx)

        sessions = await app.client.tasks.sessions.list_active()
        active_sessions = [
            {
                "id": s.id,
                "task_id": s.task_id,
                "launcher": s.launcher,
                "status": s.status.value,
                "pid": s.pid,
            }
            for s in sessions
        ]

        projects = await app.client.projects.list()
        task_count = 0
        for project in projects:
            counts = await app.client.tasks.counts(project_id=project.id)
            task_count += sum(counts.values())

        event_count = 0
        offset = 0
        page_size = 200
        while True:
            batch = await app.client.tasks.events.list_all(offset=offset, limit=page_size)
            event_count += len(batch)
            if len(batch) < page_size:
                break
            offset += len(batch)

        db_stats = {
            "tasks": task_count,
            "events": event_count,
            "active_sessions": len(active_sessions),
        }
        agent_processes = [
            {"session_id": s.id, "pid": s.pid} for s in sessions if s.pid is not None
        ]
        return {
            "active_sessions": active_sessions,
            "db_stats": db_stats,
            "agent_processes": agent_processes,
        }
