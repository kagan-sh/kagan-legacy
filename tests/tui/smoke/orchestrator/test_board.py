from __future__ import annotations

from typing import cast

import pytest
from textual.containers import ScrollableContainer
from textual.widgets import Static

from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.column import KanbanColumn
from kagan.tui.ui.widgets.keybinding_hint import KanbanHintBar
from tests.helpers.wait import wait_for_screen, wait_until

from .conftest import (
    UI_TIMEOUT_BOOT,
    UI_TIMEOUT_SHORT,
    _wait_for_kanban_overlay,
)

pytestmark = pytest.mark.usefixtures("global_mock_tmux")


@pytest.mark.asyncio
async def test_kanban_starts_on_board_when_tasks_exist(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        assert not overlay.has_class("visible")
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert bool(hint_bar.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_defaults_to_docked_intro_on_empty_board(
    e2e_app_without_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_without_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot, open_if_hidden=False)
        assert not overlay.has_class("fullscreen")
        assert overlay.region.y + overlay.region.height >= pilot.app.size.height - 1
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)
        assert not overlay.has_class("has-content")


@pytest.mark.asyncio
async def test_orchestrator_overlay_empty_board_docked_stays_pinned_to_bottom(
    e2e_app_without_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_without_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot, open_if_hidden=False)
        assert overlay.has_class("visible")
        assert not overlay.has_class("fullscreen")
        assert overlay.region.y + overlay.region.height >= pilot.app.size.height - 1

        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="empty-board docked overlay to close",
        )

        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="empty-board overlay to reopen in docked mode",
        )
        assert overlay.region.y + overlay.region.height >= pilot.app.size.height - 1


@pytest.mark.asyncio
async def test_orchestrator_overlay_empty_board_docked_keeps_minimum_visible_height(
    e2e_app_without_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_without_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(160, 48)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot, open_if_hidden=False)
        await wait_until(
            lambda: overlay.region.height >= kanban.DOCKED_OVERLAY_MIN_HEIGHT,
            timeout=UI_TIMEOUT_SHORT,
            description="docked overlay to keep minimum visible height",
        )
        assert overlay.region.height >= kanban.DOCKED_OVERLAY_MIN_HEIGHT
        expected_half = pilot.app.size.height // 2
        assert abs(overlay.region.height - expected_half) <= 1


@pytest.mark.asyncio
async def test_orchestrator_overlay_mode_toggles_switch_and_close(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        assert overlay.has_class("fullscreen")
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)

        # Docked toggle: fullscreen -> docked
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to switch from fullscreen to docked mode",
        )
        await wait_until(
            lambda: overlay.region.height > 0,
            timeout=UI_TIMEOUT_SHORT,
            description="docked overlay to complete layout",
        )
        assert not bool(hint_bar.display)
        assert overlay.region.y + overlay.region.height >= pilot.app.size.height - 1
        session_current = overlay.query_one("#chat-overlay-session-current", Static)
        assert not bool(session_current.display)

        # Docked toggle again: docked -> board
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to switch from docked to board mode",
        )
        assert bool(hint_bar.display)

        # Fullscreen toggle: board -> fullscreen
        kanban.action_open_chat_fullscreen()
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to open fullscreen from board mode",
        )
        assert not bool(hint_bar.display)

        # Cross transition: fullscreen -> docked via docked toggle
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to switch from fullscreen to docked via docked toggle",
        )

        # Cross transition: docked -> fullscreen via fullscreen toggle
        kanban.action_open_chat_fullscreen()
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to switch from docked to fullscreen via fullscreen toggle",
        )

        # Fullscreen toggle again: fullscreen -> board
        kanban.action_open_chat_fullscreen()
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close fullscreen to board mode",
        )
        assert bool(hint_bar.display)


@pytest.mark.asyncio
async def test_docked_overlay_shrinks_columns_and_increases_scroll_range(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        for index in range(6):
            await kanban.ctx.api.create_task(
                title=f"Backlog overflow {index}",
                description="Backlog overflow coverage task.",
            )
        await kanban._board.refresh_board()

        await wait_until(
            lambda: len(kanban.query_one("#column-backlog", KanbanColumn).get_cards()) >= 7,
            timeout=UI_TIMEOUT_SHORT,
            description="backlog column to render overflow tasks",
        )
        backlog_content = kanban.query_one("#content-backlog", ScrollableContainer)
        await wait_until(
            lambda: backlog_content.region.height > 0,
            timeout=UI_TIMEOUT_SHORT,
            description="backlog content region to be measurable",
        )
        baseline_height = backlog_content.region.height
        baseline_scroll_range = backlog_content.max_scroll_y

        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to switch to docked mode for column sizing check",
        )

        await wait_until(
            lambda: backlog_content.region.height < baseline_height,
            timeout=UI_TIMEOUT_SHORT,
            description="column content to shrink under docked overlay",
        )
        await wait_until(
            lambda: backlog_content.max_scroll_y > baseline_scroll_range,
            timeout=UI_TIMEOUT_SHORT,
            description="column content to gain additional scroll range in docked mode",
        )
        assert backlog_content.region.height < baseline_height
        assert backlog_content.max_scroll_y > baseline_scroll_range


@pytest.mark.asyncio
async def test_column_scroll_indicator_only_shows_when_docked_overlay_occludes_content(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        for index in range(14):
            await kanban.ctx.api.create_task(
                title=f"Backlog overflow scroll indicator {index}",
                description=(
                    "Ensure backlog column overflow exists for scrollbar visibility checks."
                ),
            )
        await kanban._board.refresh_board()
        overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        if overlay.has_class("visible"):
            overlay.hide()
            await wait_until(
                lambda: not overlay.has_class("visible"),
                timeout=UI_TIMEOUT_SHORT,
                description="overlay to close before baseline scrollbar visibility check",
            )
        kanban.sync_empty_placeholders_for_overlay()

        backlog_content = kanban.query_one("#content-backlog", ScrollableContainer)
        await wait_until(
            lambda: backlog_content.max_scroll_y > 0,
            timeout=UI_TIMEOUT_SHORT,
            description="backlog column to become scrollable",
        )
        assert int(backlog_content.styles.scrollbar_size_vertical or 0) == 0

        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to switch to docked mode for scrollbar visibility check",
        )
        await wait_until(
            lambda: int(backlog_content.styles.scrollbar_size_vertical or 0) > 0,
            timeout=UI_TIMEOUT_SHORT,
            description="column scrollbar to appear only when docked overlay occludes content",
        )

        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close so column scrollbar can hide",
        )
        await wait_until(
            lambda: int(backlog_content.styles.scrollbar_size_vertical or 0) == 0,
            timeout=UI_TIMEOUT_SHORT,
            description="column scrollbar to hide when no overlay occlusion remains",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_simplified_input_rail_omits_submit_intent_chip(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input")
        prompt = overlay.query_one("#chat-overlay-input-prompt", Static)

        assert str(prompt.render()).strip() == ">"
        assert not list(overlay.query("#chat-overlay-submit-intent"))
        assert "/ for commands" in chat_input.placeholder
        assert "Tab/Ctrl+K" not in chat_input.placeholder
        assert "Ctrl+C clears input" not in chat_input.placeholder
