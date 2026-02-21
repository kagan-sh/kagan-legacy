from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from textual.pilot import Pilot
    from textual.screen import Screen

    from kagan.core.domain.enums import TaskStatus
    from kagan.tui.app import KaganApp

# CI runners are significantly slower; scale timeouts accordingly.
# Windows CI is often slower than Linux/macOS for TUI tests.
_IS_CI: bool = bool(os.environ.get("CI"))
_CI_MULTIPLIER: float = 8.0 if (_IS_CI and os.name == "nt") else (5.0 if _IS_CI else 1.0)
_CI_TIMEOUT_CAP_SECONDS: float = 50.0


def _ci_timeout(timeout: float) -> float:
    scaled_timeout = timeout * _CI_MULTIPLIER
    if not _IS_CI:
        return scaled_timeout
    return min(scaled_timeout, _CI_TIMEOUT_CAP_SECONDS)


def _deadline(timeout: float) -> float:
    return asyncio.get_running_loop().time() + timeout


async def _wait_until_deadline[PollResult](
    predicate: Callable[[], Awaitable[PollResult | None]],
    *,
    timeout: float,
    check_interval: float,
    wait_between_checks: Callable[[float], Awaitable[None]],
    timeout_message: Callable[[float], str],
    wait_before_check: Callable[[], Awaitable[None]] | None = None,
) -> PollResult:
    timeout = _ci_timeout(timeout)
    deadline = _deadline(timeout)
    while asyncio.get_running_loop().time() < deadline:
        if wait_before_check is not None:
            await wait_before_check()
        result = await predicate()
        if result is not None:
            return result
        await wait_between_checks(check_interval)
    raise TimeoutError(timeout_message(timeout))


async def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 5.0,
    check_interval: float = 0.05,
    description: str = "condition",
) -> None:
    """Wait for a synchronous predicate to become true."""

    async def _predicate() -> bool | None:
        return True if predicate() else None

    await _wait_until_deadline(
        _predicate,
        timeout=timeout,
        check_interval=check_interval,
        wait_between_checks=asyncio.sleep,
        timeout_message=lambda scaled_timeout: (
            f"Timed out after {scaled_timeout}s waiting for {description}"
        ),
    )


async def wait_until_async(
    predicate: Callable[[], Awaitable[bool]],
    *,
    timeout: float = 5.0,
    check_interval: float = 0.05,
    description: str = "condition",
) -> None:
    """Wait for an async predicate to become true."""

    async def _predicate() -> bool | None:
        return True if await predicate() else None

    await _wait_until_deadline(
        _predicate,
        timeout=timeout,
        check_interval=check_interval,
        wait_between_checks=asyncio.sleep,
        timeout_message=lambda scaled_timeout: (
            f"Timed out after {scaled_timeout}s waiting for {description}"
        ),
    )


async def wait_for_screen(
    pilot: Pilot,
    screen_type: type[Screen],
    timeout: float = 10.0,
    check_interval: float = 0.1,
) -> Screen:
    from textual.css.query import NoMatches
    from textual.widgets import Label

    from kagan.tui.ui.screens.kanban import KanbanScreen
    from kagan.tui.ui.widgets.column import KanbanColumn
    from kagan.tui.ui.widgets.header import KaganHeader

    timeout = _ci_timeout(timeout)
    deadline = _deadline(timeout)
    while asyncio.get_running_loop().time() < deadline:
        await pilot.pause()
        startup_worker = getattr(pilot.app, "_startup_worker", None)
        startup_error = getattr(startup_worker, "error", None)
        if startup_worker is not None and startup_worker.is_finished and startup_error is not None:
            raise RuntimeError(f"startup worker failed: {startup_error}")
        current_screen = pilot.app.screen
        if isinstance(current_screen, screen_type):
            expected_agent = pilot.app.config.general.default_worker_agent.strip()
            if isinstance(current_screen, KanbanScreen):
                try:
                    header = current_screen.query_one(KaganHeader)
                    agent_text = str(header.query_one("#header-agent", Label).content)
                except (LookupError, NoMatches):
                    agent_text = ""
                if expected_agent and not agent_text:
                    await pilot.pause(check_interval)
                    continue

            if isinstance(current_screen, KanbanScreen):
                tasks = await pilot.app.ctx.api.list_tasks(
                    project_id=pilot.app.ctx.active_project_id
                )
                if tasks:
                    columns = current_screen.query(KanbanColumn)
                    if not any(column.get_cards() for column in columns):
                        await pilot.pause(check_interval)
                        continue

            return current_screen
        await pilot.pause(check_interval)

    current_screen = pilot.app.screen
    assert isinstance(current_screen, screen_type), (
        f"Expected screen {screen_type.__name__}, got {type(current_screen).__name__}"
    )
    return current_screen


async def wait_for_widget(
    pilot: Pilot,
    selector: str,
    timeout: float = 5.0,
    check_interval: float = 0.1,
) -> None:
    from textual.css.query import NoMatches

    async def _predicate() -> bool | None:
        try:
            pilot.app.screen.query_one(selector)
            return True
        except NoMatches:
            return None

    await _wait_until_deadline(
        _predicate,
        timeout=timeout,
        check_interval=check_interval,
        wait_between_checks=pilot.pause,
        wait_before_check=pilot.pause,
        timeout_message=lambda scaled_timeout: (
            f"Widget '{selector}' not found within {scaled_timeout}s"
        ),
    )


async def wait_for_text(
    pilot: Pilot,
    text: str,
    timeout: float = 5.0,
    check_interval: float = 0.1,
) -> None:
    async def _predicate() -> bool | None:
        rendered = str(pilot.app.screen)
        return True if text in rendered else None

    await _wait_until_deadline(
        _predicate,
        timeout=timeout,
        check_interval=check_interval,
        wait_between_checks=pilot.pause,
        wait_before_check=pilot.pause,
        timeout_message=lambda scaled_timeout: (
            f"Text '{text}' not found within {scaled_timeout}s"
        ),
    )


async def wait_for_modal(
    pilot: Pilot,
    modal_type: type[Screen],
    timeout: float = 5.0,
    check_interval: float = 0.1,
) -> Screen:
    async def _predicate() -> Screen | None:
        for screen in pilot.app.screen_stack:
            if isinstance(screen, modal_type):
                return screen

        return None

    return await _wait_until_deadline(
        _predicate,
        timeout=timeout,
        check_interval=check_interval,
        wait_between_checks=pilot.pause,
        wait_before_check=pilot.pause,
        timeout_message=lambda scaled_timeout: (
            f"Modal {modal_type.__name__} not found within {scaled_timeout}s"
        ),
    )


async def wait_for_task_status(
    app: KaganApp,
    task_id: str,
    status: TaskStatus,
    *,
    timeout: float = 20.0,
    pilot: Pilot | None = None,
) -> None:
    """Wait for a task to reach a specific status.

    If *pilot* is provided, pumps Textual's message queue each iteration
    so that screen callbacks (e.g. merge after ReviewModal dismiss) execute.
    """
    timeout = _ci_timeout(timeout)
    deadline = _deadline(timeout)
    last_status = None
    while asyncio.get_running_loop().time() < deadline:
        task = await app.ctx.api.get_task(task_id)
        if task:
            last_status = task.status
            if task.status == status:
                return
        if pilot is not None:
            await pilot.pause(0.1)
        else:
            await asyncio.sleep(0.1)
    raise TimeoutError(
        f"Task {task_id} did not reach {status} within {timeout}s (last status: {last_status})"
    )


async def type_text(pilot: Pilot, text: str, *, delay: float = 0.0) -> None:
    for char in text:
        await pilot.press(char)
        if delay > 0:
            await pilot.pause(delay)


async def wait_for_widget_state(
    pilot: Pilot,
    selector: str,
    predicate: Callable[[Any], bool],
    *,
    timeout: float = 5.0,
    check_interval: float = 0.05,
    description: str = "widget state",
) -> Any:
    """Wait for a widget matching ``selector`` to satisfy ``predicate``."""
    from textual.css.query import NoMatches

    async def _predicate() -> Any | None:
        try:
            widget = pilot.app.screen.query_one(selector)
        except NoMatches:
            return None
        return widget if predicate(widget) else None

    return await _wait_until_deadline(
        _predicate,
        timeout=timeout,
        check_interval=check_interval,
        wait_between_checks=pilot.pause,
        wait_before_check=pilot.pause,
        timeout_message=lambda scaled_timeout: (
            f"Timed out after {scaled_timeout}s waiting for {description}: {selector}"
        ),
    )
