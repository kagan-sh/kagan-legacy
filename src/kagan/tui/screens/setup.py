import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Footer, Input, Label, Select, Static

from kagan.tui.keybindings import SETUP_FLOW_BINDINGS

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp

_ONBOARDING_LOGO = """\
█▄▀  ▄▀▄  █▀▀  ▄▀▄  █▄  █
█▀▄  █▀█  █▄█  █▀█  █ ▀▄█"""

_AGENT_OPTIONS = [
    ("Claude Code  —  Agentic AI for coding tasks", "claude-code"),
    ("OpenCode  —  Open-source coding assistant", "opencode"),
    ("Codex  —  Fast code generation", "codex"),
    ("Gemini  —  Google coding model", "gemini"),
    ("Aider  —  Terminal pair coding assistant", "aider"),
]

_LAUNCHER_OPTIONS = [
    ("tmux", "tmux"),
    ("Neovim", "nvim"),
    ("VS Code", "vscode"),
    ("Cursor", "cursor"),
    ("Windsurf", "windsurf"),
    ("Kiro", "kiro"),
    ("Antigravity", "antigravity"),
]

SetupMode = Literal["onboarding", "new-project", "open-folder"]

_MODE_COPY: dict[SetupMode, dict[str, str]] = {
    "onboarding": {
        "title": "First-Time Setup",
        "subtitle": (
            "Choose your defaults and create the first project. The default path is "
            "Create -> Start -> Review -> Merge; attach stays available when you need it."
        ),
        "project_hint": "Pick the name shown on Welcome and the Board.",
        "repo_hint": (
            "Optional. Link a repository now or add one later; Kagan uses it for "
            "worktrees and reviews."
        ),
        "action": "Continue to Kagan",
    },
    "new-project": {
        "title": "New Project",
        "subtitle": "Create a new project and optionally attach a repository.",
        "project_hint": "Required. This is the name used across the TUI.",
        "repo_hint": (
            "Optional. Leave empty to create the project first and add repositories later."
        ),
        "action": "Create Project",
    },
    "open-folder": {
        "title": "Open Folder",
        "subtitle": "Open an existing project by repo path or create a project around it.",
        "project_hint": "Optional. If left empty, Kagan infers a project name from the folder.",
        "repo_hint": "Required. Existing projects linked to this path open directly.",
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
    ) -> None:
        super().__init__(id="setup-flow")
        self._is_creating = False
        self._mode: SetupMode = mode
        self._initial_repo_path = initial_repo_path
        self._last_inferred_name: str | None = None
        self._debounce_timer: asyncio.TimerHandle | None = None

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
                    with Vertical(id="setup-section-project", classes="setup-section"):
                        yield Label("Project", classes="setup-section-title")
                        yield Label("Project Name", classes="form-label")
                        yield Label(self._copy["project_hint"], classes="form-hint")
                        yield Input(
                            placeholder="My project",
                            id="new-project-name",
                        )

                        yield Label("Repository Path", classes="form-label")
                        yield Label(self._copy["repo_hint"], classes="form-hint")
                        yield Input(
                            placeholder="/path/to/repo",
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
                                    options=_AGENT_OPTIONS,
                                    value="claude-code",
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
                    yield Static(
                        "[bold]Enter[/] continue  [bold]Tab[/] next field  [bold]Esc[/] close",
                        classes="modal-action-hint",
                    )
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        settings = await self.kagan_app.core.settings.get()
        default_agent = settings.get("default_agent_backend")
        agent_select = self.query_one("#setup-default-agent", Select)
        allowed_agents = {value for _, value in _AGENT_OPTIONS}
        if isinstance(default_agent, str) and default_agent in allowed_agents:
            agent_select.value = default_agent
        else:
            agent_select.value = "claude-code"

        attached_launcher = settings.get("attached_launcher", "tmux")
        launcher_select = self.query_one("#setup-attached-launcher", Select)
        allowed_launchers = {value for _, value in _LAUNCHER_OPTIONS}
        launcher_select.value = (
            attached_launcher if attached_launcher in allowed_launchers else "tmux"
        )

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
        if self._mode == "open-folder":
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

        selected_agent = self.query_one("#setup-default-agent", Select).value
        default_agent = selected_agent if isinstance(selected_agent, str) else "claude-code"
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
            self.app.notify("Folder path is required to open a repository.", severity="error")
            return

        if not name and candidate_path is not None:
            name = candidate_path.resolve().name
        if not name:
            self.app.notify("Project name is required.", severity="error")
            return

        self._is_creating = True
        try:
            await self._persist_settings(default_agent, attached_launcher, auto_review)

            if self._mode == "open-folder" and candidate_path is not None:
                existing_project = await self.kagan_app.core.projects.find_by_repo(
                    str(candidate_path.resolve())
                )
                if existing_project is not None:
                    await self.kagan_app.activate_project(existing_project)
                    repo_id = await self._repo_id_for_path(
                        existing_project.id, candidate_path.resolve()
                    )
                    if repo_id is not None:
                        await self.kagan_app.remember_selected_repo(repo_id)
                    self.dismiss(None)
                    self.app.switch_screen("kanban-screen")
                    return

            repo_paths = [str(candidate_path)] if candidate_path is not None else None
            project = await self.kagan_app.core.projects.create(name, repo_paths=repo_paths)
            repo = None
            if candidate_path is not None:
                repo_id = await self._repo_id_for_path(project.id, candidate_path.resolve())
                if repo_id is not None:
                    repos = await self.kagan_app.core.projects.repos(project.id)
                    repo = next((item for item in repos if item.id == repo_id), None)

            await self.kagan_app.activate_project(project)
            if repo is not None:
                await self.kagan_app.remember_selected_repo(repo.id)
            self.dismiss(None)
            self.app.switch_screen("kanban-screen")
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

    async def action_dismiss(self, result: None = None) -> None:
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
