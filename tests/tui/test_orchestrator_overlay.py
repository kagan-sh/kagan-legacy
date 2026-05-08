"""Behavioral tests for OrchestratorOverlay.

Per testing.md: behavioral specs via KaganDriver + Textual Pilot.
Targeted waits only — no wait_for_workers().
"""

from __future__ import annotations

import asyncio

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def _create_agent_session(core, task_id: str, session_id: str) -> str:
    from sqlmodel import Session as DbSession

    from kagan.core.enums import SessionStatus
    from kagan.core.models import Session as AgentSession

    def _write() -> str:
        row = AgentSession(
            id=session_id,
            task_id=task_id,
            agent_backend="test",
            status=SessionStatus.RUNNING,
            agent_role="worker",
        )
        with DbSession(core.engine) as db:
            db.add(row)
            db.commit()
        return session_id

    return await asyncio.to_thread(_write)


async def _pause_until(pilot, predicate, *, attempts: int = 20) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await pilot.pause()
    assert predicate()


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Overlay Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Alpha task")
    yield driver
    await driver.teardown()


async def test_o_key_opens_overlay_from_kanban(board: KaganDriver) -> None:
    """Pressing o on the kanban screen opens the OrchestratorOverlay."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        # We should be on the kanban screen
        assert app.screen.id == "kanban-screen"
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)


async def test_esc_closes_overlay_when_in_orchestrator_mode(board: KaganDriver) -> None:
    """Esc while in orchestrator mode closes the overlay."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


async def test_overlay_breadcrumb_shows_orchestrator_by_default(board: KaganDriver) -> None:
    """The breadcrumb line reads 'Orchestrator' when not attached to a session."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        breadcrumb = app.screen.query_one("#orch-breadcrumb", Static)
        assert "Orchestrator" in str(breadcrumb.content)


async def test_overlay_contains_chat_panel(board: KaganDriver) -> None:
    """The overlay renders a ChatPanel so messages can be sent."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        panel = app.screen.query_one("#orch-chat", ChatPanel)
        assert panel.is_attached


async def test_attach_updates_breadcrumb(board: KaganDriver) -> None:
    """Calling attach() with a role updates the breadcrumb text."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)

        # Simulate attach with a fake session id (no actual DB session needed
        # for the breadcrumb test — the overlay accepts any string)
        await overlay.attach("fake-session-id", "worker")
        await pilot.pause()

        breadcrumb = overlay.query_one("#orch-breadcrumb", Static)
        assert "Worker" in str(breadcrumb.content)


async def test_esc_while_attached_detaches_first_then_closes(board: KaganDriver) -> None:
    """First Esc detaches to orchestrator; second Esc closes the overlay."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)

        # Attach to a fake session
        await overlay.attach("fake-session-id", "worker")
        await pilot.pause()

        # First Esc — should detach back to orchestrator
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        breadcrumb = overlay.query_one("#orch-breadcrumb", Static)
        assert "Orchestrator" in str(breadcrumb.content)
        assert overlay._attached_session_id is None

        # Second Esc — should close overlay
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


async def test_ctrl_space_also_opens_overlay(board: KaganDriver) -> None:
    """Ctrl+Space is an alternative binding for opening the overlay."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)


async def test_attached_session_replays_recent_events(board: KaganDriver) -> None:
    """Attaching to a session replays persisted output and terminal notes."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel

    task = await board.create_task("Replay task")
    session_id = "replay-session"
    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await _create_agent_session(app.core, task.id, session_id)
        await app.core.tasks.events.emit(
            task.id,
            "output_chunk",
            {"text": "replayed assistant", "kind": "assistant"},
            session_id=session_id,
        )
        await app.core.tasks.events.emit(
            task.id,
            "output_chunk",
            {"text": "replayed user", "kind": "user"},
            session_id=session_id,
        )
        await app.core.tasks.events.emit(
            task.id,
            "agent_completed",
            {"message": "done"},
            session_id=session_id,
        )

        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)
        panel = overlay.query_one("#orch-chat", ChatPanel)

        await overlay.attach(session_id, "worker", task_id=task.id)
        stream = panel.stream_output()
        await _pause_until(
            pilot,
            lambda: "replayed assistant" in stream.get_text_content()
            and "> replayed user" in stream.get_text_content()
            and "Agent completed" in stream.get_text_content(),
        )


async def test_attached_session_streams_live_events_for_selected_session(
    board: KaganDriver,
) -> None:
    """Live events render only when they belong to the attached session."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel

    task = await board.create_task("Live task")
    session_id = "live-session"
    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)
        panel = overlay.query_one("#orch-chat", ChatPanel)

        await _create_agent_session(app.core, task.id, session_id)
        await _create_agent_session(app.core, task.id, "other-session")
        await overlay.attach(session_id, "worker", task_id=task.id)
        await pilot.pause()
        await pilot.pause()
        await app.core.tasks.events.emit(
            task.id,
            "output_chunk",
            {"text": "ignored live chunk", "kind": "assistant"},
            session_id="other-session",
        )
        await app.core.tasks.events.emit(
            task.id,
            "output_chunk",
            {"text": "selected live chunk", "kind": "assistant"},
            session_id=session_id,
        )
        stream = panel.stream_output()
        await _pause_until(pilot, lambda: "selected live chunk" in stream.get_text_content())
        assert "ignored live chunk" not in stream.get_text_content()

        await app.core.tasks.events.emit(
            task.id,
            "agent_completed",
            {"message": "done"},
            session_id=session_id,
        )
        breadcrumb = overlay.query_one("#orch-breadcrumb", Static)
        await _pause_until(pilot, lambda: "Worker · done" in str(breadcrumb.content))
        assert "Agent completed" in stream.get_text_content()


async def test_attached_session_without_task_id_exits_quietly(board: KaganDriver) -> None:
    """If a task id cannot be resolved, attach mode does not show a stream error."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)
        panel = overlay.query_one("#orch-chat", ChatPanel)

        await overlay.attach("missing-task-session", "worker")
        await pilot.pause()
        await pilot.pause()

        breadcrumb = overlay.query_one("#orch-breadcrumb", Static)
        assert "Worker · attached" in str(breadcrumb.content)
        assert panel.stream_output().get_text_content() == ""
