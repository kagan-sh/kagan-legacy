"""Behavioural tests for post-audit cleanup findings.

Covers: TUI 1 (active_task_id dead code), TUI 4 (reactive layout mode),
TUI 8 (chat mode helper), D2 (CANCELLED visual), D8 (reduce_motion),
PM4 (backend picker order).
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Audit Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Task A")
    yield driver
    await driver.teardown()


@pytest.fixture
async def empty_board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Empty Audit Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    yield driver
    await driver.teardown()


# ---------------------------------------------------------------------------
# TUI 1 — task_id passed via constructor, no duck-typed app attribute needed
# ---------------------------------------------------------------------------


async def test_task_screen_opens_without_app_active_task_id(board: KaganDriver) -> None:
    """TaskScreen receives task_id via constructor; no _active_task_id fallback needed."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, TaskScreen)
        assert app.screen._task_id is not None
        assert not hasattr(app, "_active_task_id")


# ---------------------------------------------------------------------------
# TUI 4 — _chat_overlay_layout_mode is a reactive; watcher drives CSS classes
# ---------------------------------------------------------------------------


async def test_layout_mode_reactive_drives_css_on_vertical(board: KaganDriver) -> None:
    """Setting _chat_overlay_layout_mode=vertical updates chat-overlay-vertical class."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, KanbanScreen)
        screen: KanbanScreen = app.screen
        await pilot.press("ctrl+i")
        await pilot.pause()
        screen._chat_overlay_layout_mode = "vertical"
        await pilot.pause()
        assert screen.has_class("chat-overlay-vertical")
        assert not screen.has_class("chat-overlay-horizontal")


async def test_layout_mode_reactive_drives_css_on_horizontal(board: KaganDriver) -> None:
    """Setting _chat_overlay_layout_mode=horizontal updates chat-overlay-horizontal class."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, KanbanScreen)
        screen: KanbanScreen = app.screen
        await pilot.press("ctrl+i")
        await pilot.pause()
        screen._chat_overlay_layout_mode = "horizontal"
        await pilot.pause()
        assert screen.has_class("chat-overlay-horizontal")
        assert not screen.has_class("chat-overlay-vertical")


# ---------------------------------------------------------------------------
# TUI 8 — _apply_panel_visibility helper keeps state consistent
# ---------------------------------------------------------------------------


async def test_apply_panel_visibility_hides_panel(board: KaganDriver) -> None:
    """_apply_panel_visibility(visible=False) removes chat CSS classes."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, KanbanScreen)
        screen: KanbanScreen = app.screen
        panel = screen.query_one(ChatPanel)
        await pilot.press("ctrl+i")
        await pilot.pause()
        assert panel.has_class("visible")
        screen._apply_panel_visibility(panel, visible=False, fullscreen=False)
        await pilot.pause()
        assert not panel.has_class("visible")
        assert not screen.has_class("chat-overlay-visible")


async def test_apply_panel_visibility_shows_fullscreen(board: KaganDriver) -> None:
    """_apply_panel_visibility(visible=True, fullscreen=True) applies fullscreen."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, KanbanScreen)
        screen: KanbanScreen = app.screen
        panel = screen.query_one(ChatPanel)
        screen._apply_panel_visibility(panel, visible=True, fullscreen=True)
        await pilot.pause()
        assert panel.has_class("visible")
        assert panel.has_class("fullscreen")


# ---------------------------------------------------------------------------
# D2 — CANCELLED session status uses muted colour, not error red
# ---------------------------------------------------------------------------


async def test_session_dashboard_cancelled_badge_uses_muted_class(tmp_path) -> None:
    """DashboardStatusBar: CANCELLED status applies status-cancelled, not status-failed."""
    from textual.app import App, ComposeResult

    from kagan.tui.screens.session_dashboard import DashboardStatusBar

    class _TestApp(App[None]):
        def compose(self) -> ComposeResult:
            yield DashboardStatusBar()

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.screen.query_one(DashboardStatusBar)
        bar.update_status("Cancelled")
        await pilot.pause()
        badge = bar.query_one("#dashboard-task-status")
        assert "status-cancelled" in badge.classes
        assert "status-failed" not in badge.classes


async def test_session_dashboard_failed_badge_uses_error_class(tmp_path) -> None:
    """DashboardStatusBar: FAILED status applies status-failed (error is appropriate)."""
    from textual.app import App, ComposeResult

    from kagan.tui.screens.session_dashboard import DashboardStatusBar

    class _TestApp(App[None]):
        def compose(self) -> ComposeResult:
            yield DashboardStatusBar()

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.screen.query_one(DashboardStatusBar)
        bar.update_status("Failed")
        await pilot.pause()
        badge = bar.query_one("#dashboard-task-status")
        assert "status-failed" in badge.classes
        assert "status-cancelled" not in badge.classes


# ---------------------------------------------------------------------------
# D8 — reduce_motion setting applies reduce-motion CSS class on app root
# ---------------------------------------------------------------------------


async def test_reduce_motion_setting_applies_css_class(tmp_path) -> None:
    """When reduce_motion=true in settings, app root gets reduce-motion class."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.core.settings.set({"reduce_motion": "true"})
        await app._apply_saved_theme()
        await pilot.pause()
        assert app.has_class("reduce-motion")


async def test_reduce_motion_off_does_not_apply_css_class(tmp_path) -> None:
    """When reduce_motion is absent, app root does NOT get reduce-motion class."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not app.has_class("reduce-motion")


# ---------------------------------------------------------------------------
# PM4 — backend picker sorts installed-first with a separator
# ---------------------------------------------------------------------------


def test_build_agent_backend_options_installed_before_unavailable() -> None:
    """Available backends come before unavailable ones in the picker options."""
    from unittest.mock import patch

    from kagan.tui.screens.setup import _build_agent_backend_options

    mock_availability = {"claude-code": True, "codex": False, "gemini": True}

    class _MockSpec:
        def __init__(self, lbl: str, ref: bool = False) -> None:
            self._lbl = lbl
            self.reference = ref

        def label(self) -> str:
            return self._lbl

    mock_specs = {
        "claude-code": _MockSpec("Claude Code"),
        "codex": _MockSpec("Codex"),
        "gemini": _MockSpec("Gemini"),
    }

    with (
        patch("kagan.tui.screens.setup.list_available_backends", return_value=mock_availability),
        patch("kagan.tui.screens.setup.list_backend_specs", return_value=mock_specs),
    ):
        options = _build_agent_backend_options()

    values = [v for _, v in options]
    available_indices = [i for i, v in enumerate(values) if v in {"claude-code", "gemini"}]
    unavailable_indices = [i for i, v in enumerate(values) if v == "codex"]
    separator_indices = [i for i, v in enumerate(values) if v == "---"]

    assert all(a < unavailable_indices[0] for a in available_indices), (
        "All available backends should come before the first unavailable one"
    )
    assert len(separator_indices) == 1, "Exactly one separator when both groups present"
    assert separator_indices[0] > max(available_indices), "Separator after available group"
    assert separator_indices[0] < unavailable_indices[0], "Separator before unavailable group"


def test_build_agent_backend_options_no_separator_when_all_available() -> None:
    """No separator is added when all backends are installed."""
    from unittest.mock import patch

    from kagan.tui.screens.setup import _build_agent_backend_options

    mock_availability = {"claude-code": True, "codex": True}

    class _MockSpec:
        def __init__(self, lbl: str) -> None:
            self._lbl = lbl
            self.reference = False

        def label(self) -> str:
            return self._lbl

    mock_specs = {
        "claude-code": _MockSpec("Claude Code"),
        "codex": _MockSpec("Codex"),
    }

    with (
        patch("kagan.tui.screens.setup.list_available_backends", return_value=mock_availability),
        patch("kagan.tui.screens.setup.list_backend_specs", return_value=mock_specs),
    ):
        options = _build_agent_backend_options()

    assert all(v != "---" for _, v in options), "No separator when all available"
