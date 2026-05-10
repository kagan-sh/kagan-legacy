from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pathspec import GitIgnoreSpec
from textual import on
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.tui.app import KaganApp


@dataclass(frozen=True, slots=True)
class FilePickerEntry:
    repo_name: str
    repo_root: Path
    path: Path
    relative_path: str
    label: str
    search_text: str


def _load_gitignore_spec(git_ignore_path: Path) -> GitIgnoreSpec | None:
    if not git_ignore_path.is_file():
        return None
    try:
        text = git_ignore_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return GitIgnoreSpec.from_lines(text.splitlines())
    except Exception:
        return None


def _is_ignored(path: Path, *, root: Path, specs: tuple[GitIgnoreSpec, ...]) -> bool:
    if path.name == ".git":
        return True
    relative = path.relative_to(root).as_posix()
    return any(spec.match_file(relative) for spec in specs)


def _walk_repo_files(
    root: Path,
    directory: Path,
    inherited_specs: tuple[GitIgnoreSpec, ...] = (),
) -> list[Path]:
    current_specs = inherited_specs
    if spec := _load_gitignore_spec(directory / ".gitignore"):
        current_specs = (*current_specs, spec)

    files: list[Path] = []
    try:
        children = sorted(
            directory.iterdir(),
            key=lambda path: (not path.is_dir(), path.name.casefold()),
        )
    except OSError:
        return files

    for child in children:
        if _is_ignored(child, root=root, specs=current_specs):
            continue
        if child.is_dir():
            files.extend(_walk_repo_files(root, child, current_specs))
            continue
        if child.is_file():
            files.append(child)
    return files


class FilePickerModal(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss", "Dismiss")]

    def __init__(self, *, initial_query: str = "") -> None:
        super().__init__(id="file-picker-modal")
        self._initial_query = initial_query
        self._entries: list[FilePickerEntry] = []
        self._filtered_entries: list[FilePickerEntry] = []
        self._loading = True

    @property
    def kagan_app(self) -> KaganApp:
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="file-picker-container"):
            yield Static("Insert file", classes="modal-title")
            yield Static(
                "Choose a file from the active project repositories.",
                id="file-picker-description",
            )
            yield Input(
                placeholder="Filter files...",
                id="file-picker-filter",
            )
            yield Static("Loading files…", id="file-picker-match-count")
            yield OptionList(id="file-picker-options")
            yield Static("No project files available.", id="file-picker-empty")
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        filter_input = self.query_one("#file-picker-filter", Input)
        if self._initial_query:
            filter_input.value = self._initial_query
        await self._reload_entries()
        filter_input.focus()

    async def _reload_entries(self) -> None:
        empty_state = self.query_one("#file-picker-empty", Static)
        option_list = self.query_one("#file-picker-options", OptionList)
        count = self.query_one("#file-picker-match-count", Static)
        empty_state.display = False

        project = self.kagan_app.project
        if project is None:
            self._entries = []
            self._filtered_entries = []
            option_list.clear_options()
            option_list.display = False
            count.update("Open a project to pick files.")
            empty_state.update("Open a project to browse repository files.")
            empty_state.display = True
            return

        repos = await self.kagan_app.core.projects.repos(project.id)
        if not repos:
            self._entries = []
            self._filtered_entries = []
            option_list.clear_options()
            option_list.display = False
            count.update("No repositories linked to this project.")
            empty_state.update("Link a repository to browse files.")
            empty_state.display = True
            return

        selected_repo_id = self.kagan_app.selected_repo_id
        ordered_repos = sorted(
            repos,
            key=lambda repo: (repo.id != selected_repo_id, repo.name.casefold(), repo.path),
        )
        entries: list[FilePickerEntry] = []
        for repo in ordered_repos:
            root = Path(repo.path).expanduser().resolve()
            if not root.is_dir():
                continue
            files = await asyncio.to_thread(_walk_repo_files, root, root)
            for file_path in files:
                relative_path = file_path.relative_to(root).as_posix()
                label = relative_path
                if len(ordered_repos) > 1:
                    label = f"{repo.name}: {relative_path}"
                entries.append(
                    FilePickerEntry(
                        repo_name=repo.name,
                        repo_root=root,
                        path=file_path,
                        relative_path=relative_path,
                        label=label,
                        search_text=f"{repo.name} {relative_path}",
                    )
                )

        self._entries = sorted(
            entries,
            key=lambda entry: (entry.repo_name.casefold(), entry.relative_path.casefold()),
        )
        self._apply_filter(self._initial_query)

        if not self._entries:
            option_list.clear_options()
            option_list.display = False
            count.update("No files found in the active repositories.")
            empty_state.update("No files matched in the active project repositories.")
            empty_state.display = True

    def _apply_filter(self, query: str) -> None:
        normalized = query.strip().casefold()
        if normalized:
            self._filtered_entries = [
                entry
                for entry in self._entries
                if normalized in entry.label.casefold()
                or normalized in entry.relative_path.casefold()
                or normalized in entry.search_text.casefold()
            ]
        else:
            self._filtered_entries = self._entries[:]
        self._render_options()

    def _render_options(self) -> None:
        option_list = self.query_one("#file-picker-options", OptionList)
        empty_state = self.query_one("#file-picker-empty", Static)
        count = self.query_one("#file-picker-match-count", Static)

        option_list.clear_options()
        if not self._filtered_entries:
            option_list.display = False
            count.update("No matching files.")
            empty_state.update("No files match the current filter.")
            empty_state.display = True
            return

        option_list.display = True
        empty_state.display = False
        file_count = len(self._filtered_entries)
        count.update(f"{file_count} file" + ("s" if file_count != 1 else ""))
        option_list.add_options(
            [
                Option(entry.label, id=str(index))
                for index, entry in enumerate(self._filtered_entries)
            ]
        )
        option_list.highlighted = 0

    @on(Input.Changed, "#file-picker-filter")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    @on(Input.Submitted, "#file-picker-filter")
    def _on_filter_submitted(self) -> None:
        self.action_select_file()

    @on(OptionList.OptionSelected, "#file-picker-options")
    def _on_option_selected(self, _: OptionList.OptionSelected) -> None:
        self.action_select_file()

    def action_cursor_up(self) -> None:
        self.query_one("#file-picker-options", OptionList).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#file-picker-options", OptionList).action_cursor_down()

    def action_select_file(self) -> None:
        option_list = self.query_one("#file-picker-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or highlighted < 0 or highlighted >= len(self._filtered_entries):
            self.dismiss(None)
            return
        self.dismiss(self._filtered_entries[highlighted].relative_path)

    def action_dismiss(self, result: str | None = None) -> None:
        self.dismiss(result)
