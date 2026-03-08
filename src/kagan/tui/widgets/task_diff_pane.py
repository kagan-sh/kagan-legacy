from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from kagan.tui.widgets.diff import DiffView


class TaskDiffPane(Widget):
    DEFAULT_CSS = """
    TaskDiffPane {
        height: 1fr;
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Workspace", id="ts-workspace-bar", classes="ts-workspace-bar loading")
            yield DiffView(id="ts-diff-view", default_focus="content")

    def update_workspace_bar(
        self,
        text: str,
        *,
        loading: bool = False,
        no_workspace: bool = False,
    ) -> None:
        bar = self.query_one("#ts-workspace-bar", Static)
        bar.update(text)
        bar.set_class(loading, "loading")
        bar.set_class(no_workspace, "ts-no-workspace")

    def update_diff(self, diff_text: str) -> None:
        self.query_one("#ts-diff-view", DiffView).set_diff(diff_text)

    def get_diff_view(self) -> DiffView:
        return self.query_one("#ts-diff-view", DiffView)

    def get_workspace_bar(self) -> Static:
        return self.query_one("#ts-workspace-bar", Static)
