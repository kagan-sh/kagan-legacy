"""Compatibility dispatch map built from CommandRouter.

Core host dispatch no longer uses this module. It exists for transitional unit tests.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from kagan.core.api import KaganAPI
from kagan.core.commands import get_command_router
from kagan.core.policy import collect_exposed_methods

RequestHandler = Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any]]]


def _command_router_handler(capability: str, method: str) -> RequestHandler:
    async def _handler(api: Any, params: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(api, KaganAPI):
            raise ValueError("API context is not initialized")
        ctx = getattr(api, "_ctx", None)
        if ctx is None:
            raise ValueError("API context is not initialized")
        result = await get_command_router().dispatch(capability, method, ctx, params)
        if result is None:
            raise RuntimeError(
                f"CommandRouter missing registered command for {capability}.{method}"
            )
        return result

    return _handler


def build_request_dispatch_map() -> dict[tuple[str, str], RequestHandler]:
    dispatch_map: dict[tuple[str, str], RequestHandler] = {}
    router = get_command_router()

    for api_method_name, _method, meta in collect_exposed_methods(KaganAPI):
        key = (meta.capability, meta.method)
        if not router.has_command(*key):
            raise RuntimeError(
                "Missing request handler for exposed API method "
                f"'{api_method_name}' ({meta.capability}.{meta.method})"
            )
        if key in dispatch_map:
            raise RuntimeError(
                "Duplicate exposed operation metadata for request dispatch: "
                f"{meta.capability}.{meta.method}"
            )
        dispatch_map[key] = _command_router_handler(*key)

    additional_keys = {
        ("tasks", "wait"),
        ("review", "merge"),
        ("review", "rebase"),
        ("jobs", "submit"),
        ("jobs", "cancel"),
        ("jobs", "get"),
        ("jobs", "wait"),
        ("jobs", "events"),
        ("sessions", "create"),
        ("sessions", "attach"),
        ("sessions", "exists"),
        ("sessions", "kill"),
        ("tui", "api_call"),
    }
    for key in additional_keys:
        dispatch_map[key] = _command_router_handler(*key)

    return dispatch_map


__all__ = ["RequestHandler", "build_request_dispatch_map"]
