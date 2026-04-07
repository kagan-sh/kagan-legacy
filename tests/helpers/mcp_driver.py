"""Protocol driver: McpDriver — translates DSL operations to MCP tool calls.

This is an alternative Layer 3 in the 4-layer test architecture:
    Test Cases → DSL (KaganDriver) → Protocol Driver (McpDriver) → MCP Server

McpDriver mirrors CoreDriver's interface but uses mcp.client.ClientSession
to call MCP tools instead of direct KaganCore service calls.
It translates tool call results back to TaskView/ProjectView DTOs.
"""

import json

from mcp.types import CallToolResult, TextContent

from kagan.core import Priority, TaskStatus
from mcp import ClientSession
from tests.helpers.core_driver import ProjectView, TaskView


def _parse(result: CallToolResult) -> dict:
    """Extract JSON payload from the first TextContent block of a tool result."""
    if result.isError:
        block = result.content[0] if result.content else None
        msg = block.text if isinstance(block, TextContent) else "tool error"
        raise ValueError(msg)
    block = result.content[0]
    assert isinstance(block, TextContent)
    return json.loads(block.text)


def _to_task_view(data: dict) -> TaskView:
    """Convert a tool result dict to a TaskView DTO."""
    status_raw = data.get("status", "BACKLOG")
    try:
        status = TaskStatus(status_raw)
    except ValueError:
        status = TaskStatus.BACKLOG

    priority_raw = data.get("priority", "MEDIUM")
    # Priority uses integer values; tool returns string names
    try:
        priority = Priority[priority_raw]
    except KeyError:
        priority = Priority.MEDIUM

    return TaskView(
        id=data["id"],
        title=data.get("title", ""),
        description=data.get("description", ""),
        status=status,
        priority=priority,
        agent_backend=data.get("agent_backend"),
        base_branch=data.get("base_branch"),
        acceptance_criteria=data.get("acceptance_criteria") or [],
        project_id=data.get("project_id", ""),
        launcher=data.get("launcher") if isinstance(data.get("launcher"), str) else None,
    )


def _to_project_view(data: dict) -> ProjectView:
    """Convert a tool result dict to a ProjectView DTO."""
    return ProjectView(
        id=data["id"],
        name=data.get("name", ""),
        description=data.get("description", ""),
    )


class McpDriver:
    """Drives the system through MCP tool calls on a connected ClientSession.

    Every method is async, returns protocol-independent DTOs, and
    raises ValueError on tool errors.
    """

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    # -- Tasks --------------------------------------------------------------

    async def create_task(self, title: str, description: str = "") -> TaskView:
        """Create a task via task_create tool and return its view."""
        result = await self._session.call_tool(
            "task_create", {"title": title, "description": description}
        )
        return _to_task_view(_parse(result))

    async def get_task(self, task_id: str) -> TaskView:
        """Get a task by ID via task_get tool."""
        result = await self._session.call_tool("task_get", {"task_id": task_id})
        return _to_task_view(_parse(result))

    async def list_tasks(self, *, status: str | None = None) -> list[TaskView]:
        """List tasks via task_list tool with optional status filter."""
        args: dict = {}
        if status is not None:
            args["status"] = status
        result = await self._session.call_tool("task_list", args)
        payload = _parse(result)
        return [_to_task_view(t) for t in payload.get("tasks", [])]

    # -- Projects -----------------------------------------------------------

    async def list_projects(self) -> list[ProjectView]:
        """List all projects via project_list tool."""
        result = await self._session.call_tool("project_list", {})
        payload = _parse(result)
        return [_to_project_view(p) for p in payload.get("projects", [])]


__all__ = ["McpDriver"]
