from types import SimpleNamespace

import pytest
from tests.helpers.async_utils import wait_for
from tests.helpers.driver import KaganDriver
from textual.widgets import Input, SelectionList, Static

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


class _AsyncSpy:
    """Async callable that records the most-recent call."""

    def __init__(self, return_value=None) -> None:
        self._return_value = return_value
        self.await_count = 0
        self.await_args: SimpleNamespace | None = None

    async def __call__(self, *args, **kwargs) -> object:
        self.await_count += 1
        self.await_args = SimpleNamespace(args=args, kwargs=kwargs)
        return self._return_value

    def assert_awaited_once(self) -> None:
        assert self.await_count == 1, f"expected 1 call, got {self.await_count}"


async def _open_github_import_modal(app) -> None:
    from kagan.tui.screens.github_import_modal import GitHubImportModal

    await app.push_screen(GitHubImportModal())
    await wait_for(
        lambda: app.screen.__class__.__name__ == "GitHubImportModal"
        and bool(app.screen.query("#github-import-repo")),
        pump_delay=0.05,
    )


def _issue(number: int, title: str, *, already_synced: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(number),
        title=title,
        state="open",
        labels=("area:ui",),
        already_synced=already_synced,
        extra={"number": number},
    )


async def test_github_import_preview_shows_fetched_issues(
    board_with_task: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    preview = _AsyncSpy(return_value=[_issue(10, "Fix the preview")])

    monkeypatch.setattr(
        "kagan.tui.screens.github_import_modal.github_preflight_checks",
        _AsyncSpy(return_value=[]),
    )
    monkeypatch.setattr(
        "kagan.tui.screens.github_import_modal.preview_github_issues",
        preview,
    )

    async with app.run_test() as pilot:
        await wait_for(lambda: app.screen.id == "kanban-screen", pump_delay=0.05)
        await _open_github_import_modal(app)

        app.screen.query_one("#github-import-repo", Input).value = "owner/repo"
        await pilot.press("enter")

        await wait_for(
            lambda: app.screen.query_one("#github-import-selection", SelectionList).display,
            pump_delay=0.05,
        )

        selection = app.screen.query_one("#github-import-selection", SelectionList)
        status = app.screen.query_one("#github-import-status", Static)
        assert selection.option_count == 1
        assert list(selection.selected) == [10]
        assert "1 issue found" in str(status.content)

    preview.assert_awaited_once()


async def test_github_import_selected_issues_sync_and_close(
    board_with_task: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.core.integrations import ImportResult
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    preview = _AsyncSpy(return_value=[_issue(10, "Fix the preview")])
    sync = _AsyncSpy(return_value=ImportResult(created=1))

    monkeypatch.setattr(
        "kagan.tui.screens.github_import_modal.github_preflight_checks",
        _AsyncSpy(return_value=[]),
    )
    monkeypatch.setattr(
        "kagan.tui.screens.github_import_modal.preview_github_issues",
        preview,
    )
    monkeypatch.setattr(
        "kagan.tui.screens.github_import_modal.sync_github_issues",
        sync,
    )

    async with app.run_test() as pilot:
        await wait_for(lambda: app.screen.id == "kanban-screen", pump_delay=0.05)
        await _open_github_import_modal(app)

        app.screen.query_one("#github-import-repo", Input).value = "owner/repo"
        await pilot.press("enter")
        await wait_for(
            lambda: app.screen.query_one("#github-import-selection", SelectionList).display,
            pump_delay=0.05,
        )

        await pilot.press("enter")
        await wait_for(lambda: app.screen.id == "kanban-screen", pump_delay=0.05)

    sync.assert_awaited_once()
    assert sync.await_args.kwargs["repo_slug"] == "owner/repo"
    assert sync.await_args.kwargs["issue_numbers"] == [10]
