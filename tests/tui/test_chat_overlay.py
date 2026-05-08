"""Behavioral tests for OrchestratorOverlay footer mode and Ctrl+Up/Down cycling.

Per testing.md: behavioral specs via KaganDriver + Textual Pilot.
Targeted waits only — no wait_for_workers().
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Overlay Test Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Sample task")
    yield driver
    await driver.teardown()


# ---------------------------------------------------------------------------
# Startup gate — optional backend WARNs must not show "Degraded mode" toast
# ---------------------------------------------------------------------------


async def test_boot_with_optional_backend_warns_shows_no_degraded_toast(
    tmp_path,
) -> None:
    """When the default backend passes and non-default backends WARN,
    the 'Degraded mode' toast must NOT be shown at startup."""
    from kagan.cli.doctor import DoctorCheck
    from kagan.tui import KaganApp

    # Case (b): one PASS, five WARNs for non-default backends
    startup_checks = [
        DoctorCheck(
            name="agent backend: claude-code",
            status="pass",
            message="claude-code found",
            fix_hint="",
            verify_hint="",
            category="backend",
        ),
        DoctorCheck(
            name="agent backend: opencode",
            status="warn",
            message="opencode not found",
            fix_hint="",
            verify_hint="",
            category="backend",
        ),
        DoctorCheck(
            name="agent backend: gemini-cli",
            status="warn",
            message="gemini-cli not found",
            fix_hint="",
            verify_hint="",
            category="backend",
        ),
    ]

    notified: list[str] = []

    app = KaganApp(
        db_path=tmp_path / "kagan.db",
        startup_checks=startup_checks,
    )
    # Intercept notify() calls
    original_notify = app.notify

    def _capture_notify(message, *args, **kwargs):
        notified.append(str(message))
        return original_notify(message, *args, **kwargs)

    with patch.object(app, "notify", side_effect=_capture_notify):
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

    degraded = [m for m in notified if "Degraded mode" in m]
    assert not degraded, (
        f"Expected no 'Degraded mode' toast for optional backend WARNs, but got: {degraded}"
    )


# ---------------------------------------------------------------------------
# Bug A — footer mode in overlay shows correct hints
# ---------------------------------------------------------------------------


async def test_overlay_footer_shows_cycle_agent_hint(board: KaganDriver) -> None:
    """Status footer in overlay mode has footer_mode='overlay' set on the panel."""
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

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        assert panel._footer_mode == "overlay"


async def test_overlay_footer_does_not_contain_ctrl_shift_t(board: KaganDriver) -> None:
    """Status footer in overlay mode must NOT contain 'Ctrl+Shift+T'."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.status_bar import StatusBar

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        assert panel._footer_mode == "overlay"

        # Read hint directly from the StatusBar reactive
        status_bar = panel.query_one(StatusBar)
        hint = status_bar.hint
        assert "Ctrl+Shift+T" not in hint
        assert "switch agent" in hint.lower() or "ctrl+up/down" in hint.lower()


# ---------------------------------------------------------------------------
# Bug C — replay does not animate historical chunks
# ---------------------------------------------------------------------------


async def test_replay_does_not_animate_historical_chunks(board: KaganDriver) -> None:
    """append_chunk with replay=True renders text immediately without spawning drain task."""
    from textual.app import App, ComposeResult

    from kagan.tui.widgets.streaming import OutputChunk, StreamingOutput

    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield StreamingOutput(id="out")

    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        output = app.query_one(StreamingOutput)

        output.append_chunk("Hello ", kind="assistant", merge=False, replay=True)
        output.append_chunk("world", kind="assistant", merge=True, replay=True)
        await pilot.pause()

        chunks = list(output.query(OutputChunk))
        assert chunks, "Expected at least one OutputChunk after replay"
        combined = " ".join(c._accumulated_text for c in chunks)
        assert "Hello" in combined
        assert "world" in combined

        # No drain task should be running for replay chunks
        for chunk in chunks:
            assert chunk._drain_task is None or chunk._drain_task.done(), (
                "Drain task unexpectedly running after replay — animation should be skipped"
            )


# ---------------------------------------------------------------------------
# Bug D — Ctrl+Down cycles attached session
# ---------------------------------------------------------------------------


async def test_ctrl_down_cycles_selected_session(board: KaganDriver) -> None:
    """Ctrl+Down rotates selection: orchestrator → row1 → row2 → orchestrator."""

    from kagan.core._session_items import SessionCapabilities, SessionItem
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.session_list import SessionList

    def _make_item(session_id: str, task_id: str, title: str) -> SessionItem:
        return SessionItem(
            id=session_id,
            type="task",
            role="worker",
            status="running",
            title=title,
            backend="claude",
            project_id=None,
            task_id=task_id,
            session_id=session_id,
            chat_session_id=None,
            updated_at="",
            capabilities=SessionCapabilities(
                can_chat=False,
                can_stream=False,
                can_replay=True,
                can_stop=True,
                can_close=False,
                has_kagan_tools=True,
            ),
        )

    item1 = _make_item("sess-aaa", "task-1", "Task Alpha")
    item2 = _make_item("sess-bbb", "task-2", "Task Beta")

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)
        assert overlay._selected_session_id is None

        # Inject fake items into the session list
        session_list = overlay.query_one("#orch-session-list", SessionList)
        session_list._items = [item1, item2]
        await pilot.pause()

        # Ctrl+Down: orchestrator → row1
        await pilot.press("ctrl+down")
        await pilot.pause()
        await pilot.pause()
        assert overlay._selected_session_id == "sess-aaa"

        # Ctrl+Down: row1 → row2
        await pilot.press("ctrl+down")
        await pilot.pause()
        await pilot.pause()
        assert overlay._selected_session_id == "sess-bbb"

        # Ctrl+Down: row2 → orchestrator (wrap around)
        await pilot.press("ctrl+down")
        await pilot.pause()
        await pilot.pause()
        assert overlay._selected_session_id is None
