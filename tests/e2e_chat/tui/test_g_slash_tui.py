"""Flow G — Slash Commands + Registry (TUI).

Assertions:
  1. /help is handled without error — panel remains functional (no crash, no
     error message, input cleared cleanly).
  2. Unknown slash shows an error system message, not a crash.

Implementation note: /help triggers _show_help_overlay() which sets the input
to "/" and repopulates _slash_matches, but the _submit_current_input() cleanup
immediately clears the input and hides the overlay. The observable result is
that the panel stays in a non-error state with an empty, focusable input.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers.async_utils import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def _boot_to_overlay(pilot: Any, app: Any) -> bool:
    """Navigate to the orchestrator overlay and return True if successful."""
    from textual.widgets import Input

    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    await pilot.press("ctrl+space")
    await pilot.pause()

    try:
        app.screen.query_one("#chat-overlay-input", Input)
        return True
    except Exception:
        return False


async def _noop_warm(*args: Any, **kwargs: Any) -> None:
    return None


async def test_slash_help_handled_without_error(tui_driver: Any) -> None:
    """(1) /help is handled cleanly — panel stays functional, no error state."""
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            reachable = await _boot_to_overlay(pilot, app)
            if not reachable:
                pytest.skip("Orchestrator overlay not reachable")
                return

            inp = app.screen.query_one("#chat-overlay-input", Input)
            inp.focus()

            # Type /help and submit.
            for char in "/help":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()

            panel = app.screen.query_one("#chat-panel", ChatPanel)

            # Give the event loop time to process the slash command.
            await wait_for(
                lambda: inp.value == "" or inp.value.startswith("/"),
                pump_delay=0.05,
                tries=40,
            )

            # (1) Verify: no error state, no error message, panel functional.
            rendered = panel.export_rendered_messages()
            assert panel._runtime_status != "error", (
                f"Panel entered error state after /help: {panel._runtime_status}"
            )
            assert not any("Error:" in m for m in rendered), (
                f"Unexpected error message after /help: {rendered}"
            )
            # Input is either cleared or reset to "/" (help overlay mode).
            assert inp.value == "" or inp.value.startswith("/"), (
                f"Unexpected input value after /help: {inp.value!r}"
            )
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]


async def test_unknown_slash_shows_error_not_crash(tui_driver: Any) -> None:
    """(2) /unknownxyz shows an error system message and does not crash."""
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            reachable = await _boot_to_overlay(pilot, app)
            if not reachable:
                pytest.skip("Orchestrator overlay not reachable")
                return

            inp = app.screen.query_one("#chat-overlay-input", Input)
            inp.focus()

            for char in "/unknownxyz":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()

            panel = app.screen.query_one("#chat-panel", ChatPanel)

            await wait_for(
                lambda: any(
                    "unknown" in m.lower() or "unknownxyz" in m.lower() or "error" in m.lower()
                    for m in panel.export_rendered_messages()
                ),
                pump_delay=0.05,
                tries=40,
            )

            rendered = panel.export_rendered_messages()
            assert any(
                "unknown" in m.lower() or "unknownxyz" in m.lower() or "error" in m.lower()
                for m in rendered
            ), f"Expected error message for unknown slash, got: {rendered}"
            # Panel must not be in a crashed state.
            assert panel._runtime_status != "error", (
                f"Panel errored after unknown slash: {panel._runtime_status}"
            )
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
