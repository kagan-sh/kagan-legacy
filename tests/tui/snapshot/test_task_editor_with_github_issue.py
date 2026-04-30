"""Snapshot test — TaskEditor with the github_issue field visible.

Run with: ``uv run poe test-snapshot``
Seed baseline: ``uv run poe snapshot-update``
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.snapshot]


async def test_snapshot_task_editor_shows_github_issue_field(
    board_with_task: KaganDriver,
) -> None:
    """Task editor with advanced options expanded shows the github_issue field."""
    from textual.widgets import Input

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        # Navigate to the board and open new-task editor
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

        # Expand advanced options
        await pilot.press("ctrl+period")
        await pilot.pause()

        # Confirm github_issue field is rendered
        assert pilot.app.screen.query_one("#task-github-issue", Input) is not None
