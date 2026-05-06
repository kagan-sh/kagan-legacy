"""Asyncio compatibility workarounds for subprocess shutdown races."""

import asyncio
import sys
from typing import Any

from loguru import logger

_PATCH_FLAG = "_kagan_asyncio_subprocess_handler_patched"
_UNRAISABLE_PATCH_FLAG = "_kagan_asyncio_unraisable_hook_patched"


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


def _is_known_windows_proactor_closed_pipe_unraisable(unraisable: Any) -> bool:
    exc = getattr(unraisable, "exc_value", None)
    if not isinstance(exc, ValueError):
        return False
    if "I/O operation on closed pipe" not in str(exc):
        return False

    obj = getattr(unraisable, "object", None)
    obj_text = " ".join(
        str(part)
        for part in (
            getattr(obj, "__module__", ""),
            getattr(obj, "__qualname__", ""),
            repr(obj),
        )
        if part
    )
    return any(
        marker in obj_text
        for marker in (
            "asyncio.proactor_events",
            "asyncio.base_subprocess",
            "_ProactorBasePipeTransport.__del__",
            "BaseSubprocessTransport.__del__",
        )
    )


def _install_asyncio_subprocess_unraisable_filter() -> None:
    if getattr(sys, _UNRAISABLE_PATCH_FLAG, False):
        return
    previous_hook = sys.unraisablehook

    def _hook(unraisable: Any) -> None:
        if _is_known_windows_proactor_closed_pipe_unraisable(unraisable):
            logger.debug("Ignoring known Windows asyncio subprocess closed-pipe shutdown race")
            return
        previous_hook(unraisable)

    sys.unraisablehook = _hook
    setattr(sys, _UNRAISABLE_PATCH_FLAG, True)


def install_asyncio_subprocess_exception_filter(
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    _install_asyncio_subprocess_unraisable_filter()
    if loop is None:
        try:
            target = asyncio.get_running_loop()
        except RuntimeError:
            return
    else:
        target = loop
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
