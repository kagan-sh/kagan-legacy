"""Modal for viewing git diffs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Label, RichLog, Rule, Static, TabbedContent, TabPane

from kagan.tui.keybindings import DIFF_BINDINGS
from kagan.tui.ui.utils.helpers import colorize_diff, copy_with_notification

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.core.services.workspaces import RepoDiff
    from kagan.tui.ui.types import TaskView


class DiffModal(ModalScreen[str | None]):
    """Modal for showing task diffs.

    Returns:
        str | None:
            - "approve" if user pressed 'a'
            - "reject" if user pressed 'r'
            - None if user just closed the modal
    """

    BINDINGS = DIFF_BINDINGS

    def __init__(
        self,
        *,
        title: str | None = None,
        diff_text: str | None = None,
        diffs: list[RepoDiff] | None = None,
        task: TaskView | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._title = title or "WORKSPACE DIFF"
        self._diff_text = diff_text or ""
        self._diffs = diffs or []
        self._task_model = task

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-container"):
            yield Label(self._title, classes="modal-title")
            if self._diffs:
                with TabbedContent():
                    for diff in self._diffs:
                        tab_label = (
                            f"{diff.repo_name} (+{diff.total_additions}/-{diff.total_deletions})"
                        )
                        with TabPane(tab_label, id=f"tab-{diff.repo_id}"):
                            yield from self._render_repo_diff(diff)
            else:
                yield RichLog(id="diff-log", wrap=True, highlight=True)
            yield Rule()
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Enter approve  |  r reject  |  y copy  |  Esc close",
                    classes="modal-action-hint",
                )
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        if not self._diffs:
            log = self.query_one("#diff-log", RichLog)

            log.styles.border = ("none", "transparent")
            for line in self._diff_text.splitlines() or ["(No diff available)"]:
                log.write(line)

    def _render_repo_diff(self, diff: RepoDiff) -> ComposeResult:
        with VerticalScroll(classes="diff-scroll"):
            for file in diff.files:
                yield Label(
                    f"{file.status.upper()}: {file.path} (+{file.additions}/-{file.deletions})",
                    classes="diff-header",
                )
                yield Static(
                    colorize_diff(file.diff_content),
                    classes="diff-content",
                )

    def action_close(self) -> None:
        """Close the modal without any action."""
        self.dismiss(None)

    def action_approve(self) -> None:
        """Approve and dismiss the modal."""
        self.dismiss("approve")

    def action_reject(self) -> None:
        """Reject and dismiss the modal."""
        self.dismiss("reject")

    def action_copy(self) -> None:
        """Copy diff content to clipboard."""
        content = self._diff_text or self._build_unified_diff()
        copy_with_notification(self.app, content, "Diff")

    def _build_unified_diff(self) -> str:
        if not self._diffs:
            return self._diff_text

        lines: list[str] = []
        for diff in self._diffs:
            lines.append(f"# === {diff.repo_name} ({diff.target_branch}) ===")
            lines.append(f"# +{diff.total_additions} -{diff.total_deletions}")
            lines.append("")
            for file in diff.files:
                lines.append(file.diff_content)
                lines.append("")
        return "\n".join(lines)
