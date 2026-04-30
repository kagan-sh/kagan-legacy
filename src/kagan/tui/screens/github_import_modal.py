from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from loguru import logger
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


@dataclass(frozen=True)
class GitHubPreviewIssue:
    number: int
    title: str
    state: str
    labels: tuple[str, ...]
    already_synced: bool

    @property
    def selection_label(self) -> str:
        suffix: list[str] = []
        if self.labels:
            suffix.append(", ".join(self.labels[:3]))
        if self.already_synced:
            suffix.append("synced")
        metadata = f"  [{' | '.join(suffix)}]" if suffix else ""
        return f"#{self.number}  {self.title}{metadata}"


def _preview_issue_from_item(item: object) -> GitHubPreviewIssue:
    extra = getattr(item, "extra", {})
    raw_number = extra.get("number") if isinstance(extra, dict) else None
    if raw_number is None:
        raw_number = getattr(item, "id", "")

    return GitHubPreviewIssue(
        number=int(raw_number),
        title=str(getattr(item, "title", "")).strip(),
        state=str(getattr(item, "state", "open")),
        labels=tuple(str(label) for label in getattr(item, "labels", ())),
        already_synced=bool(getattr(item, "already_synced", False)),
    )


class GitHubImportModal(ModalScreen[GitHubImportSummary | None]):
    BINDINGS = GITHUB_IMPORT_BINDINGS

    def __init__(self) -> None:
        super().__init__()
        self._is_importing = False
        self._phase: str = "filter"
        self._previewed_issues: list[GitHubPreviewIssue] = []
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
        return f"{import_key} import  Space toggle  A all  N none  {close_key} back"

    async def action_check_readiness(self) -> None:
        ready, message = await self._check_github_ready()
        self._set_status(message)
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
        except Exception as exc:
            logger.opt(exception=True).warning("GitHub import modal action failed")
            self._set_status(f"GitHub import stopped: {exc}")
            self.app.notify(f"GitHub import stopped: {exc}", severity="error")
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
        self._set_status(status_message)
        if not ready:
            return

        self._parsed_repo = repo
        self._parsed_state = state
        self._parsed_labels = labels
        self._parsed_limit = limit

        self._set_status(f"Fetching issues from {repo}...")
        try:
            items = await preview_github_issues(
                self.kagan_app.core,
                project_id=project.id,
                repo_slug=repo,
                state=state,
                labels=labels,
                limit=limit,
            )
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            self._set_status(f"Preview failed: {exc}")
            self.app.notify(f"Preview failed: {exc}", severity="error")
            return

        try:
            issues = [_preview_issue_from_item(item) for item in items]
        except (TypeError, ValueError) as exc:
            self._set_status(f"Preview failed: unexpected issue data from GitHub ({exc})")
            self.app.notify("Preview failed: unexpected issue data from GitHub.", severity="error")
            return
        if not issues:
            self._set_status(
                "No issues match the filters. Adjust the repository, state, or labels."
            )
            self.app.notify("No issues match the filters.", severity="warning")
            return

        self._previewed_issues = issues
        self._switch_to_select_phase(issues)

    def _switch_to_select_phase(self, issues: list[GitHubPreviewIssue]) -> None:
        self._phase = "select"

        selections = [
            Selection(
                issue.selection_label,
                issue.number,
                initial_state=not issue.already_synced,
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
                ("Space", "toggle"),
                ("A", "all"),
                ("N", "none"),
                ("Esc", "back"),
            ]
        )
        self.query_one("#github-import-action-hint", Static).update(self._action_hint_text())
        count = len(issues)
        selected_count = sum(not issue.already_synced for issue in issues)
        self._set_status(
            f"{count} issue{'s' if count != 1 else ''} found. "
            f"{selected_count} selected for import."
        )

    async def _do_import(self) -> None:
        project = self.kagan_app.project
        if project is None:
            self.app.notify("Open a project before importing from GitHub.", severity="warning")
            return

        selection_list = self.query_one("#github-import-selection", SelectionList)
        selected_numbers: list[int] = list(selection_list.selected)

        if not selected_numbers:
            self._set_status("No issues selected. Select at least one issue to import.")
            self.app.notify("No issues selected.", severity="warning")
            return

        self._set_status(
            f"Importing {len(selected_numbers)} issue"
            f"{'s' if len(selected_numbers) != 1 else ''} from {self._parsed_repo}..."
        )
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
            self._set_status(f"GitHub import failed: {exc}")
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
        self._set_status("GitHub setup looks good. Enter a repository and continue.")
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

    def _set_status(self, message: str) -> None:
        self.query_one("#github-import-status", Static).update(message)

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
