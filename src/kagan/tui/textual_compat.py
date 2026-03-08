"""Compatibility workarounds for Textual versions used by Kagan."""

import asyncio
from typing import Any

from loguru import logger
from textual.widgets._select import SelectOverlay

_PATCH_FLAG = "_kagan_select_overlay_move_page_patched"
_ASYNCIO_SUBPROCESS_HANDLER_PATCH_FLAG = "_kagan_asyncio_subprocess_handler_patched"


def _patch_select_overlay_page_navigation() -> None:
    original_move_page = SelectOverlay._move_page
    if getattr(original_move_page, _PATCH_FLAG, False):
        return

    def _safe_move_page(self: SelectOverlay, direction: Any) -> None:
        # Guard 1: No options at all -> nothing to navigate
        options = getattr(self, "_options", None)
        if not options:
            return
        # Guard 2: No lines rendered yet -> cannot compute page offset
        lines = getattr(self, "_lines", None)
        if not lines:
            return
        # Guard 3: Index map empty or missing highlighted key -> fallback to boundary
        highlighted = self.highlighted
        anchor = highlighted if isinstance(highlighted, int) else 0
        index_to_line = getattr(self, "_index_to_line", None)
        if not index_to_line or anchor not in index_to_line:
            if direction < 0:
                self.action_first()
            else:
                self.action_last()
            return
        try:
            original_move_page(self, direction)
        except KeyError:
            # Defensive guard for transient stale index maps on overlay updates.
            logger.debug(
                "Caught KeyError in SelectOverlay._move_page, falling back to boundary action"
            )
            if direction < 0:
                self.action_first()
            else:
                self.action_last()

    setattr(_safe_move_page, _PATCH_FLAG, True)
    SelectOverlay._move_page = _safe_move_page


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
    target = loop or asyncio.get_running_loop()
    if getattr(target, _ASYNCIO_SUBPROCESS_HANDLER_PATCH_FLAG, False):
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
    setattr(target, _ASYNCIO_SUBPROCESS_HANDLER_PATCH_FLAG, True)


def apply_textual_compat_workarounds() -> None:
    """Apply runtime compatibility fixes for known Textual edge cases."""
    _patch_select_overlay_page_navigation()


__all__ = ["apply_textual_compat_workarounds", "install_asyncio_subprocess_exception_filter"]
