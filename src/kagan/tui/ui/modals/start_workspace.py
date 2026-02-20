"""Modal for starting a workspace with repo selection."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Checkbox, Label, Select, Static

from kagan.tui.ui.modals.base import KaganModalScreen
from kagan.tui.ui.utils.workspace_inputs import repo_details_to_workspace_inputs

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.core.services.workspaces import RepoWorkspaceInput


class RepoCheckboxItem(Static):
    """A repo item with checkbox for selection."""

    def __init__(
        self,
        repo_id: str,
        repo_name: str,
        repo_path: str,
        default_branch: str,
        is_primary: bool = False,
        preselected: bool = True,
    ) -> None:
        super().__init__()
        self.repo_id = repo_id
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.default_branch = default_branch
        self.is_primary = is_primary
        self.preselected = preselected

    def compose(self) -> ComposeResult:
        with Horizontal(classes="repo-row"):
            label = self.repo_name + (" (primary)" if self.is_primary else "")
            yield Checkbox(label, value=self.preselected, id=f"cb-{self.repo_id}")
            yield Label(self.repo_path, classes="repo-path")
            yield Label(f"→ {self.default_branch}", classes="repo-branch")


class StartWorkspaceModal(KaganModalScreen[str | None]):
    """Modal for selecting repos and starting a workspace."""

    BINDINGS = [
        Binding("enter", "start_workspace", "Start", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(
        self,
        task_id: str,
        task_title: str,
        project_id: str,
        suggested_repos: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.task_id = task_id
        self.task_title = task_title
        self.project_id = project_id
        self.suggested_repos = suggested_repos or []
        self.project_repos: list[dict] = []
        self._is_starting = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("START WORKSPACE", classes="dialog-title")
            yield Label(f"Task: {self.task_title}", classes="task-name")

            yield Label("SELECT REPOSITORIES", classes="section-header")
            yield Label(
                "Choose which repos to include in this workspace:",
                classes="section-hint",
            )

            with ScrollableContainer(id="repo-list"):
                pass

            with Vertical(id="executor-section"):
                yield Label("EXECUTOR", classes="section-header")
                yield Select(
                    [
                        ("Claude Sonnet 4 (Auto)", "auto"),
                        ("Claude Opus 4", "opus"),
                        ("Human (Pair Mode)", "human"),
                    ],
                    id="executor-select",
                    value="auto",
                )

            yield Label("", id="error-label", classes="error")

            with Horizontal(id="actions", classes="modal-action-hint-row"):
                yield Static(
                    "Press [bold]Enter[/bold] to start workspace, [bold]Esc[/bold] to cancel",
                    classes="modal-action-hint",
                )

    async def on_mount(self) -> None:
        self.run_worker(self._load_repos(), exclusive=True)
        self.query_one("#executor-select", Select).focus()

    async def _load_repos(self) -> None:
        repos = await self.ctx.api.get_project_repo_details(self.project_id)

        repo_list = self.query_one("#repo-list", ScrollableContainer)

        for repo_data in repos:
            preselected = not self.suggested_repos or repo_data["name"] in self.suggested_repos

            item = RepoCheckboxItem(
                repo_id=repo_data["id"],
                repo_name=repo_data["name"],
                repo_path=repo_data["path"],
                default_branch=repo_data["default_branch"],
                is_primary=repo_data.get("is_primary", False),
                preselected=preselected,
            )
            self.project_repos.append({**repo_data, "item": item})
            await repo_list.mount(item)

        if self.project_repos:
            first_repo = self.project_repos[0]
            item = first_repo["item"]
            checkbox = item.query_one(f"#cb-{first_repo['id']}", Checkbox)
            checkbox.focus()

    def _get_selected_repos(self) -> list[RepoWorkspaceInput]:
        selected_repo_details: list[dict[str, object]] = []
        for repo_data in self.project_repos:
            item = repo_data["item"]
            checkbox = item.query_one(f"#cb-{repo_data['id']}", Checkbox)
            if checkbox.value:
                selected_repo_details.append(repo_data)
        if not selected_repo_details:
            return []
        return repo_details_to_workspace_inputs(selected_repo_details)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        """Check action."""
        if action == "start_workspace":
            with contextlib.suppress(ValueError):
                return bool(self._get_selected_repos())
            return False
        return True

    def action_cancel(self) -> None:
        self.dismiss(None)

    async def action_start_workspace(self) -> None:
        await self._start_workspace()

    async def _start_workspace(self) -> None:
        if self._is_starting:
            return

        try:
            selected_repos = self._get_selected_repos()
        except ValueError as exc:
            error_label = self.query_one("#error-label", Label)
            error_label.update(str(exc))
            return

        if not selected_repos:
            error_label = self.query_one("#error-label", Label)
            error_label.update("Please select at least one repository")
            return

        self._is_starting = True
        error_label = self.query_one("#error-label", Label)
        error_label.update("Starting workspace...")

        try:
            workspace_id = await self.ctx.api.provision_workspace(
                task_id=self.task_id,
                repos=selected_repos,
            )
            self.dismiss(workspace_id)
        except Exception as exc:
            error_label.update(f"Error: {exc}")
            self._is_starting = False
