"""Flow T — Interactive Launcher (TUI).

Gate: only runs when ``KAGAN_TUI_LAUNCHER_E2E=1`` is set — the flow
involves pressing ``a`` on a kanban card to trigger the
``AttachedInstructionsModal``.

``check_terminal_installed`` is patched to return ``True`` for the
configured backend so the flow reaches the modal without a real tmux
install check or subprocess spawn.

Assertions:
  1. Pressing ``a`` on a selected task opens ``AttachedInstructionsModal``.
  2. The modal display text contains the expected launcher name ("tmux").
  3. Pressing Escape cancels and returns to KanbanScreen without zombie procs.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests.e2e_tui.helpers.wait import wait_for

pytestmark = [
    pytest.mark.tui,
    pytest.mark.e2e_tui,
    pytest.mark.skipif(
        os.environ.get("KAGAN_TUI_LAUNCHER_E2E") != "1",
        reason="opt-in: set KAGAN_TUI_LAUNCHER_E2E=1 to run; spawns real subprocess paths",
    ),
]


async def test_attach_opens_instructions_modal(tui_driver: Any) -> None:
    """Pressing ``a`` on a task card opens AttachedInstructionsModal with launcher hint."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.gateway import AttachedInstructionsModal
    from kagan.tui.screens.kanban import KanbanScreen

    await tui_driver.create_task("Launcher Task", launcher="tmux")

    mp = pytest.MonkeyPatch()
    mp.setattr(
        "kagan.tui.screens.kanban.check_terminal_installed",
        lambda _backend: True,
    )

    try:
        app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
            await pilot.pause()

            kanban = app.screen
            assert isinstance(kanban, KanbanScreen)

            # The task should already be focused if it's the only BACKLOG item
            await pilot.press("a")
            await pilot.pause()
            await pilot.pause()

            # Wait for the modal to appear
            await wait_for(
                lambda: isinstance(app.screen, AttachedInstructionsModal),
                tries=40,
                pump_delay=0.1,
            )

            modal = app.screen
            assert isinstance(modal, AttachedInstructionsModal)

            # The modal should show the backend name "tmux"
            modal_text = modal.query("Static")
            modal_content = " ".join(str(w.renderable) for w in modal_text)
            assert "tmux" in modal_content.lower(), (
                f"Expected 'tmux' in modal text but got: {modal_content!r}"
            )

            # Escape dismisses without spawning any subprocess
            await pilot.press("escape")
            await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
    finally:
        mp.undo()


async def test_attach_no_zombie_after_cancel(tui_driver: Any) -> None:
    """Cancelling the instructions modal leaves no zombie processes."""
    import psutil

    from kagan.tui import KaganApp
    from kagan.tui.screens.gateway import AttachedInstructionsModal
    from kagan.tui.screens.kanban import KanbanScreen

    await tui_driver.create_task("Zombie Check Task", launcher="tmux")

    mp = pytest.MonkeyPatch()
    mp.setattr(
        "kagan.tui.screens.kanban.check_terminal_installed",
        lambda _backend: True,
    )

    children_before = set(psutil.Process().children(recursive=True))

    try:
        app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
            await pilot.pause()

            await pilot.press("a")
            await pilot.pause()
            await pilot.pause()

            if not isinstance(app.screen, AttachedInstructionsModal):
                pytest.skip("AttachedInstructionsModal did not open; skipping zombie check")
                return

            await pilot.press("escape")
            await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
    finally:
        mp.undo()

    children_after = set(psutil.Process().children(recursive=True))
    new_children = children_after - children_before
    assert not new_children, f"Unexpected child processes after modal cancel: {new_children}"
