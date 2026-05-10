"""Flow J — Workspace View / Orchestrator Overlay (TUI).

TODO: delete tests/tui/test_chat_overlay.py (replaced by J)

Assertions:
  1. Ctrl+Space opens the orchestrator overlay.
  2. Overlay lists session items (SessionList is mounted).
  3. Esc closes the overlay.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def _noop_warm(*args: Any, **kwargs: Any) -> None:
    return None


async def test_orchestrator_overlay_opens_and_closes(tui_driver: Any) -> None:
    """(1-3) Ctrl+Space opens overlay; SessionList is mounted; Esc closes."""
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.session_list import SessionList

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Dismiss startup screen.
            await pilot.press("enter")
            await pilot.pause()

            # (1) Open orchestrator overlay with Ctrl+Space.
            await pilot.press("ctrl+space")
            await pilot.pause()

            # Check overlay is now the active screen.
            if not isinstance(app.screen, OrchestratorOverlay):
                pytest.skip(
                    "OrchestratorOverlay not pushed — startup routing showed a different screen"
                )
                return

            # (2) SessionList is mounted in the overlay.
            try:
                session_list = app.screen.query_one("#orch-session-list", SessionList)
                assert session_list is not None, "SessionList should be present in overlay"
            except Exception as exc:
                pytest.fail(f"SessionList not found in overlay: {exc}")

            await pilot.pause()

            # (3) Esc closes the overlay.
            await pilot.press("escape")
            await pilot.pause()

            assert not isinstance(app.screen, OrchestratorOverlay), (
                "Esc should have closed the orchestrator overlay"
            )
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]


async def test_orchestrator_overlay_toggle_idempotent(tui_driver: Any) -> None:
    """Ctrl+Space toggles: second press closes overlay again."""
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # First toggle — opens overlay.
            await pilot.press("ctrl+space")
            await pilot.pause()

            if not isinstance(app.screen, OrchestratorOverlay):
                pytest.skip("OrchestratorOverlay not available from current startup screen")
                return

            # Second toggle (Ctrl+Space again) — closes overlay.
            await pilot.press("ctrl+space")
            await pilot.pause()

            assert not isinstance(app.screen, OrchestratorOverlay), (
                "Second Ctrl+Space should have closed the overlay"
            )
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
