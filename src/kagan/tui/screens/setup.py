import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Footer, Input, Label, OptionList, Select, Static

from kagan.cli.chat import resolve_default_agent_backend
from kagan.core import list_available_backends, list_backend_specs
from kagan.core.models import Project, Repository
from kagan.tui.keybindings import SETUP_FLOW_BINDINGS

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp

_ONBOARDING_LOGO = """\
█▄▀  ▄▀▄  █▀▀  ▄▀▄  █▄  █
█▀▄  █▀█  █▄█  █▀█  █ ▀▄█"""

_LAUNCHER_OPTIONS = [
    ("tmux", "tmux"),
    ("Neovim", "nvim"),
    ("VS Code", "vscode"),
    ("Cursor", "cursor"),
    ("Windsurf", "windsurf"),
    ("Kiro", "kiro"),
    ("Antigravity", "antigravity"),
]

SetupMode = Literal["onboarding", "project-picker", "new-project", "open-folder"]


def _build_agent_backend_options() -> list[tuple[str, str]]:
    availability = list_available_backends()
    specs = list_backend_specs()
    options: list[tuple[str, str]] = []
    for name, spec in specs.items():
        label = spec.label()
        suffix: list[str] = []
        if spec.reference:
            suffix.append("reference")
        if not availability.get(name, False):
            suffix.append("unavailable")
        if suffix:
            label = f"{label} ({', '.join(suffix)})"
        options.append((label, name))
    return options


_MODE_COPY: dict[SetupMode, dict[str, str]] = {
    "onboarding": {
        "title": "First-Time Setup",
        "subtitle": (
            "Choose your defaults and create the first Kagan Project. The default path is "
            "Create -> Start -> Review -> Merge; attach stays available when you need it."
        ),
        "project_hint": "Pick the Kagan Project name shown on the Board.",
        "path_label": "Repository Folder",
        "repo_hint": (
            "Optional. Link a git folder as the Repository now or add one later; "
            "Kagan uses it for worktrees and reviews."
        ),
        "action": "Continue to Kagan",
    },
    "project-picker": {
        "title": "Open Kagan Project",
        "subtitle": (
            "Pick an existing Kagan Project, open the current folder, or create a new Project."
        ),
        "project_hint": "Optional. Used when creating a new Kagan Project.",
        "path_label": "Folder Path",
        "repo_hint": (
            "Defaults to the folder where Kagan was launched. Existing Projects linked to "
            "this folder open directly."
        ),
        "action": "Open",
    },
    "new-project": {
        "title": "New Project",
        "subtitle": "Create a new Kagan Project and optionally link a Repository.",
        "project_hint": "Required. This Kagan Project name is used across the TUI.",
        "path_label": "Repository Folder",
        "repo_hint": (
            "Optional. Leave empty to create the Project first and add repositories later."
        ),
        "action": "Create Project",
    },
    "open-folder": {
        "title": "Open Folder",
        "subtitle": (
            "Open a folder. If it is already linked as a Repository, Kagan opens "
            "that Project; otherwise it creates a Project around the folder."
        ),
        "project_hint": "Optional. If left empty, Kagan infers a Project name from the folder.",
        "path_label": "Folder Path",
        "repo_hint": "Required. Existing Projects linked to this folder open directly.",
        "action": "Open Folder",
    },
}


class OnboardingFlow(ModalScreen[None]):
    BINDINGS = [*SETUP_FLOW_BINDINGS]

    def __init__(
        self,
        *,
        mode: SetupMode = "onboarding",
        initial_repo_path: str | None = None,
        dismissible: bool = True,
    ) -> None:
        super().__init__(id="setup-flow")
        self._is_creating = False
        self._mode: SetupMode = mode
        self._initial_repo_path = initial_repo_path
        self._dismissible = dismissible
        self._last_inferred_name: str | None = None
        self._debounce_timer: asyncio.TimerHandle | None = None
        self._projects: list[Project] = []
        self._repos_by_project_id: dict[str, list[Repository]] = {}
        self._resolved_repo_path: str | None = None

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    @property
    def _copy(self) -> dict[str, str]:
        return _MODE_COPY[self._mode]

    def compose(self) -> ComposeResult:
        with Container(id="setup-shell"):
            with Container(id="onboarding-container"):
                yield Static(_ONBOARDING_LOGO, id="onboarding-logo")
                yield Label(self._copy["title"], id="setup-title")
                yield Label(self._copy["subtitle"], id="setup-subtitle")

                with VerticalScroll(id="onboarding-form"):
                    with Vertical(id="setup-section-existing", classes="setup-section"):
                        yield Label("Existing Projects", classes="setup-section-title")
                        yield Label(
                            "Select a Project to open it, or use the folder fields below.",
                            classes="form-hint",
                        )
                        yield OptionList(id="setup-project-list")
                        yield Static("", id="setup-project-detail")

                    with Vertical(id="setup-section-project", classes="setup-section"):
                        yield Label("Project", classes="setup-section-title")
                        yield Label("Project Name", classes="form-label")
                        yield Label(self._copy["project_hint"], classes="form-hint")
                        yield Input(
                            placeholder="My project",
                            id="new-project-name",
                        )

                        yield Label(self._copy["path_label"], classes="form-label")
                        yield Label(self._copy["repo_hint"], classes="form-hint")
                        yield Input(
                            placeholder="/path/to/folder",
                            id="new-project-repo-path",
                        )

                    with Vertical(id="setup-section-config", classes="setup-section"):
                        yield Label("Configuration", classes="setup-section-title")

                        with Horizontal(classes="setup-field-attached"):
                            with Vertical(classes="setup-field-half"):
                                yield Label("Default agent backend", classes="form-label")
                                yield Label(
                                    "Used for new tasks on the canonical "
                                    "Create -> Start -> Review -> Merge path.",
                                    classes="form-hint",
                                )
                                yield Select[str](
                                    options=_build_agent_backend_options(),
                                    value=resolve_default_agent_backend({}),
                                    id="setup-default-agent",
                                    allow_blank=False,
                                    compact=True,
                                )
                            with Vertical(classes="setup-field-half"):
                                yield Label("Interactive attach launcher", classes="form-label")
                                yield Label(
                                    "Used only when you attach an interactive run; "
                                    "managed runs stay the default.",
                                    classes="form-hint",
                                )
                                yield Select[str](
                                    options=_LAUNCHER_OPTIONS,
                                    value="tmux",
                                    id="setup-attached-launcher",
                                    allow_blank=False,
                                    compact=True,
                                )

                        with Horizontal(id="auto-review-row"):
                            yield Checkbox(
                                "Enable auto review",
                                id="setup-auto-review",
                                value=True,
                                compact=True,
                                classes="onboarding-auto-review-checkbox",
                            )
                            yield Label(
                                "Automatically moves finished managed runs into Review.",
                                classes="form-hint auto-review-hint",
                            )

                with Horizontal(id="setup-actions"):
                    dismiss_hint = (
                        "[bold]Esc[/] close" if self._dismissible else "[bold]Ctrl+Q[/] quit"
                    )
                    yield Static(
                        f"[bold]Enter[/] continue  [bold]Tab[/] next field  {dismiss_hint}",
                        classes="modal-action-hint",
                    )
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        settings = await self.kagan_app.core.settings.get()
        agent_select = self.query_one("#setup-default-agent", Select)
        allowed_agents = {value for _, value in _build_agent_backend_options()}
        default_agent = resolve_default_agent_backend(settings)
        if default_agent not in allowed_agents:
            default_agent = resolve_default_agent_backend({})
        if agent_select.value != default_agent:
            agent_select.value = default_agent

        attached_launcher = settings.get("attached_launcher", "tmux")
        launcher_select = self.query_one("#setup-attached-launcher", Select)
        allowed_launchers = {value for _, value in _LAUNCHER_OPTIONS}
        launcher = attached_launcher if attached_launcher in allowed_launchers else "tmux"
        if launcher_select.value != launcher:
            launcher_select.value = launcher

        auto_review = settings.get("auto_review", "true").strip().lower()
        self.query_one("#setup-auto-review", Checkbox).value = auto_review not in {
            "0",
            "false",
            "off",
            "no",
        }

        name_input = self.query_one("#new-project-name", Input)
        repo_input = self.query_one("#new-project-repo-path", Input)
        if self._initial_repo_path:
            repo_input.value = self._initial_repo_path
            self._infer_project_name(self._initial_repo_path)

        if not self._initial_repo_path and self._mode in {"project-picker", "open-folder"}:
            await self._prefill_current_folder()

        await self._load_projects()

        if self._projects and self._mode in {"project-picker", "onboarding"}:
            self.query_one("#setup-project-list", OptionList).focus()
        elif self._mode == "open-folder":
            repo_input.focus()
        else:
            name_input.focus()

    async def action_submit(self) -> None:
        await self._create_project()

    @on(Input.Submitted)
    async def _on_input_submitted(self) -> None:
        await self._create_project()

    @on(Input.Changed, "#new-project-repo-path")
    def _on_repo_path_changed(self, event: Input.Changed) -> None:
        # Debounce rapid input changes to prevent performance issues
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        loop = asyncio.get_running_loop()
        self._debounce_timer = loop.call_later(0.1, self._infer_project_name, event.value)

    async def _create_project(self) -> None:
        if self._is_creating:
            return

        focused = self.app.focused
        if isinstance(focused, OptionList) and focused.id == "setup-project-list":
            opened = await self._open_highlighted_project()
            if opened:
                return

        selected_agent = self.query_one("#setup-default-agent", Select).value
        allowed_agents = {value for _, value in _build_agent_backend_options()}
        default_agent = (
            selected_agent
            if isinstance(selected_agent, str) and selected_agent in allowed_agents
            else resolve_default_agent_backend({})
        )
        selected_launcher = self.query_one("#setup-attached-launcher", Select).value
        attached_launcher = selected_launcher if isinstance(selected_launcher, str) else "tmux"
        auto_review = self.query_one("#setup-auto-review", Checkbox).value

        name = self.query_one("#new-project-name", Input).value.strip()
        repo_path = self.query_one("#new-project-repo-path", Input).value.strip()

        candidate_path: Path | None = None
        if repo_path:
            candidate_path = Path(repo_path).expanduser()
            if candidate_path.exists() and not candidate_path.is_dir():
                self.app.notify("Repository path must be a directory.", severity="error")
                return

        if self._mode == "open-folder" and not repo_path:
            self.app.notify("Folder path is required for Open Folder.", severity="error")
            return

        if not name and candidate_path is not None:
            name = candidate_path.resolve().name
        if not name:
            self.app.notify("Project name is required.", severity="error")
            return

        self._is_creating = True
        try:
            await self._persist_settings(default_agent, attached_launcher, auto_review)

            repo_path_for_create: str | None = None
            if candidate_path is not None:
                resolution = await self.kagan_app.core.projects.inspect_folder(candidate_path)
                self._resolved_repo_path = resolution.repo_path
                if resolution.existing_project_id:
                    existing_project = await self.kagan_app.core.projects.get(
                        resolution.existing_project_id
                    )
                    await self._open_project(
                        existing_project,
                        repo_id=resolution.existing_repo_id,
                    )
                    return
                repo_path_for_create = resolution.repo_path
                if not name:
                    name = resolution.suggested_project_name

            repo_paths = [repo_path_for_create] if repo_path_for_create is not None else None
            project = await self.kagan_app.core.projects.create(name, repo_paths=repo_paths)
            repo = None
            if repo_path_for_create is not None:
                repo_id = await self._repo_id_for_path(project.id, Path(repo_path_for_create))
                if repo_id is not None:
                    repos = await self.kagan_app.core.projects.repos(project.id)
                    repo = next((item for item in repos if item.id == repo_id), None)

            await self.kagan_app.activate_project(project)
            if repo is not None:
                await self.kagan_app.remember_selected_repo(repo.id)
            self.dismiss(None)
            self.app.push_screen("kanban-screen")
        except Exception as exc:  # quality-allow-broad-except
            self.app.notify(f"Unable to save setup: {exc}", severity="error")
        finally:
            self._is_creating = False

    async def _persist_settings(
        self,
        default_agent: str,
        attached_launcher: str,
        auto_review: bool,
    ) -> None:
        await self.kagan_app.core.settings.set(
            {
                "default_agent_backend": default_agent,
                "attached_launcher": attached_launcher,
                "auto_review": "true" if auto_review else "false",
            }
        )

    async def _repo_id_for_path(self, project_id: str, repo_path: Path) -> str | None:
        repos = await self.kagan_app.core.projects.repos(project_id)
        resolved = str(repo_path.resolve())
        for repo in repos:
            if repo.path == resolved:
                return repo.id
        return None

    async def _prefill_current_folder(self) -> None:
        try:
            resolution = await self.kagan_app.core.projects.inspect_folder(Path.cwd())
        except Exception:  # quality-allow-broad-except
            return
        self._resolved_repo_path = resolution.repo_path
        repo_input = self.query_one("#new-project-repo-path", Input)
        name_input = self.query_one("#new-project-name", Input)
        repo_input.value = resolution.repo_path
        if not name_input.value.strip():
            name_input.value = resolution.suggested_project_name
            self._last_inferred_name = resolution.suggested_project_name

    async def _load_projects(self) -> None:
        option_list = self.query_one("#setup-project-list", OptionList)
        section = self.query_one("#setup-section-existing", Vertical)
        option_list.clear_options()
        self._projects = await self.kagan_app.core.projects.list()
        self._repos_by_project_id = {}

        if not self._projects:
            section.display = False
            return

        section.display = True
        for project in self._projects:
            try:
                repos = await self.kagan_app.core.projects.repos(project.id)
            except Exception:  # quality-allow-broad-except
                repos = []
            self._repos_by_project_id[project.id] = repos
            option_list.add_option(self._project_label(project, repos))

        highlighted = self._project_highlight_index()
        option_list.highlighted = highlighted
        self._update_project_detail(highlighted)

    def _project_label(self, project: Project, repos: list[Repository]) -> str:
        repo_count = len(repos)
        selected = any(repo.path == self._resolved_repo_path for repo in repos)
        indicator = "●" if selected else "○"
        suffix = "repo" if repo_count == 1 else "repos"
        repo_name = repos[0].name if repo_count == 1 else f"{repo_count} {suffix}"
        return f"{indicator} {project.name}  {repo_name}"

    def _project_highlight_index(self) -> int:
        if self._resolved_repo_path is not None:
            for index, project in enumerate(self._projects):
                repos = self._repos_by_project_id.get(project.id, [])
                if any(repo.path == self._resolved_repo_path for repo in repos):
                    return index
        return 0

    def _update_project_detail(self, index: int | None) -> None:
        detail = self.query_one("#setup-project-detail", Static)
        if index is None or index < 0 or index >= len(self._projects):
            detail.update("Select a Project to see linked repositories.")
            return
        project = self._projects[index]
        repos = self._repos_by_project_id.get(project.id, [])
        if not repos:
            detail.update("No repositories linked. Opens the Project only.")
            return
        repo_lines = [f"{repo.name}: {repo.path}" for repo in repos[:3]]
        if len(repos) > 3:
            repo_lines.append(f"+ {len(repos) - 3} more")
        detail.update("\n".join(repo_lines))

    async def _open_highlighted_project(self) -> bool:
        option_list = self.query_one("#setup-project-list", OptionList)
        index = option_list.highlighted
        if index is None or index < 0 or index >= len(self._projects):
            return False
        await self._open_project(self._projects[index])
        return True

    async def _open_project(self, project: Project, *, repo_id: str | None = None) -> None:
        await self.kagan_app.activate_project(project)
        if repo_id is not None:
            await self.kagan_app.remember_selected_repo(repo_id)
        self.dismiss(None)
        self.app.push_screen("kanban-screen")

    def _infer_project_name(self, raw_path: str) -> None:
        if not raw_path.strip():
            return
        candidate = Path(raw_path).expanduser()
        inferred_name = candidate.name or candidate.resolve().name
        if not inferred_name:
            return
        name_input = self.query_one("#new-project-name", Input)
        current_name = name_input.value.strip()
        if current_name and current_name != self._last_inferred_name:
            return
        name_input.value = inferred_name
        self._last_inferred_name = inferred_name

    @on(OptionList.OptionSelected, "#setup-project-list")
    async def _on_project_selected(self, _: OptionList.OptionSelected) -> None:
        await self._open_highlighted_project()

    @on(OptionList.OptionHighlighted, "#setup-project-list")
    def _on_project_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._update_project_detail(event.option_index)

    async def action_dismiss(self, result: None = None) -> None:
        if not self._dismissible:
            self.app.notify("Open or create a Kagan Project to continue.", severity="warning")
            return
        # Clean up debounce timer to prevent callbacks after dismissal
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        self.dismiss(result)

    def on_unmount(self) -> None:
        # Ensure timer cleanup on all dismissal paths (covers success case)
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
