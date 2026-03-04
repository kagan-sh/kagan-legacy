from collections.abc import Mapping

from textual.reactive import reactive
from textual.widgets import Static

STATUS_MARKERS = {
    "modified": "M",
    "added": "A",
    "deleted": "D",
    "renamed": "R",
}


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return default


class WorktreePanel(Static):
    DEFAULT_CSS = """
    WorktreePanel {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    """

    files: reactive[list[dict[str, object]]] = reactive(list)
    stats: reactive[dict[str, int]] = reactive(dict)
    is_loading: reactive[bool] = reactive(False)
    empty_message: reactive[str] = reactive("No changes")

    def on_mount(self) -> None:
        self._refresh_display()

    def set_changes(self, files: list[dict[str, object]], stats: dict[str, int]) -> None:
        self.files = files
        self.stats = stats
        self.is_loading = False
        self._refresh_display()

    def set_loading(self, loading: bool = True) -> None:
        self.is_loading = loading
        self.files = []
        self.stats = {}
        self._refresh_display()

    def set_empty(self, message: str) -> None:
        self.is_loading = False
        self.files = []
        self.stats = {}
        self.empty_message = message
        self._refresh_display()

    def watch_files(self, _: list[dict[str, object]]) -> None:
        self._refresh_display()

    def watch_stats(self, _: Mapping[str, int]) -> None:
        self._refresh_display()

    def watch_is_loading(self, _: bool) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        if self.is_loading:
            self.update("Loading worktree changes...")
            return
        if not self.files:
            self.update(self.empty_message)
            return

        files_changed = int(self.stats.get("files", len(self.files)))
        insertions = int(self.stats.get("insertions", 0))
        deletions = int(self.stats.get("deletions", 0))
        lines = [f"{files_changed} files changed · +{insertions} / -{deletions}"]

        for entry in self.files:
            lines.append(self._format_file_entry(entry))

        self.update("\n".join(lines))

    def _format_file_entry(self, entry: Mapping[str, object]) -> str:
        status = str(entry.get("status", "?")).strip().lower()
        marker = STATUS_MARKERS.get(status, status[:1].upper() if status else "?")
        path = str(entry.get("path", "-")).strip() or "-"
        insertions = _as_int(entry.get("insertions", 0))
        deletions = _as_int(entry.get("deletions", 0))
        return f"{marker} {path}  +{insertions} -{deletions}"


__all__ = ["WorktreePanel"]
