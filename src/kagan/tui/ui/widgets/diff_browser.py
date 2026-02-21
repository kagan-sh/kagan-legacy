"""Split-pane diff browser widget: file picker on the left, diff view on the right."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static

from kagan.tui.ui.utils.helpers import colorize_diff

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from textual import events
    from textual.app import ComposeResult


# ---------------------------------------------------------------------------
# Internal data model
# ---------------------------------------------------------------------------


@dataclass
class _FileEntry:
    path: str
    status: str  # "ADDED" | "MODIFIED" | "DELETED"
    additions: int
    deletions: int
    diff_content: str


@dataclass
class _RepoNode:
    repo_id: str
    repo_name: str
    target_branch: str
    total_additions: int
    total_deletions: int
    files: list[_FileEntry]
    expanded: bool = True


# ---------------------------------------------------------------------------
# Left pane: file tree
# ---------------------------------------------------------------------------


class DiffFileTree(Widget):
    """Scrollable file picker listing repos and their changed files."""

    BINDINGS: list[BindingType] = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("enter", "select", "Select", show=False),
    ]

    can_focus = True

    _cursor: reactive[int] = reactive(0)
    _repos: reactive[list[_RepoNode]] = reactive([], recompose=True)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class FileSelected(Message):
        def __init__(self, repo_id: str, entry: _FileEntry) -> None:
            super().__init__()
            self.repo_id = repo_id
            self.entry = entry

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _flat_items(self) -> list[tuple[_RepoNode, _FileEntry | None]]:
        """Return ordered flat list of (repo, file|None) pairs for cursor math."""
        items: list[tuple[_RepoNode, _FileEntry | None]] = []
        for repo in self._repos:
            items.append((repo, None))
            if repo.expanded:
                for entry in repo.files:
                    items.append((repo, entry))
        return items

    def set_repos(self, nodes: list[_RepoNode]) -> None:
        self._repos = nodes
        self.recompose()  # force recompose — reactive skips [] == [] equality

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        flat = self._flat_items()
        cursor = self._cursor

        # Clamp cursor in case repos changed
        if flat and cursor >= len(flat):
            cursor = len(flat) - 1

        idx = 0
        for repo in self._repos:
            arrow = "▼" if repo.expanded else "▶"
            header_text = (
                f"{arrow} {repo.repo_name}  +{repo.total_additions} -{repo.total_deletions}"
            )
            header_classes = "diff-tree-repo-header"
            if not repo.files:
                header_classes += " no-changes"
            selected = idx == cursor
            if selected:
                header_classes += " cursor"
            yield Static(header_text, classes=header_classes, markup=False)
            idx += 1

            if repo.expanded:
                for entry in repo.files:
                    glyph = {"MODIFIED": "[●]", "ADDED": "[+]", "DELETED": "[-]"}.get(
                        entry.status.upper(), "[?]"
                    )
                    status_class = entry.status.lower()
                    file_classes = f"diff-tree-file-row {status_class}"
                    if idx == cursor:
                        file_classes += " cursor"
                    yield Static(f"{glyph} {entry.path}", classes=file_classes, markup=False)
                    idx += 1

        if not self._repos:
            yield Static("  (loading…)", classes="diff-tree-hint", markup=False)
        else:
            yield Static("  j/k navigate", classes="diff-tree-hint", markup=False)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        flat = self._flat_items()
        if not flat:
            return
        new = min(self._cursor + 1, len(flat) - 1)
        if new != self._cursor:
            self._cursor = new
            self.recompose()

    def action_cursor_up(self) -> None:
        if self._cursor > 0:
            self._cursor -= 1
            self.recompose()

    def action_select(self) -> None:
        flat = self._flat_items()
        if not flat:
            return
        cursor = self._cursor
        if cursor >= len(flat):
            return
        repo, entry = flat[cursor]
        if entry is None:
            repo.expanded = not repo.expanded
            self.recompose()
        else:
            self.post_message(self.FileSelected(repo.repo_id, entry))


# ---------------------------------------------------------------------------
# Right pane: diff content
# ---------------------------------------------------------------------------


class DiffContentPane(VerticalScroll):
    """Scrollable diff viewer showing the selected file's unified diff."""

    can_focus = True

    def compose(self) -> ComposeResult:
        yield Static("DIFF · (select a file)", classes="diff-content-header", id="diff-header")
        yield RichLog(
            highlight=True,
            markup=True,
            classes="diff-content-body",
            id="diff-log",
        )
        yield Static("  [a] Approve  [r] Reject  [m] Merge all", classes="diff-action-hint")

    def show_file(self, entry: _FileEntry | None) -> None:
        header = self.query_one("#diff-header", Static)
        log = self.query_one("#diff-log", RichLog)
        log.clear()
        if entry is None:
            header.update("DIFF · (select a file)")
            return
        status = entry.status.upper()
        header.update(
            f"DIFF · {entry.path}  {status}  +{entry.additions}/-{entry.deletions}"
        )
        for line in colorize_diff(entry.diff_content).splitlines():
            log.write(line)


# ---------------------------------------------------------------------------
# Main exported widget
# ---------------------------------------------------------------------------


class DiffBrowserWidget(Widget):
    """Split-pane diff browser replacing the flat WorkspaceReposWidget."""

    can_focus = False

    class ActionRequested(Message):
        def __init__(self, action: str) -> None:  # "approve" | "reject" | "merge"
            super().__init__()
            self.action = action

    def __init__(
        self,
        workspace_id: str,
        *,
        load_repos: Callable[[str], Awaitable[list[dict[str, Any]]]] | None = None,
        load_repo_diff: Callable[[str, str], Awaitable[Any | None]] | None = None,
        load_all_diffs: Callable[[str], Awaitable[list[Any]]] | None = None,
    ) -> None:
        super().__init__()
        self._workspace_id = workspace_id
        self._load_repos = load_repos
        self._load_repo_diff = load_repo_diff
        self._load_all_diffs = load_all_diffs

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield DiffFileTree(id="diff-file-tree")
            yield DiffContentPane(id="diff-content-pane")

    def on_mount(self) -> None:
        self.run_worker(
            self._load_all_repo_diffs,
            group="diff-browser-load",
            exclusive=True,
            exit_on_error=False,
        )

    async def _load_all_repo_diffs(self) -> None:
        if self._load_all_diffs is not None:
            await self._load_via_all_diffs()
        elif self._load_repos is not None:
            await self._load_via_repos()

    async def _load_via_all_diffs(self) -> None:
        """Fast path: single call returns all RepoDiff objects at once."""
        assert self._load_all_diffs is not None
        try:
            repo_diffs = await self._load_all_diffs(self._workspace_id)
        except Exception as exc:
            self.notify(f"Failed to load diffs: {exc}", severity="warning")
            self.query_one("#diff-file-tree", DiffFileTree).set_repos([])
            return

        nodes = [
            _RepoNode(
                repo_id=str(getattr(rd, "repo_id", "")),
                repo_name=str(getattr(rd, "repo_name", "")),
                target_branch=str(getattr(rd, "target_branch", "unknown")),
                total_additions=int(getattr(rd, "total_additions", 0)),
                total_deletions=int(getattr(rd, "total_deletions", 0)),
                files=[
                    _FileEntry(
                        path=f.path,
                        status=f.status.upper(),
                        additions=f.additions,
                        deletions=f.deletions,
                        diff_content=f.diff_content,
                    )
                    for f in (getattr(rd, "files", []) or [])
                ],
            )
            for rd in (repo_diffs or [])
            if str(getattr(rd, "repo_id", "")).strip()
        ]
        self.query_one("#diff-file-tree", DiffFileTree).set_repos(nodes)

    async def _load_via_repos(self) -> None:
        """Two-step path: get repo list then fetch each diff individually."""
        assert self._load_repos is not None
        try:
            repos = await self._load_repos(self._workspace_id)
        except Exception as exc:
            self.notify(f"Failed to load repos: {exc}", severity="warning")
            self.query_one("#diff-file-tree", DiffFileTree).set_repos([])
            return

        nodes: list[_RepoNode] = []
        for repo in repos:
            repo_id = str(repo.get("repo_id", "")).strip()
            if not repo_id:
                continue
            repo_name = str(repo.get("repo_name", repo_id))
            target_branch = str(repo.get("target_branch", "unknown"))
            has_changes = bool(repo.get("has_changes", False))

            if not has_changes or self._load_repo_diff is None:
                diff_stats = repo.get("diff_stats") or {}
                nodes.append(
                    _RepoNode(
                        repo_id=repo_id,
                        repo_name=repo_name,
                        target_branch=target_branch,
                        total_additions=int(diff_stats.get("insertions", 0)),
                        total_deletions=int(diff_stats.get("deletions", 0)),
                        files=[],
                    )
                )
                continue

            try:
                repo_diff = await self._load_repo_diff(self._workspace_id, repo_id)
            except Exception as exc:
                self.notify(f"Failed to load diff for {repo_name}: {exc}", severity="warning")
                repo_diff = None

            if repo_diff is None:
                diff_stats = repo.get("diff_stats") or {}
                nodes.append(
                    _RepoNode(
                        repo_id=repo_id,
                        repo_name=repo_name,
                        target_branch=target_branch,
                        total_additions=int(diff_stats.get("insertions", 0)),
                        total_deletions=int(diff_stats.get("deletions", 0)),
                        files=[],
                    )
                )
                continue

            files = [
                _FileEntry(
                    path=f.path,
                    status=f.status.upper(),
                    additions=f.additions,
                    deletions=f.deletions,
                    diff_content=f.diff_content,
                )
                for f in repo_diff.files
            ]
            nodes.append(
                _RepoNode(
                    repo_id=repo_id,
                    repo_name=repo_name,
                    target_branch=target_branch,
                    total_additions=repo_diff.total_additions,
                    total_deletions=repo_diff.total_deletions,
                    files=files,
                )
            )

        self.query_one("#diff-file-tree", DiffFileTree).set_repos(nodes)

    def on_diff_file_tree_file_selected(self, event: DiffFileTree.FileSelected) -> None:
        event.stop()
        pane = self.query_one("#diff-content-pane", DiffContentPane)
        pane.show_file(event.entry)

    def on_key(self, event: events.Key) -> None:
        if event.key == "a":
            self.post_message(self.ActionRequested("approve"))
            event.stop()
        elif event.key == "r":
            self.post_message(self.ActionRequested("reject"))
            event.stop()
        elif event.key == "m":
            self.post_message(self.ActionRequested("merge"))
            event.stop()
