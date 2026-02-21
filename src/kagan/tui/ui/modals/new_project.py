"""Modal for creating a new project."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, Static

from kagan.tui.ui.modals.base import KaganModalScreen

if TYPE_CHECKING:
    from textual.app import ComposeResult

logger = logging.getLogger(__name__)


class NewProjectModal(KaganModalScreen[dict | None]):
    """Modal for creating a new project."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "submit", "Create", priority=True),
        Binding("tab", "next_field", "Next Field", priority=True),
        Binding("shift+tab", "previous_field", "Previous Field", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._is_creating = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("New Project", classes="dialog-title")
            yield Label(
                "Enter creates from any field (default). Esc cancels.",
                classes="hint",
            )

            with Vertical(classes="field"):
                yield Label("Project Name", classes="field-label")
                yield Input(placeholder="My Awesome Project", id="name-input")

            with Vertical(classes="field"):
                yield Label("Repository Path (optional)", classes="field-label")
                yield Input(placeholder="/path/to/repo", id="path-input")
                yield Label("Leave blank to add repos later", classes="hint")

            with Horizontal(id="dialog-actions", classes="modal-action-hint-row"):
                yield Static(
                    "Esc cancel  |  Enter create (default)  |  Tab/Shift+Tab move",
                    classes="modal-action-hint",
                )

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def action_cancel(self) -> None:
        if self._is_creating:
            return
        self.dismiss(None)

    def action_submit(self) -> None:
        if self._is_creating:
            return
        self._set_busy(True)
        self.run_worker(
            self._create_project(),
            group="create-project",
            exclusive=True,
            exit_on_error=False,
        )

    def action_next_field(self) -> None:
        self.focus_next(Input)

    def action_previous_field(self) -> None:
        self.focus_previous(Input)

    def _set_busy(self, is_busy: bool) -> None:
        """Disable form inputs while creating to prevent duplicate actions."""
        self._is_creating = is_busy
        for input_widget in self.query(Input):
            input_widget.disabled = is_busy

    async def on_input_submitted(self, _: Input.Submitted) -> None:
        if self._is_creating:
            return
        self.action_submit()

    async def _create_project(self) -> None:
        await asyncio.sleep(0)  # Yield so disabled inputs render before API call
        name = self.query_one("#name-input", Input).value.strip()
        path = self.query_one("#path-input", Input).value.strip()

        if not name:
            self.notify("Project name is required", severity="error")
            self._set_busy(False)
            return

        resolved_path: Path | None = None
        if path:
            resolved_path = Path(path).expanduser().resolve()
            if not resolved_path.exists():
                self.notify(f"Path does not exist: {resolved_path}", severity="error")
                self._set_busy(False)
                return

            if not (resolved_path / ".git").exists():
                try:
                    from kagan.core.git_utils import init_git_repo

                    self.notify("Initializing git repository...", severity="information")
                    result = await init_git_repo(resolved_path, base_branch="main")
                    if not result.success:
                        msg = result.error.message if result.error else "Unknown error"
                        details = result.error.details if result.error else ""
                        self.notify(
                            f"Failed to initialize git repository: {msg}\n{details}",
                            severity="error",
                        )
                        self._set_busy(False)
                        return
                    self.notify("Git repository initialized", severity="information")
                except Exception as exc:
                    logger.warning("Git init failed: %s", exc)
                    self.notify(f"Failed to initialize git: {exc}", severity="error")
                    self._set_busy(False)
                    return

        repo_paths: list[str | Path] = []
        if resolved_path is not None:
            repo_paths.append(str(resolved_path))

        try:
            project_id = await self.ctx.api.create_project(name=name, repo_paths=repo_paths)
        except Exception as exc:
            logger.warning("Project creation failed: %s", exc)
            self.notify(f"Failed to create project: {exc}", severity="error")
            self._set_busy(False)
            return

        if not project_id:
            self.notify("Project creation failed", severity="error")
            self._set_busy(False)
            return

        self.dismiss({"project_id": project_id})
