from collections.abc import Sequence

from textual.reactive import reactive
from textual.widgets import Static

MAX_COMMITS = 8


class CommitsPanel(Static):
    DEFAULT_CSS = """
    CommitsPanel {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    """

    commits: reactive[list[tuple[str, str]]] = reactive(list)
    branch: reactive[str] = reactive("-")
    base: reactive[str] = reactive("-")
    is_loading: reactive[bool] = reactive(False)
    empty_message: reactive[str] = reactive("No commits")

    def on_mount(self) -> None:
        self._refresh_display()

    def set_commits(self, commits: list[tuple[str, str]], branch: str, base: str) -> None:
        self.commits = commits
        self.branch = branch.strip() or "-"
        self.base = base.strip() or "-"
        self.is_loading = False
        self._refresh_display()

    def set_loading(self, loading: bool = True) -> None:
        self.is_loading = loading
        self.commits = []
        self._refresh_display()

    def set_empty(self, message: str) -> None:
        self.is_loading = False
        self.commits = []
        self.empty_message = message
        self._refresh_display()

    def watch_commits(self, _: Sequence[tuple[str, str]]) -> None:
        self._refresh_display()

    def watch_branch(self, _: str) -> None:
        self._refresh_display()

    def watch_base(self, _: str) -> None:
        self._refresh_display()

    def watch_is_loading(self, _: bool) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        if self.is_loading:
            self.update("Loading commits...")
            return

        header = f"COMMITS ({self.branch}..{self.base})"
        if not self.commits:
            self.update(f"{header}\n{self.empty_message}")
            return

        visible = self.commits[:MAX_COMMITS]
        lines = [header]
        for short_hash, message in visible:
            lines.append(f"• {short_hash}  {message}")

        remaining = len(self.commits) - len(visible)
        if remaining > 0:
            lines.append(f"… +{remaining} more")

        self.update("\n".join(lines))


__all__ = ["CommitsPanel"]
