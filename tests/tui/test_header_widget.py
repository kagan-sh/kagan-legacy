import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from kagan.tui.widgets.header import KaganHeader

pytestmark = [pytest.mark.tui, pytest.mark.unit]


class _HeaderHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield KaganHeader(id="header")


async def test_github_status_hidden_when_disconnected() -> None:
    app = _HeaderHarness()

    async with app.run_test() as pilot:
        await pilot.pause()
        status = app.query_one("#header-github-status", Static)
        separator = app.query_one("#sep-github", Static)

        assert not status.display
        assert str(status.content) == ""
        assert not separator.display


async def test_github_status_uses_compact_indicator_when_connected() -> None:
    app = _HeaderHarness()

    async with app.run_test() as pilot:
        await pilot.pause()
        header = app.query_one(KaganHeader)
        header.set_connected(True)
        await pilot.pause()

        status = app.query_one("#header-github-status", Static)
        separator = app.query_one("#sep-github", Static)

        assert status.display
        assert str(status.content) == "● GH"
        assert separator.display
