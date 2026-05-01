"""Tests for the github_issue field on the TaskEditor widget."""

import pytest
from tests.helpers.driver import KaganDriver
from textual.widgets import Input

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def _open_new_task_editor(pilot) -> None:
    """Press n to open the new-task editor and wait for it."""
    from tests.helpers.async_utils import wait_for

    await pilot.press("enter")
    await pilot.press("n")
    await wait_for(
        lambda: getattr(pilot.app.screen, "id", None) == "task-editor-modal",
        pump_delay=0.05,
    )
    # Expand advanced options so github_issue field is visible
    await pilot.press("ctrl+period")
    await wait_for(
        lambda: bool(pilot.app.screen.query("#task-github-issue")),
        pump_delay=0.05,
    )


async def test_task_editor_shows_github_issue_field(
    board_with_task: KaganDriver,
) -> None:
    """The task editor renders a github_issue Input field in advanced options."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_new_task_editor(pilot)

        # The field must be present and have the right placeholder
        github_field = pilot.app.screen.query_one("#task-github-issue", Input)
        assert github_field is not None
        assert "none" in github_field.placeholder.lower() or "42" in github_field.placeholder


async def test_task_editor_creates_task_with_github_issue_value(
    board_with_task: KaganDriver,
) -> None:
    """Filling in the github_issue field passes the value to tasks.create()."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")

    # Patch tasks.create to capture the github_issue kwarg without actually
    # calling gh CLI (which isn't available in the test environment).
    captured: dict[str, object] = {}
    original_create = None

    async def _fake_create(title, **kwargs):
        captured.update(kwargs)
        # Delegate to the real create but strip github_issue so no gh call happens
        kwargs_no_gh = {k: v for k, v in kwargs.items() if k != "github_issue"}
        return await original_create(title, **kwargs_no_gh)  # type: ignore[misc]

    async with app.run_test() as pilot:
        await pilot.pause()
        core = app.core  # type: ignore[attr-defined]
        original_create = core.tasks.create
        core.tasks.create = _fake_create  # type: ignore[method-assign]

        await _open_new_task_editor(pilot)

        # Set title
        title_input = pilot.app.screen.query_one("#task-title", Input)
        title_input.value = "GH Issue Task"
        await pilot.pause()

        # Set github_issue
        github_field = pilot.app.screen.query_one("#task-github-issue", Input)
        github_field.value = "99"
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()

    assert captured.get("github_issue") == "99"


async def test_task_editor_edit_prepopulates_github_issue(
    board_with_task: KaganDriver,
) -> None:
    """Editing a task with an existing github_issue pre-populates the field."""
    from tests.helpers.async_utils import wait_for

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_editor_modal import TaskEditorModal

    # Create a task that has github_issue set
    tasks = await board_with_task.list_tasks()
    assert tasks, "fixture must have at least one task"
    task_id = tasks[0].id

    # Manually set github_issue on the task object used to open the editor
    # (we mock the core model since update() doesn't accept github_issue yet in this
    # code path — we're testing that the editor renders existing values)
    import types

    task = await board_with_task._driver._ctx.tasks.get(task_id)
    fake_task = types.SimpleNamespace(
        id=task.id,
        title=task.title,
        description=task.description,
        priority=task.priority,
        agent_backend=task.agent_backend,
        launcher=task.launcher,
        base_branch=task.base_branch,
        acceptance_criteria=list(task.acceptance_criteria),
        github_issue="octocat/hello#7",
    )

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.push_screen(TaskEditorModal(task=fake_task))  # type: ignore[arg-type]
        await wait_for(
            lambda: isinstance(pilot.app.screen, TaskEditorModal),
            pump_delay=0.05,
        )
        # Expand advanced options
        await pilot.press("ctrl+period")
        await wait_for(
            lambda: bool(pilot.app.screen.query("#task-github-issue")),
            pump_delay=0.05,
        )

        github_field = pilot.app.screen.query_one("#task-github-issue", Input)
        assert github_field.value == "octocat/hello#7"
