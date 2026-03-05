import pytest
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Static

from kagan.tui.widgets.diff import DiffView

pytestmark = [pytest.mark.tui, pytest.mark.unit]


class _DiffHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield DiffView(id="diff-view", default_focus="content")


async def test_diff_view_renders_structured_unified_diff() -> None:
    app = _DiffHarness()
    diff_text = "\n".join(
        [
            "diff --git a/main.py b/main.py",
            "index 1111111..2222222 100644",
            "--- a/main.py",
            "+++ b/main.py",
            "@@ -1,2 +1,3 @@",
            " line0",
            "-line1",
            "+line1_changed",
            "+line2",
        ]
    )

    async with app.run_test() as pilot:
        view = app.query_one(DiffView)
        view.set_diff(diff_text)
        await pilot.pause()
        view.set_selected_file("main.py")
        await pilot.pause()

        log = app.query_one("#diff-log", Static)
        content = log.content
        assert isinstance(content, Text)
        assert "+line1_changed" in content.plain
        assert "-line1" in content.plain
        assert "@@ -1,2 +1,3 @@" in content.plain
        assert "│" in content.plain


async def test_diff_view_preserves_selected_file_across_refresh() -> None:
    app = _DiffHarness()
    diff_text = "\n".join(
        [
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1 +1 @@",
            "-old",
            "+new",
            "diff --git a/b.py b/b.py",
            "--- a/b.py",
            "+++ b/b.py",
            "@@ -1 +1 @@",
            "-left",
            "+right",
        ]
    )

    async with app.run_test() as pilot:
        view = app.query_one(DiffView)
        view.set_diff(diff_text)
        await pilot.pause()
        view.set_selected_file("b.py")
        await pilot.pause()

        assert view.current_file_path() == "b.py"

        view.set_diff(diff_text)
        await pilot.pause()

        assert view.current_file_path() == "b.py"
