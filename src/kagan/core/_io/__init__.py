"""kagan.core._io — Shared Pydantic request models for REST + MCP surfaces.

Both ``server/_task_routes.py`` and ``server/mcp/toolsets/tasks.py`` import
from here to prevent argument-shaping drift between surfaces.  No generator,
no manifest, no adapter framework — just one Pydantic class per operation.
"""
