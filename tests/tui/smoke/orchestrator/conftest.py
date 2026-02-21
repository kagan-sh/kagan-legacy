from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, cast

from kagan.tui.ui.modals.session_picker import SessionPickerModal
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.screens.task_output import TaskOutputScreen
from kagan.tui.ui.widgets.card import TaskCard
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.streaming_output import StreamingOutput, ThinkingIndicator
from tests.helpers.wait import wait_for_screen, wait_until

if TYPE_CHECKING:
    from textual.pilot import Pilot

UI_TIMEOUT_SHORT = 5.0
UI_TIMEOUT_LONG = 10.0
UI_TIMEOUT_BOOT = 15.0


async def _wait_for_kanban_overlay(
    pilot: Pilot, *, open_if_hidden: bool = True
) -> tuple[KanbanScreen, ChatOverlay]:
    kanban = cast(
        "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
    )
    overlay = kanban.query_one("#chat-overlay", ChatOverlay)
    if open_if_hidden and not overlay.has_class("visible"):
        await pilot.press("ctrl+p")
    await wait_until(
        lambda: overlay.has_class("visible"),
        timeout=UI_TIMEOUT_LONG,
        description="orchestrator overlay to become visible",
    )
    return kanban, overlay


async def _focus_task_card(pilot: Pilot, kanban: KanbanScreen, task_id: str) -> TaskCard:
    card = kanban.query_one(f"#card-{task_id}", TaskCard)
    card.focus()
    await wait_until(
        lambda: (
            (focused := kanban.get_focused_card()) is not None
            and focused.task_model is not None
            and focused.task_model.id == task_id
        ),
        timeout=UI_TIMEOUT_SHORT,
        description=f"task card {task_id[:8]} to receive focus",
    )
    await pilot.pause()
    return card


async def _open_task_output_via_enter(
    pilot: Pilot,
    kanban: KanbanScreen,
    task_id: str,
    *,
    timeout: float = UI_TIMEOUT_LONG,
    ensure_workspace: bool = True,
) -> TaskOutputScreen:
    timeout = min(timeout, UI_TIMEOUT_SHORT)
    await _focus_task_card(pilot, kanban, task_id)
    task = await kanban.ctx.api.get_task(task_id)

    if ensure_workspace:
        workspace_path = await kanban.ctx.api.get_task_workspace_path(task_id)
        if workspace_path is None and task is not None:
            with contextlib.suppress(Exception):
                await kanban._session.provision_workspace_for_active_repo(task)
            await pilot.pause()

    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await pilot.press("o")
        await pilot.pause()
        current_screen = pilot.app.screen
        if isinstance(current_screen, TaskOutputScreen):
            return current_screen
        await asyncio.sleep(0.1)

    if task is not None:
        # Fallback for slower runners where synthetic key events can be dropped.
        kanban.run_worker(
            kanban._session.open_session_flow(task),
            group="test-open-session-fallback",
            exclusive=True,
            exit_on_error=False,
        )
    return cast("TaskOutputScreen", await wait_for_screen(pilot, TaskOutputScreen, timeout=timeout))


async def _press_enter_until(
    pilot: Pilot,
    predicate,
    *,
    timeout: float = UI_TIMEOUT_LONG,
    description: str = "Enter-driven action",
) -> None:
    timeout = min(timeout, UI_TIMEOUT_SHORT)
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await pilot.press("o")
        await pilot.pause()
        if predicate():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Timed out after {timeout}s waiting for {description}")


def _has_slash_complete(overlay: ChatOverlay) -> bool:
    from kagan.tui.ui.widgets.slash_complete import SlashComplete

    return bool(list(overlay.query(SlashComplete)))


def _has_thinking_indicator(output: StreamingOutput) -> bool:
    return bool(list(output.query(ThinkingIndicator)))


def _active_session_picker(app: object) -> SessionPickerModal | None:
    screen_stack = getattr(app, "screen_stack", [])
    for screen in reversed(screen_stack):
        if isinstance(screen, SessionPickerModal):
            return screen
    return None


def _thinking_indicator_text(output: StreamingOutput) -> str:
    indicators = list(output.query(ThinkingIndicator))
    if not indicators:
        return ""
    return str(indicators[0].render())
