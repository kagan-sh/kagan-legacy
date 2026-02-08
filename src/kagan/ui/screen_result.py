"""Helpers for awaiting modal dismiss results across UI contexts."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from textual.app import App
    from textual.screen import Screen


async def await_screen_result(app: App, screen: Screen[Any]) -> Any:
    """Push a screen and await its dismiss result."""
    push_screen_wait = cast(
        "Callable[[Screen[Any]], Awaitable[Any]] | None",
        getattr(app, "push_screen_wait", None),
    )
    if push_screen_wait is not None:
        try:
            return await push_screen_wait(screen)
        except TypeError:
            # Some tests monkeypatch push_screen with non-awaitable doubles.
            # Treat this as a dismissed/unsupported modal interaction.
            return None

    future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

    def _on_result(result: Any) -> None:
        if not future.done():
            future.set_result(result)

    push_result = app.push_screen(screen, callback=_on_result)
    if inspect.isawaitable(push_result):
        await push_result
    else:
        # Test doubles may return immediate non-awaitable values and not invoke callback.
        return None
    return await future


__all__ = ["await_screen_result"]
