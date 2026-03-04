from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Select, Static

from kagan.core.errors import KaganError
from kagan.integrations.github import (
    canonical_repo_slug,
    detect_github_repo_slug_from_origin,
    format_github_setup_message,
    github_blocking_checks,
    github_preflight_checks,
    normalize_github_state,
    sync_github_issues,
)

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp
from kagan.tui.widgets.hint_bar import KeybindingHint


@dataclass(frozen=True)
class GitHubImportSummary:
    repo: str
    state: str
    created: int
    skipped: int
    errors: list[str]

    @property
    def error_count(self) -> int:
        return len(self.errors)


class GitHubImportModal(ModalScreen[GitHubImportSummary | None]):
    BINDINGS = [
        Binding("enter", "run_import", "Import", key_display="Enter"),
        Binding("ctrl+r", "check_readiness", "Check", key_display="Ctrl+R"),
        Binding("escape", "dismiss", "Close", key_display="Esc"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._is_importing = False

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="github-import-container"):
            yield Static("Import from GitHub", id="github-import-title")
            yield Static(
                "Bring GitHub issues into your board as tasks.",
                id="github-import-subtitle",
            )
            yield Static("Checking GitHub setup...", id="github-import-status")

            with Vertical(id="github-import-fields"):
                yield Static("Repository (owner/repo)", classes="github-import-label")
                yield Input(
                    placeholder="octocat/hello-world",
                    id="github-import-repo",
                )

                yield Static("Issue state", classes="github-import-label")
                yield Select(
                    options=[
                        ("Open", "open"),
                        ("Closed", "closed"),
                        ("All", "all"),
                    ],
                    id="github-import-state",
                    allow_blank=False,
                )

                yield Static(
                    "Only import issues with label (optional)",
                    classes="github-import-label",
                )
                yield Input(
                    placeholder="bug",
                    id="github-import-label",
                )

            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Enter import  Ctrl+R check setup  Esc close",
                    classes="modal-action-hint",
                )

        yield KeybindingHint(id="github-import-hint", classes="keybinding-hint")
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        state_select = self.query_one("#github-import-state", Select)
        state_select.value = "open"
        await self._prefill_repo_from_selected_origin()
        await self.action_check_readiness()
        self.query_one("#github-import-repo", Input).focus()
        self.query_one("#github-import-hint", KeybindingHint).show_hints(
            [
                ("Enter", "import"),
                ("Ctrl+R", "check"),
                ("Esc", "close"),
            ]
        )

    async def action_check_readiness(self) -> None:
        ready, message = await self._check_github_ready()
        self.query_one("#github-import-status", Static).update(message)
        if not ready:
            self.app.notify("GitHub setup is required before import.", severity="warning")

    def action_run_import(self) -> None:
        self.run_worker(
            self._run_import_flow(),
            group="github-import-run",
            exclusive=True,
            exit_on_error=False,
        )

    async def _run_import_flow(self) -> None:
        if self._is_importing:
            return
        self._is_importing = True
        try:
            await self._run_import_once()
        finally:
            self._is_importing = False

    async def _run_import_once(self) -> None:
        project = self.kagan_app.project
        if project is None:
            self.app.notify("Open a project before importing from GitHub.", severity="warning")
            return

        repo_input = self.query_one("#github-import-repo", Input).value
        state_value = self.query_one("#github-import-state", Select).value
        state_input = state_value if isinstance(state_value, str) else "open"
        import_label = self.query_one("#github-import-label", Input).value.strip() or None

        try:
            repo = canonical_repo_slug(repo_input)
            state = normalize_github_state(state_input)
        except ValueError as exc:
            self.app.notify(str(exc), severity="warning")
            return

        ready, status_message = await self._check_github_ready()
        self.query_one("#github-import-status", Static).update(status_message)
        if not ready:
            return

        from kagan.tui.screens.confirm import ConfirmModal

        confirmed = await self.app.push_screen_wait(
            ConfirmModal(
                title="Start GitHub Import",
                message=(
                    f"Repository: {repo}\n"
                    f"State: {state}\n"
                    f"Label filter: {import_label or 'none'}\n\n"
                    "Continue?"
                ),
                confirm_label="Import",
                cancel_label="Cancel",
            )
        )
        if not confirmed:
            return

        try:
            result = await sync_github_issues(
                self.kagan_app.core,
                project_id=project.id,
                repo_slug=repo,
                state=state,
                import_label=import_label,
            )
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            self.app.notify(f"GitHub import failed: {exc}", severity="error")
            return

        summary = GitHubImportSummary(
            repo=repo,
            state=state,
            created=result.created,
            skipped=result.skipped,
            errors=result.errors,
        )
        severity = "warning" if summary.error_count else "information"
        self.app.notify(
            (
                f"Imported from {summary.repo}: {summary.created} created, "
                f"{summary.skipped} skipped, {summary.error_count} errors"
            ),
            severity=severity,
        )
        self.dismiss(summary)

    @on(Input.Submitted)
    def _on_input_submitted(self) -> None:
        self.action_run_import()

    async def _prefill_repo_from_selected_origin(self) -> None:
        repo_input = self.query_one("#github-import-repo", Input)
        if repo_input.value.strip():
            return

        project = self.kagan_app.project
        selected_repo_id = self.kagan_app.selected_repo_id
        if project is None or selected_repo_id is None:
            return

        repos = await self.kagan_app.core.projects.repos(project.id)
        selected_repo = next((repo for repo in repos if repo.id == selected_repo_id), None)
        if selected_repo is None:
            return

        detected_repo = await detect_github_repo_slug_from_origin(selected_repo.path)
        if detected_repo is not None:
            repo_input.value = detected_repo

    async def _check_github_ready(self) -> tuple[bool, str]:
        try:
            checks = await github_preflight_checks(self.kagan_app.core)
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            return False, f"Unable to load GitHub integration: {exc}"

        blocked = github_blocking_checks(checks)
        if not blocked:
            return True, format_github_setup_message(checks)

        return False, format_github_setup_message(checks)

    async def action_dismiss(self, result: GitHubImportSummary | None = None) -> None:
        self.dismiss(result)
