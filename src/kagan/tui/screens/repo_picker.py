from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, OptionList, Static

from kagan.core.models import Repository
from kagan.tui.keybindings import REPO_PICKER_BINDINGS, get_key_for_action

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp
from kagan.tui.widgets.hint_bar import KeybindingHint


class RepoPickerModal(ModalScreen[str | None]):
    BINDINGS = REPO_PICKER_BINDINGS

    def __init__(self) -> None:
        super().__init__(id="repo-picker-modal")
        self._repos: list[Repository] = []
        self._current_repo_id: str | None = None

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="repo-picker-container"):
            yield Static("KAGAN", id="repo-picker-logo")
            yield Label("Select Repository", id="repo-picker-subtitle")
            yield Label("PROJECT", id="repo-picker-project-name")
            yield Static("", id="repo-picker-detail")
            yield Label(
                "No repositories yet. Add one to continue.",
                id="repo-picker-empty",
            )
            yield OptionList(id="repo-picker-list")
            with Vertical(id="repo-picker-add"):
                yield Label("Add repository path", id="repo-picker-add-label")
                with Horizontal(id="repo-picker-add-row"):
                    yield Input(
                        placeholder="/path/to/repository",
                        id="repo-picker-path",
                    )
        yield KeybindingHint(id="repo-picker-hint", classes="keybinding-hint")
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        await self._reload_repos()
        self._update_keybinding_hints()

    def _update_keybinding_hints(self) -> None:
        self.query_one("#repo-picker-hint", KeybindingHint).show_hints(
            [
                ("↑/↓", "navigate"),
                (
                    get_key_for_action(REPO_PICKER_BINDINGS, "select_repo", default="Enter"),
                    "select",
                ),
                (get_key_for_action(REPO_PICKER_BINDINGS, "dismiss", default="Esc"), "close"),
            ]
        )

    async def action_reload(self) -> None:
        await self._reload_repos()

    async def _reload_repos(self) -> None:
        option_list = self.query_one("#repo-picker-list", OptionList)
        empty_state = self.query_one("#repo-picker-empty", Label)
        project_name = self.query_one("#repo-picker-project-name", Label)
        detail = self.query_one("#repo-picker-detail", Static)

        project = self.kagan_app.project
        if project is None:
            project_name.update("No active project")
            detail.update("Open a project before choosing a repository.")
            option_list.clear_options()
            self._repos = []
            empty_state.display = True
            return

        self._current_repo_id = self.kagan_app.selected_repo_id
        project_name.update(f"PROJECT: {project.name}")
        self._repos = await self.kagan_app.core.projects.repos(project.id)

        option_list.clear_options()
        if not self._repos:
            empty_state.display = True
            option_list.display = False
            detail.update("No repositories are linked yet. Add one below to get started.")
            return

        empty_state.display = False
        option_list.display = True
        option_list.add_options([self._repo_label(repo) for repo in self._repos])
        highlight_index = self._highlight_index()
        option_list.highlighted = highlight_index
        self._update_detail(highlight_index)

    def _repo_label(self, repo: Repository) -> str:
        path_name = Path(repo.path).name or repo.path
        indicator = "●" if repo.id == self._current_repo_id else "○"
        return f"{indicator} {repo.name}  [{repo.default_branch}]  {path_name}"

    async def action_select_repo(self) -> None:
        option_list = self.query_one("#repo-picker-list", OptionList)
        index = option_list.highlighted
        if index is not None and 0 <= index < len(self._repos):
            repo = self._repos[index]
            await self.kagan_app.remember_selected_repo(repo.id)
            self.app.notify(f"Selected repo: {repo.name}", severity="information")
            self.dismiss(repo.id)
            return
        self.dismiss(None)

    async def action_add_repo(self) -> None:
        project = self.kagan_app.project
        if project is None:
            self.app.notify("Open a project before adding a repository.", severity="warning")
            return

        repo_path = self.query_one("#repo-picker-path", Input).value.strip()
        if not repo_path:
            self.app.notify("Repository path is required.", severity="warning")
            return

        existing = {Path(repo.path).resolve() for repo in self._repos}
        candidate = Path(repo_path).expanduser().resolve()
        if candidate in existing:
            self.app.notify("Repository already linked to this project.", severity="warning")
            return

        try:
            repo = await self.kagan_app.core.projects.add_repo(project.id, repo_path)
        except Exception as exc:  # quality-allow-broad-except
            self.app.notify(f"Unable to add repository: {exc}", severity="error")
            return

        self.query_one("#repo-picker-path", Input).value = ""
        self._current_repo_id = repo.id
        await self.kagan_app.remember_selected_repo(repo.id)
        await self._reload_repos()
        self.app.notify(f"Added repo: {repo.name}", severity="information")

    @on(OptionList.OptionSelected, "#repo-picker-list")
    async def _on_repo_selected(self, _: OptionList.OptionSelected) -> None:
        await self.action_select_repo()

    @on(OptionList.OptionHighlighted, "#repo-picker-list")
    def _on_repo_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._update_detail(event.option_index)

    @on(Input.Submitted, "#repo-picker-path")
    async def _on_repo_path_submitted(self) -> None:
        await self.action_add_repo()

    async def action_dismiss(self, result: str | None = None) -> None:
        self.dismiss(result)

    def _highlight_index(self) -> int:
        if self._current_repo_id is None:
            return 0
        for index, repo in enumerate(self._repos):
            if repo.id == self._current_repo_id:
                return index
        return 0

    def _update_detail(self, index: int | None) -> None:
        detail = self.query_one("#repo-picker-detail", Static)
        if index is None or index < 0 or index >= len(self._repos):
            detail.update("Select a repository to see its branch and full path.")
            return

        repo = self._repos[index]
        status = "Current selection" if repo.id == self._current_repo_id else "Available"
        detail.update(
            "\n".join(
                [
                    f"{status} · default branch {repo.default_branch}",
                    repo.path,
                ]
            )
        )
