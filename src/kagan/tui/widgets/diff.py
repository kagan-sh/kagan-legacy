import re
from dataclasses import dataclass
from typing import ClassVar, Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


@dataclass(frozen=True, slots=True)
class _DiffFile:
    path: str
    status: str
    insertions: int
    deletions: int
    diff_text: str


class DiffStats(Static):
    def __init__(
        self,
        files: int = 0,
        insertions: int = 0,
        deletions: int = 0,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__("", id=id, classes=classes)
        self._files = files
        self._insertions = insertions
        self._deletions = deletions
        self._refresh_display()

    def set_stats(self, files: int, insertions: int, deletions: int) -> None:
        self._files = max(files, 0)
        self._insertions = max(insertions, 0)
        self._deletions = max(deletions, 0)
        self._refresh_display()

    def _refresh_display(self) -> None:
        total = self._insertions + self._deletions
        insert_ratio = 0 if total == 0 else round((self._insertions / total) * 10)
        deletion_ratio = 10 - insert_ratio
        bar = "" if total == 0 else "\u2588" * insert_ratio + "\u2591" * deletion_ratio
        suffix = f" {bar}" if bar else ""
        self.update(f"{self._files} files  +{self._insertions} -{self._deletions}{suffix}")


class DiffFileTree(Widget):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j,down", "cursor_down", "Next file", show=True),
        Binding("k,up", "cursor_up", "Prev file", show=True),
        Binding("enter", "select", "Select", show=True),
    ]

    can_focus = True
    DEFAULT_CSS = """
    DiffFileTree {
        width: 1fr;
        height: 1fr;
        min-width: 24;
        background: $surface;
        border: none;
    }
    DiffFileTree .diff-tree-panel-title {
        color: $text-muted;
        text-style: bold;
        padding: 0 1;
        height: 1;
        background: $panel;
    }
    DiffFileTree .diff-tree-hint {
        color: $text-disabled;
        padding: 1;
        height: 1;
    }
    DiffFileTree .diff-tree-file-row {
        padding: 0 1;
        height: 1;
    }
    DiffFileTree .diff-tree-file-row.added {
        color: $success;
    }
    DiffFileTree .diff-tree-file-row.deleted {
        color: $error;
    }
    DiffFileTree .diff-tree-file-row.modified {
        color: $warning;
    }
    DiffFileTree .diff-tree-file-row.cursor {
        background: $primary 20%;
        text-style: bold;
    }
    """

    _cursor: reactive[int] = reactive(0)
    _files: reactive[list[_DiffFile]] = reactive(list, recompose=True)

    class FileSelected(Message):
        def __init__(self, entry: _DiffFile | None) -> None:
            super().__init__()
            self.entry = entry

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._empty_message = "No files"

    def compose(self) -> ComposeResult:
        yield Static("Files", classes="diff-tree-panel-title")

        if not self._files:
            yield Static(f"  {self._empty_message}", classes="diff-tree-hint")
            return

        for index, entry in enumerate(self._files):
            row_classes = f"diff-tree-file-row {entry.status.lower()}"
            if index == self._cursor:
                row_classes += " cursor"
            # Cleaner markers: ◈ modified, + added, - deleted
            marker = {"added": "+", "deleted": "-", "modified": "◈"}.get(
                entry.status.lower(),
                "?",
            )
            has_changes = entry.insertions or entry.deletions
            stats = f" +{entry.insertions}/-{entry.deletions}" if has_changes else ""
            yield Static(f"{marker} {entry.path}{stats}", classes=row_classes)

        yield Static("j/k navigate · Enter · h/l panes", classes="diff-tree-hint")

    def set_files(self, files: list[_DiffFile], *, empty_message: str = "No files") -> None:
        self._files = files
        self._empty_message = empty_message
        if not files:
            self._cursor = 0
            self.refresh(recompose=True)
            self.post_message(self.FileSelected(None))
            return
        self._cursor = min(self._cursor, len(files) - 1)
        self.refresh(recompose=True)
        self._publish_selection()

    def selected_file(self) -> _DiffFile | None:
        if not self._files:
            return None
        if self._cursor < 0 or self._cursor >= len(self._files):
            return None
        return self._files[self._cursor]

    def select_next(self) -> None:
        if not self._files:
            return
        self._cursor = min(self._cursor + 1, len(self._files) - 1)
        self.refresh(recompose=True)
        self._publish_selection()

    def select_previous(self) -> None:
        if not self._files:
            return
        self._cursor = max(self._cursor - 1, 0)
        self.refresh(recompose=True)
        self._publish_selection()

    def action_cursor_down(self) -> None:
        self.select_next()

    def action_cursor_up(self) -> None:
        self.select_previous()

    def action_select(self) -> None:
        self._publish_selection()

    def _publish_selection(self) -> None:
        self.post_message(self.FileSelected(self.selected_file()))


class DiffContentPane(Widget):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j,down", "scroll_down", "Scroll down", show=True),
        Binding("k,up", "scroll_up", "Scroll up", show=True),
        Binding("f,pagedown", "page_down", "Page down", show=True),
        Binding("b,pageup", "page_up", "Page up", show=True),
        Binding("g,home", "scroll_home", "Top", show=True),
        Binding("G,end", "scroll_end", "Bottom", show=True),
    ]

    can_focus = True
    DEFAULT_CSS = """
    DiffContentPane {
        width: 2fr;
        height: 1fr;
        background: $background;
        border: none;
    }
    DiffContentPane .diff-content-header {
        color: $text-muted;
        text-style: bold;
        padding: 0 1;
        height: 1;
        background: $panel;
    }
    DiffContentPane .diff-content-body {
        padding: 0 1;
        height: auto;
    }
    DiffContentPane .diff-action-hint {
        color: $text-disabled;
        padding: 0 1;
        height: 1;
        dock: bottom;
    }
    DiffContentPane #diff-log {
        height: 1fr;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Select a file", classes="diff-content-header", id="diff-header")
        yield DiffStats(id="diff-stats", classes="diff-content-body")
        yield Static("No changes", id="diff-log", classes="diff-content-body")
        yield Static("j/k scroll · f/b page · g/G home/end", classes="diff-action-hint")

    def show_file(self, entry: _DiffFile | None) -> None:
        header = self.query_one("#diff-header", Static)
        stats = self.query_one("#diff-stats", DiffStats)
        body = self.query_one("#diff-log", Static)
        if entry is None:
            header.update("Select a file")
            stats.set_stats(0, 0, 0)
            body.update("No changes")
            return

        status_marker = {"added": "NEW", "deleted": "DEL", "modified": "MOD"}.get(
            entry.status.lower(), entry.status.upper()
        )
        header.update(f"{entry.path}  {status_marker}  +{entry.insertions}/-{entry.deletions}")
        stats.set_stats(1, entry.insertions, entry.deletions)
        body.update(_render_diff(entry.diff_text))

    def action_scroll_down(self) -> None:
        self.query_one("#diff-log", Static).scroll_down(animate=False)

    def action_scroll_up(self) -> None:
        self.query_one("#diff-log", Static).scroll_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one("#diff-log", Static).scroll_page_down(animate=False)

    def action_page_up(self) -> None:
        self.query_one("#diff-log", Static).scroll_page_up(animate=False)

    def action_scroll_home(self) -> None:
        self.query_one("#diff-log", Static).scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        self.query_one("#diff-log", Static).scroll_end(animate=False)


class DiffView(Widget):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("h,left", "focus_file_tree", "Files", show=True),
        Binding("l,right", "focus_diff_content", "Diff", show=True),
    ]

    def __init__(
        self,
        *,
        id: str | None = None,
        classes: str | None = None,
        default_focus: Literal["tree", "content"] = "tree",
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._diff_text = ""
        self._files: list[_DiffFile] = []
        self._default_focus = default_focus

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal

        with Horizontal(id="diff-browser", classes="diff-browser"):
            yield DiffFileTree(id="diff-file-tree")
            yield DiffContentPane(id="diff-content-pane")

    def on_mount(self) -> None:
        self.call_after_refresh(self._focus_default_pane)

    def _focus_default_pane(self) -> None:
        if self._default_focus == "content":
            self.query_one(DiffContentPane).focus()
            return
        self.query_one(DiffFileTree).focus()

    def action_focus_file_tree(self) -> None:
        self.query_one(DiffFileTree).focus()

    def action_focus_diff_content(self) -> None:
        self.query_one(DiffContentPane).focus()

    def set_diff(self, diff_text: str) -> None:
        self._diff_text = diff_text.strip()
        self._files = _parse_diff_files(self._diff_text)
        self.query_one(DiffFileTree).set_files(
            self._files,
            empty_message="No changed files",
        )

    def append_diff(self, diff_text: str) -> None:
        if not diff_text.strip():
            return
        cleaned = diff_text.strip()
        combined = cleaned if not self._diff_text else f"{self._diff_text}\n{cleaned}"
        self.set_diff(combined)

    def set_selected_file(self, path: str | None) -> None:
        if path is None:
            self.query_one(DiffContentPane).show_file(None)
            return
        for index, entry in enumerate(self._files):
            if entry.path != path:
                continue
            tree = self.query_one(DiffFileTree)
            tree._cursor = index
            tree.refresh(recompose=True)
            tree._publish_selection()
            return

    def current_file_path(self) -> str | None:
        entry = self.query_one(DiffFileTree).selected_file()
        return entry.path if entry is not None else None

    def select_next_file(self) -> None:
        self.query_one(DiffFileTree).select_next()

    def select_previous_file(self) -> None:
        self.query_one(DiffFileTree).select_previous()

    def focus_file_tree(self) -> None:
        self.query_one(DiffFileTree).focus()

    def focus_diff_content(self) -> None:
        self.query_one(DiffContentPane).focus()

    def on_diff_file_tree_file_selected(self, event: DiffFileTree.FileSelected) -> None:
        event.stop()
        self.query_one(DiffContentPane).show_file(event.entry)


def _parse_diff_files(diff_text: str) -> list[_DiffFile]:
    if not diff_text:
        return []

    parts = re.split(r"(?=^diff --git a/)", diff_text, flags=re.MULTILINE)
    files: list[_DiffFile] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        match = re.search(r"^diff --git a/(.+?) b/(.+)$", cleaned, flags=re.MULTILINE)
        if match is None:
            continue
        path = match.group(2).strip()
        status = _detect_status(cleaned)
        insertions = 0
        deletions = 0
        for line in cleaned.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                insertions += 1
            elif line.startswith("-"):
                deletions += 1
        files.append(
            _DiffFile(
                path=path,
                status=status,
                insertions=insertions,
                deletions=deletions,
                diff_text=cleaned,
            )
        )
    return files


def _detect_status(diff_text: str) -> str:
    lowered = diff_text.lower()
    if "new file mode" in lowered or "\n--- /dev/null" in lowered:
        return "added"
    if "deleted file mode" in lowered or "\n+++ /dev/null" in lowered:
        return "deleted"
    return "modified"


def _render_diff(diff_text: str) -> Text:
    if not diff_text.strip():
        return Text("No changes", style="dim")

    rendered = Text()
    old_line: int | None = None
    new_line: int | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("@@"):
            match = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
            if match is not None:
                old_line = int(match.group(1))
                new_line = int(match.group(2))
            rendered.append(f"{_line_prefix(None, None)}{raw_line}\n", style="bold cyan")
            continue

        if raw_line.startswith("diff --git"):
            rendered.append("\n")
            rendered.append(f"{_line_prefix(None, None)}{raw_line}\n", style="bold")
            old_line = None
            new_line = None
            continue

        if raw_line.startswith(
            ("index ", "new file mode", "deleted file mode", "similarity index")
        ):
            rendered.append(f"{_line_prefix(None, None)}{raw_line}\n", style="dim")
            continue

        if raw_line.startswith("---"):
            rendered.append(f"{_line_prefix(None, None)}{raw_line}\n", style="red")
            continue

        if raw_line.startswith("+++"):
            rendered.append(f"{_line_prefix(None, None)}{raw_line}\n", style="green")
            continue

        if raw_line.startswith("+"):
            rendered.append(f"{_line_prefix(None, new_line)}{raw_line}\n", style="green")
            if new_line is not None:
                new_line += 1
            continue

        if raw_line.startswith("-"):
            rendered.append(f"{_line_prefix(old_line, None)}{raw_line}\n", style="red")
            if old_line is not None:
                old_line += 1
            continue

        rendered.append(f"{_line_prefix(old_line, new_line)}{raw_line}\n")
        if old_line is not None:
            old_line += 1
        if new_line is not None:
            new_line += 1

    rendered.rstrip()
    return rendered


def _line_prefix(old_line: int | None, new_line: int | None) -> str:
    left = "" if old_line is None else str(old_line)
    right = "" if new_line is None else str(new_line)
    return f"{left:>5} {right:>5} │ "
