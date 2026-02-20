"""Command routing and registration for core capability handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib import import_module
from threading import Lock
from typing import TYPE_CHECKING, Any

from kagan.core.policy import CommandMetadata, collect_command_methods

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext

CommandFn = Callable[["AppContext", dict[str, Any]], Awaitable[dict[str, Any]]]


class CommandRouter:
    """Dispatch capability+method operations to registered command functions."""

    def __init__(self) -> None:
        self._commands: dict[tuple[str, str], CommandFn] = {}

    def register(self, fn: CommandFn, meta: CommandMetadata) -> None:
        key = (meta.capability, meta.method)
        if key in self._commands:
            raise RuntimeError(
                f"Duplicate command registration for {meta.capability}.{meta.method}"
            )
        self._commands[key] = fn

    def register_module(self, module: object) -> None:
        for _name, fn, meta in collect_command_methods(module):
            self.register(fn, meta)

    async def dispatch(
        self,
        capability: str,
        method: str,
        ctx: AppContext,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        handler = self._commands.get((capability, method))
        if handler is None:
            return None
        return await handler(ctx, params)

    def has_command(self, capability: str, method: str) -> bool:
        return (capability, method) in self._commands


def build_command_router() -> CommandRouter:
    """Build a router with all currently ported command modules."""
    router = CommandRouter()
    for module_name in (
        "kagan.core.commands.tasks",
        "kagan.core.commands.projects",
        "kagan.core.commands.settings",
        "kagan.core.commands.automation",
        "kagan.core.commands.plugins",
        "kagan.core.commands.workspaces",
    ):
        router.register_module(import_module(module_name))
    return router


_COMMAND_ROUTER: CommandRouter | None = None
_COMMAND_ROUTER_LOCK = Lock()


def get_command_router() -> CommandRouter:
    """Return the cached command router instance."""
    global _COMMAND_ROUTER
    if _COMMAND_ROUTER is None:
        with _COMMAND_ROUTER_LOCK:
            if _COMMAND_ROUTER is None:
                _COMMAND_ROUTER = build_command_router()
    return _COMMAND_ROUTER


__all__ = [
    "CommandFn",
    "CommandRouter",
    "build_command_router",
    "get_command_router",
]
