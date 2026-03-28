from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Static

HEADER_SEPARATOR = "│"
LOGO_SMALL = "ᘚᘛ"


class KaganHeader(Horizontal):
    DEFAULT_CSS = """
    KaganHeader {
        layout: horizontal;
    }

    KaganHeader .header-logo,
    KaganHeader .header-title,
    KaganHeader .header-repo,
    KaganHeader .header-github-status,
    KaganHeader .header-branch,
    KaganHeader .header-sessions,
    KaganHeader .header-agent,
    KaganHeader .header-stats,
    KaganHeader .header-separator {
        width: auto;
    }

    KaganHeader .header-spacer {
        width: 1fr;
    }
    """

    project_name: reactive[str] = reactive("No project")
    repo_name: reactive[str] = reactive("")
    backend_name: reactive[str] = reactive("-")
    connected: reactive[bool] = reactive(False)
    task_count: reactive[int] = reactive(0)
    active_count: reactive[int] = reactive(0)
    review_count: reactive[int] = reactive(0)
    done_count: reactive[int] = reactive(0)
    active_sessions: reactive[int] = reactive(0)
    git_branch: reactive[str] = reactive("")
    plugin_badges_text: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        logo = Static(LOGO_SMALL, id="header-logo", classes="header-logo")
        logo.tooltip = "Kagan - AI-powered Kanban TUI"
        yield logo
        project = Static("", id="header-project", classes="header-title")
        project.tooltip = "Current project"
        yield project
        repo = Static("", id="header-repo", classes="header-repo")
        repo.tooltip = "Repository name"
        yield repo
        yield Static("", classes="header-spacer")

        gh_status = Static("", id="header-github-status", classes="header-github-status")
        gh_status.tooltip = "GitHub connection status"
        yield gh_status
        yield Static(HEADER_SEPARATOR, id="sep-github", classes="header-separator")
        branch = Static("", id="header-branch", classes="header-branch")
        branch.tooltip = "Current Git branch"
        yield branch
        yield Static(HEADER_SEPARATOR, id="sep-branch", classes="header-separator")
        sessions = Static("", id="header-sessions", classes="header-sessions")
        sessions.tooltip = "Active agent sessions"
        yield sessions
        yield Static(HEADER_SEPARATOR, id="sep-sessions", classes="header-separator")
        agent = Static("", id="header-agent", classes="header-agent")
        agent.tooltip = "Current AI agent backend"
        yield agent
        yield Static(HEADER_SEPARATOR, id="sep-agent", classes="header-separator")
        stats = Static("", id="header-stats", classes="header-stats")
        stats.tooltip = "Task statistics (active, in review, completed)"
        yield stats
        yield Static(HEADER_SEPARATOR, id="sep-stats", classes="header-separator")
        help_widget = Static("? help", id="header-help", classes="header-branch")
        help_widget.tooltip = "Press ? to open help (keyboard shortcuts)"
        yield help_widget

    def on_mount(self) -> None:
        self._render_project()
        self._render_repo()
        self._render_github_status()
        self._render_branch()
        self._render_sessions()
        self._render_backend()
        self._render_status()
        self._render_count()

    def set_project_name(self, value: str) -> None:
        self.project_name = value

    def set_backend_name(self, value: str) -> None:
        self.backend_name = value

    def set_connected(self, value: bool) -> None:
        self.connected = value

    def update_project(self, value: str) -> None:
        self.set_project_name(value)

    def update_backend(self, value: str) -> None:
        self.set_backend_name(value)

    def update_count(self, count: int) -> None:
        self.task_count = max(0, count)

    def update_health_strip(self, *, active: int, review: int, done: int) -> None:
        self.active_count = max(0, active)
        self.review_count = max(0, review)
        self.done_count = max(0, done)

    def update_sessions(self, active: int) -> None:
        self.active_sessions = max(0, active)

    def update_branch(self, branch: str) -> None:
        self.git_branch = branch

    def update_repo(self, repo: str) -> None:
        self.repo_name = repo

    def update_plugin_badges_text(self, text: str) -> None:
        self.plugin_badges_text = text

    def watch_project_name(self, _: str) -> None:
        self._render_project()

    def watch_repo_name(self, _: str) -> None:
        self._render_repo()

    def watch_backend_name(self, _: str) -> None:
        self._render_backend()

    def watch_connected(self, _: bool) -> None:
        self._render_status()
        self._render_github_status()

    def watch_task_count(self, _: int) -> None:
        self._render_count()

    def watch_active_count(self, _: int) -> None:
        self._render_count()

    def watch_review_count(self, _: int) -> None:
        self._render_count()

    def watch_done_count(self, _: int) -> None:
        self._render_count()

    def watch_active_sessions(self, _: int) -> None:
        self._render_sessions()

    def watch_git_branch(self, _: str) -> None:
        self._render_branch()

    def watch_plugin_badges_text(self, _: str) -> None:
        self._render_github_status()

    def _render_project(self) -> None:
        self._update_label("#header-project", self.project_name or "Kagan")

    def _render_repo(self) -> None:
        has_repo = bool(self.repo_name)
        self._update_label("#header-repo", f" / {self.repo_name}" if has_repo else "")
        self._set_visible("#header-repo", has_repo)

    def _render_backend(self) -> None:
        value = self._backend_text()
        self._update_label("#header-agent", value)
        has_value = bool(value)
        self._set_visible("#header-agent", has_value)
        self._set_visible("#sep-agent", has_value)

    def _render_status(self) -> None:
        try:
            logo = self.query_one("#header-logo", Static)
        except NoMatches:
            return
        logo.set_class(self.connected, "logo-connected")
        logo.set_class(not self.connected, "logo-disconnected")

    def _render_github_status(self) -> None:
        text = self.plugin_badges_text or ("● GH" if self.connected else "")
        self._update_label("#header-github-status", text)
        self._set_visible("#header-github-status", bool(text))
        self._set_visible("#sep-github", bool(text))

    def _render_branch(self) -> None:
        has_branch = bool(self.git_branch)
        self._update_label("#header-branch", f"⎇ {self.git_branch}" if has_branch else "")
        self._set_visible("#header-branch", has_branch)
        self._set_visible("#sep-branch", has_branch)

    def _render_sessions(self) -> None:
        has_sessions = self.active_sessions > 0
        value = f"● {self.active_sessions} active" if has_sessions else ""
        self._update_label("#header-sessions", value)
        self._set_visible("#header-sessions", has_sessions)
        self._set_visible("#sep-sessions", has_sessions)

    def _render_count(self) -> None:
        self._update_label("#header-stats", self._count_text())

    def _update_label(self, label_id: str, value: str) -> None:
        try:
            self.query_one(label_id, Static).update(value)
        except NoMatches:
            return

    def _set_visible(self, label_id: str, visible: bool) -> None:
        try:
            self.query_one(label_id, Static).display = visible
        except NoMatches:
            return

    def _backend_text(self) -> str:
        backend = self.backend_name.strip() if self.backend_name else ""
        if not backend or backend == "-":
            return ""
        return f"AI: {backend}"

    def _count_text(self) -> str:
        if self.active_count or self.review_count or self.done_count:
            return (
                f"● {self.active_count} active  ◎ {self.review_count} review"
                f"  ✓ {self.done_count} done"
            )
        return f"📋 {self.task_count} tasks"
