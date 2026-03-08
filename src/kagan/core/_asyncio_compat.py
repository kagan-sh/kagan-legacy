"""Asyncio compatibility workarounds for subprocess shutdown races."""

import asyncio
from typing import Any

from loguru import logger

_PATCH_FLAG = "_kagan_asyncio_subprocess_handler_patched"


def _is_known_asyncio_subprocess_invalid_state(context: dict[str, Any]) -> bool:
    exc = context.get("exception")
    message = str(context.get("message") or "")
    if isinstance(exc, RuntimeError) and "Event loop is closed" in str(exc):
        if "SubprocessTransport" in message:
            return True
    if not isinstance(exc, asyncio.InvalidStateError):
        return False
    handle = context.get("handle")
    callback = getattr(handle, "_callback", None)
    callback_name = str(getattr(callback, "__qualname__", ""))
    if "_call_connection_lost" not in f"{callback_name} {message}":
        return False
    return "BaseSubprocessTransport" in message or "_UnixReadPipeTransport" in message


def install_asyncio_subprocess_exception_filter(
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Install a loop exception handler that silences known subprocess shutdown races.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    target = loop or asyncio.get_running_loop()
    if getattr(target, _PATCH_FLAG, False):
        return
    previous_handler = target.get_exception_handler()

    def _handler(active_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if _is_known_asyncio_subprocess_invalid_state(context):
            logger.debug(
                "Ignoring known asyncio subprocess shutdown race: {}",
                context.get("message") or "InvalidStateError in _call_connection_lost",
            )
            return
        if previous_handler is not None:
            previous_handler(active_loop, context)
            return
        active_loop.default_exception_handler(context)

    target.set_exception_handler(_handler)
    setattr(target, _PATCH_FLAG, True)


__all__ = ["install_asyncio_subprocess_exception_filter"]
