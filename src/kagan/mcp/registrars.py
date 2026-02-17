"""Backward compatibility module - re-exports from _tool_gen.py and _response_models.py."""

from kagan.mcp._response_models import (
    TaskRuntimeState,
)
from kagan.mcp._tool_gen import (
    SharedToolRegistrationContext,
    ToolRegistrationContext,
    register_shared_tools,
)


def register_full_mode_tools(*args: object, **kwargs: object) -> None:
    """Backward compatibility stub - implementation moved to server.py."""
    from kagan.mcp.server import _register_full_mode_tools as impl

    return impl(*args, **kwargs)


__all__ = [
    "SharedToolRegistrationContext",
    "TaskRuntimeState",
    "ToolRegistrationContext",
    "register_full_mode_tools",
    "register_shared_tools",
]
