from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Select, SelectionList, Static
from textual.widgets.selection_list import Selection

from kagan.core.errors import KaganError
from kagan.core.integrations.github import (
    canonical_repo_slug,
    detect_github_repo_slug_from_origin,
    format_github_setup_message,
    github_blocking_checks,
    github_preflight_checks,
    normalize_github_state,
    preview_github_issues,
    sync_github_issues,
)

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp
from kagan.tui.keybindings import GITHUB_IMPORT_BINDINGS, get_key_for_action
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
    BINDINGS = GITHUB_IMPORT_BINDINGS

    def __init__(self) -> None:
        super().__init__()
        self._is_importing = False
        self._phase: str = "filter"
        self._previewed_issues: list = []
        self._selection_list: SelectionList | None = None
        # Parsed form values cached after preview
        self._parsed_repo: str = ""
        self._parsed_state: str = "open"
        self._parsed_labels: list[str] = []
        self._parsed_limit: int = 100

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
                    "Filter by labels (comma-separated, optional)",
                    classes="github-import-label",
                )
                yield Input(
                    placeholder="bug, feature",
                    id="github-import-label",
                )

                yield Static("Limit", classes="github-import-label")
                yield Input(
                    placeholder="100",
                    id="github-import-limit",
                )

            yield SelectionList(id="github-import-selection")

            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    self._action_hint_text(),
                    classes="modal-action-hint",
                    id="github-import-action-hint",
                )

        yield KeybindingHint(id="github-import-hint", classes="keybinding-hint")
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        state_select = self.query_one("#github-import-state", Select)
        state_select.value = "open"
        self.query_one("#github-import-selection", SelectionList).display = False
        await self._prefill_repo_from_selected_origin()
        await self.action_check_readiness()
        self.query_one("#github-import-repo", Input).focus()
        self.query_one("#github-import-hint", KeybindingHint).show_hints(
            [
                ("Enter", "preview"),
                ("Esc", "close"),
            ]
        )
        self.query_one("#github-import-action-hint", Static).update(self._action_hint_text())

    def _action_hint_text(self) -> str:
        import_key = get_key_for_action(GITHUB_IMPORT_BINDINGS, "run_import", default="Enter")
        close_key = get_key_for_action(GITHUB_IMPORT_BINDINGS, "dismiss", default="Esc")
        if self._phase == "filter":
            return f"{import_key} preview  {close_key} close"
        return f"{import_key} import  {close_key} back"

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
        if self._phase == "filter":
            await self._do_preview()
        else:
            await self._do_import()

    async def _do_preview(self) -> None:
        project = self.kagan_app.project
        if project is None:
            self.app.notify("Open a project before importing from GitHub.", severity="warning")
            return

        repo_input = self.query_one("#github-import-repo", Input).value
        state_value = self.query_one("#github-import-state", Select).value
        state_input = state_value if isinstance(state_value, str) else "open"
        labels_raw = self.query_one("#github-import-label", Input).value.strip()
        labels = [lbl.strip() for lbl in labels_raw.split(",") if lbl.strip()] if labels_raw else []
        limit_raw = self.query_one("#github-import-limit", Input).value.strip()
        try:
            limit = int(limit_raw) if limit_raw else 100
        except ValueError:
            self.app.notify("Limit must be a number.", severity="warning")
            return

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

        self._parsed_repo = repo
        self._parsed_state = state
        self._parsed_labels = labels
        self._parsed_limit = limit

        self.app.notify("Fetching issues…", severity="information")
        try:
            issues = await preview_github_issues(
                self.kagan_app.core,
                project_id=project.id,
                repo_slug=repo,
                state=state,
                labels=labels,
                limit=limit,
            )
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            self.app.notify(f"Preview failed: {exc}", severity="error")
            return

        if not issues:
            self.app.notify("No issues match the filters.", severity="warning")
            return

        self._previewed_issues = issues
        self._switch_to_select_phase(issues)

    def _switch_to_select_phase(self, issues: list) -> None:
        self._phase = "select"

        selections = [
            Selection(
                f"#{issue['number']}  {issue['title']}"
                + (" (synced)" if issue["already_synced"] else ""),
                issue["number"],
                initial_state=not issue["already_synced"],
            )
            for issue in issues
        ]

        fields = self.query_one("#github-import-fields", Vertical)
        fields.display = False

        selection_list = self.query_one("#github-import-selection", SelectionList)
        selection_list.clear_options()
        for sel in selections:
            selection_list.add_option(sel)
        selection_list.display = True
        self._selection_list = selection_list
        selection_list.focus()

        self.query_one("#github-import-hint", KeybindingHint).show_hints(
            [
                ("Enter", "import"),
                ("Esc", "back"),
            ]
        )
        self.query_one("#github-import-action-hint", Static).update(self._action_hint_text())

    async def _do_import(self) -> None:
        project = self.kagan_app.project
        if project is None:
            self.app.notify("Open a project before importing from GitHub.", severity="warning")
            return

        selection_list = self.query_one("#github-import-selection", SelectionList)
        selected_numbers: list[int] = list(selection_list.selected)

        if not selected_numbers:
            self.app.notify("No issues selected.", severity="warning")
            return

        try:
            result = await sync_github_issues(
                self.kagan_app.core,
                project_id=project.id,
                repo_slug=self._parsed_repo,
                state=self._parsed_state,
                labels=self._parsed_labels,
                limit=self._parsed_limit,
                issue_numbers=selected_numbers,
            )
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            self.app.notify(f"GitHub import failed: {exc}", severity="error")
            return

        summary = GitHubImportSummary(
            repo=self._parsed_repo,
            state=self._parsed_state,
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

    def action_back_to_filter(self) -> None:
        if self._phase != "select":
            return
        self._phase = "filter"
        self._previewed_issues = []
        self._selection_list = None

        selection_list = self.query_one("#github-import-selection", SelectionList)
        selection_list.display = False
        selection_list.clear_options()

        fields = self.query_one("#github-import-fields", Vertical)
        fields.display = True

        self.query_one("#github-import-hint", KeybindingHint).show_hints(
            [
                ("Enter", "preview"),
                ("Esc", "close"),
            ]
        )
        self.query_one("#github-import-action-hint", Static).update(self._action_hint_text())
        self.query_one("#github-import-repo", Input).focus()

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

    def action_select_all(self) -> None:
        if self._phase != "select" or self._selection_list is None:
            return
        self._selection_list.select_all()

    def action_select_none(self) -> None:
        if self._phase != "select" or self._selection_list is None:
            return
        self._selection_list.deselect_all()

    async def action_dismiss(self, result: GitHubImportSummary | None = None) -> None:
        if self._phase == "select":
            self.action_back_to_filter()
        else:
            self.dismiss(result)
