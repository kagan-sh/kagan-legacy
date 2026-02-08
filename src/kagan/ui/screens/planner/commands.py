"""Planner command palette provider."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from textual.command import DiscoveryHit, Hit, Hits, Provider

if TYPE_CHECKING:
    from textual.screen import Screen


@dataclass(frozen=True, slots=True)
class ScreenAction:
    command: str
    help: str
    action: str


PLANNER_ACTIONS: tuple[ScreenAction, ...] = (
    ScreenAction("planner enhance", "Refine prompt", "refine"),
    ScreenAction("planner back to board", "Return to board", "to_board"),
    ScreenAction("planner stop", "Stop planner or clear input", "cancel"),
)


def _screen_allows_action(screen: Screen, action: str) -> bool:
    if not hasattr(screen, f"action_{action}"):
        return False
    check_action = getattr(screen, "check_action", None)
    if check_action is None:
        return True
    try:
        return check_action(action, ()) is True
    except Exception:
        return False


async def _run_screen_action(screen: Screen, action: str) -> None:
    action_method = getattr(screen, f"action_{action}", None)
    if action_method is None:
        return
    result = action_method()
    if asyncio.iscoroutine(result):
        await result


class PlannerCommandProvider(Provider):
    """Command palette provider for planner actions."""

    async def search(self, query: str) -> Hits:
        screen = self.screen
        matcher = self.matcher(query)
        for item in PLANNER_ACTIONS:
            if not _screen_allows_action(screen, item.action):
                continue
            score = matcher.match(item.command)
            if score <= 0:
                continue
            yield Hit(
                score,
                matcher.highlight(item.command),
                partial(_run_screen_action, screen, item.action),
                help=item.help,
            )

    async def discover(self) -> Hits:
        screen = self.screen
        for item in PLANNER_ACTIONS:
            if not _screen_allows_action(screen, item.action):
                continue
            yield DiscoveryHit(
                item.command,
                partial(_run_screen_action, screen, item.action),
                help=item.help,
            )
