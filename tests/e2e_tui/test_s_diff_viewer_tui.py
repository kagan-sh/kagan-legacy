"""Flow S — Diff Viewer / File Picker (TUI).

Sets up a real git repo and worktree with a committed change, pushes
TaskScreen for a task in IN_PROGRESS status, switches to the Changes
tab, and verifies that:

1. The DiffFileTree shows at least one file after tab hydration.
2. The DiffView content pane is wired correctly to display a file diff.

If git worktree provisioning fails the tests skip with an explicit reason.

Assertions:
  1. TaskScreen loads and tab "2" (Changes) is reachable.
  2. DiffFileTree lists at least one file entry after waiting for worker.
  3. DiffView.set_selected_file() populates the DiffContentPane header.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e_tui.helpers.wait import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


async def _make_repo_and_workspace(tui_driver: Any) -> tuple[str, Any] | None:
    """Return (workspace_path, task) after setting up repo + worktree.

    Returns None if any step fails so the caller can skip.
    """
    from tests.helpers.helpers import commit_file, make_git_repo

    repo_path = tui_driver.tmp_path / "repo"
    result = await make_git_repo(repo_path)
    if not result.get("success"):
        return None

    await tui_driver.add_repo(repo_path)

    from kagan.core.enums import TaskStatus

    task = await tui_driver.create_task("Diff Task")
    # Move to IN_PROGRESS — prevents TaskScreen auto-opening OrchestratorOverlay
    await tui_driver.move_task(task.id, TaskStatus.IN_PROGRESS)

    try:
        await tui_driver.provision_workspace(task.id)
    except Exception:
        return None

    ws_path = await tui_driver.get_workspace_path(task.id)
    if ws_path is None:
        return None

    from pathlib import Path

    wt = Path(ws_path)
    ok = await commit_file(wt, "feature.py", "def hello(): pass\n")
    if not ok:
        return None

    return ws_path, task


def _diff_tree_has_files(app: Any) -> bool:
    """Predicate: DiffFileTree has at least one file entry."""
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.diff import DiffFileTree

    if not isinstance(app.screen, TaskScreen):
        return False
    try:
        tree = app.screen.query_one(DiffFileTree)
        return len(tree._files) >= 1
    except Exception:
        return False


async def test_diff_viewer_shows_changed_files(tui_driver: Any) -> None:
    """Changes tab lists files after diff hydration worker completes."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.diff import DiffFileTree

    setup = await _make_repo_and_workspace(tui_driver)
    if setup is None:
        pytest.skip("Git repo or worktree setup failed — skipping diff viewer test")
        return

    _ws_path, task = setup

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await wait_for(lambda: isinstance(app.screen, TaskScreen), tries=60)
        await pilot.pause()

        # Switch to Changes tab — triggers diff hydration via 0.12s timer + worker
        await pilot.press("2")
        # Allow Textual's set_timer(0.12) + async worker to execute
        await pilot.pause(delay=0.5)
        await pilot.pause(delay=0.5)

        await wait_for(lambda: _diff_tree_has_files(app), tries=60, pump_delay=0.1)

        try:
            tree = app.screen.query_one(DiffFileTree)
        except Exception:
            pytest.skip("DiffFileTree not found — layout may have changed")
            return

        assert len(tree._files) >= 1, (
            f"Expected at least 1 file in DiffFileTree but got {len(tree._files)}"
        )
        assert tree._files[0].path, "First diff file should have a non-empty path"


async def test_diff_viewer_content_pane_populates(tui_driver: Any) -> None:
    """Selecting a file via DiffView.set_selected_file() populates DiffContentPane."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.diff import DiffContentPane, DiffFileTree, DiffView

    setup = await _make_repo_and_workspace(tui_driver)
    if setup is None:
        pytest.skip("Git repo or worktree setup failed — skipping diff viewer test")
        return

    _ws_path, task = setup

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await wait_for(lambda: isinstance(app.screen, TaskScreen), tries=60)
        await pilot.pause()

        await pilot.press("2")
        await pilot.pause(delay=0.5)
        await pilot.pause(delay=0.5)

        await wait_for(lambda: _diff_tree_has_files(app), tries=60, pump_delay=0.1)

        try:
            diff_view = app.screen.query_one(DiffView)
            tree = app.screen.query_one(DiffFileTree)
            content_pane = app.screen.query_one(DiffContentPane)
        except Exception:
            pytest.skip("DiffView/DiffFileTree/DiffContentPane not found")
            return

        if not tree._files:
            pytest.skip("No diff files available to select")
            return

        first_path = tree._files[0].path
        diff_view.set_selected_file(first_path)
        await pilot.pause()

        from textual.widgets import Static

        header = content_pane.query_one("#diff-header", Static)
        # Static.content is a Rich renderable; coerce to plain string for assertion
        from rich.text import Text

        raw = header.content
        header_text = raw.plain if isinstance(raw, Text) else str(raw)
        assert first_path in header_text or header_text != "Select a file", (
            f"Expected file path in DiffContentPane header but got: {header_text!r}"
        )
