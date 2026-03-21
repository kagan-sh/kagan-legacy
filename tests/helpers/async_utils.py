"""Async test utilities — deterministic waiting without wall-clock sleeps."""

from __future__ import annotations

import asyncio
from inspect import isawaitable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def wait_for(
    predicate: Callable[[], bool | Awaitable[bool]],
    *,
    tries: int = 100,
    pump_delay: float = 0,
) -> None:
    """Pump the event loop until predicate is true. No wall-clock sleep."""
    for _ in range(tries):
        result = predicate()
        if isawaitable(result):
            result = await result
        if result:
            return
        await asyncio.sleep(pump_delay)
    raise TimeoutError(f"predicate not satisfied after {tries} pumps")


__all__ = [
    "wait_for",
]
