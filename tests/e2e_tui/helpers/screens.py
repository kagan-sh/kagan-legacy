"""Screen-stack assertions.

Centralises ``isinstance(app.screen, …)`` checks so flow tests stay
readable. Always wait for the predicate before querying widgets on the
new screen — ``push_screen`` is synchronous but mount/compose happen on
the next event loop iteration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.e2e_tui.helpers.wait import wait_for

if TYPE_CHECKING:
    from textual.app import App
    from textual.screen import Screen


async def wait_for_screen(app: App, screen_cls: type[Screen]) -> None:
    """Wait until ``app.screen`` is an instance of ``screen_cls``."""
    await wait_for(lambda: isinstance(app.screen, screen_cls))


def is_screen(app: App, screen_cls: type[Screen]) -> bool:
    return isinstance(app.screen, screen_cls)


__all__ = ["is_screen", "wait_for_screen"]
