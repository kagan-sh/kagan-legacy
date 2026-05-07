from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, cast

from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import (
    Checkbox,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from kagan.cli.chat import resolve_default_agent_backend
from kagan.core import git
from kagan.core.enums import (
    ChatMode,
    SessionKind,
    StreamSource,
    TaskStatus,
)
from kagan.core.errors import (
    KaganError,
    NotFoundError,
)
from kagan.tui._chat_helpers import build_session_options
from kagan.tui.keybindings import TASK_SCREEN_BINDINGS
from kagan.tui.screens._task_chat import _TaskChatMixin
from kagan.tui.screens._task_review import _TaskReviewMixin
from kagan.tui.screens._task_stream import _TaskStreamMixin
from kagan.tui.screens.task_commands import TaskScreenCommandProvider
from kagan.tui.widgets.chat import ChatPanel
from kagan.tui.widgets.diff import DiffFileTree
from kagan.tui.widgets.header import KaganHeader
from kagan.tui.widgets.task_action_bar import TaskActionBar
from kagan.tui.widgets.task_detail_pane import TaskDetailPane
from kagan.tui.widgets.task_diff_pane import TaskDiffPane
from kagan.tui.widgets.task_workspace_helpers import (
    hydrate_workspace_panels,
    merged_commit_diff_fallback,
    resolve_latest_merge_event,
)

if TYPE_CHECKING:
    from textual import events
    from textual.app import ComposeResult
    from textual.timer import Timer

    from kagan.core.models import Task
    from kagan.tui.app import KaganApp


class TaskScreen(_TaskReviewMixin, _TaskStreamMixin, _TaskChatMixin, Screen[None]):
    BINDINGS = TASK_SCREEN_BINDINGS
    COMMANDS = {TaskScreenCommandProvider}

    def __init__(self, task_id: str | None = None) -> None:
        super().__init__(id="task-screen")
        self._task_id = task_id
        self._task_model: Task | None = None
        self._review_approved: bool = False
        self._running = False
        self._status_override: str | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._runtime_poll_timer: Timer | None = None
        self._stream_refresh_timer: Timer | None = None
        self._pending_runtime_refresh = False
        self._pending_workspace_refresh = False
        self._pending_review_refresh = False
        self._simulated_session = False
        self._chat_mode = ChatMode.TASK
        self._overlay_layout_mode = "vertical"
        self._chat_orchestrator_history: list[tuple[str, str]] = []
        self._chat_session_switch_token = 0
        self._chat_message_task: asyncio.Task[None] | None = None
        self._review_criteria_signature: tuple[str, ...] | None = None
        self._review_file_entries_signature: tuple[tuple[str, int, int], ...] | None = None
        self._stream_source: str | None = None
        self._last_merge_blocker: str | None = None
        self._oldest_event_ts: str | None = None
        self._replay_count: int = 0
        self._worker_session_id: str | None = None
        self._reviewer_session_id: str | None = None
        self._pending_reviewer_session_id = False
        self._user_switched_tab = False

    @property
    def kagan_app(self) -> KaganApp:
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        yield KaganHeader()
        with Vertical(id="task-screen-root"):
            yield Label("Task", id="ts-title", classes="ts-title")
            yield Label("Branch: -", id="ts-branch", classes="ts-branch")
            yield Label("Idle", id="ts-status", classes="ts-status")

            with TabbedContent(id="ts-tabs", initial="overview"):
                with TabPane("Overview", id="overview"):
                    yield TaskDetailPane(id="ts-overview-pane")

                with TabPane("Changes", id="changes"):
                    yield TaskDiffPane(id="ts-diff-pane")

                with TabPane("Review", id="review"):
                    with VerticalScroll(id="ts-review-scroll"):
                        yield Static(
                            "",
                            id="ts-detail-stream-source",
                            classes="ts-detail-stream-source",
                        )
                        yield Static("", id="ts-detail-status", classes="ts-detail-status")
                        yield Static(
                            "",
                            id="ts-detail-changes-summary",
                            classes="ts-detail-changes-summary",
                        )
                        yield Static("Merge Readiness", classes="ts-section-label")
                        yield Static("", id="ts-merge-readiness", classes="ts-detail-review")
                        yield Static("Verify Criteria", classes="ts-section-label")
                        yield Vertical(
                            id="ts-detail-criteria-list",
                            classes="ts-detail-criteria-list",
                        )
                        yield Static(
                            "",
                            id="ts-detail-criteria-status",
                            classes="ts-detail-criteria-status",
                        )

            yield Static("Press o · AI Overlay", id="ts-chat-hint", classes="ts-chat-hint")
            yield ChatPanel(id="ts-chat-overlay", classes="chat-overlay")

        yield TaskActionBar(id="ts-actions")

    async def on_mount(self) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        if self._task_id is None:
            self._refresh_header()
            self._refresh_header_labels()
            self._set_status("Idle")
            self._select_initial_tab()
            self._sync_action_bar()
            self._sync_overlay_layout_class()
            self._sync_stream_source_indicator()
            self.run_worker(
                self._refresh_header_context(),
                group="task-screen-header-context",
                exclusive=True,
                exit_on_error=False,
            )
            self.call_after_refresh(self.refresh_bindings)
            return

        with contextlib.suppress(NotFoundError):
            self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        self._refresh_header()
        self._refresh_header_labels()
        self._select_initial_tab()
        await self._hydrate_workspace_panels()
        await self._load_review_context()
        self._sync_action_bar()
        self._sync_overlay_layout_class()
        self.run_worker(
            self._refresh_header_context(),
            group="task-screen-header-context",
            exclusive=True,
            exit_on_error=False,
        )
        self.query_one("#ts-overview-scroll", VerticalScroll).focus()
        self.call_after_refresh(self.refresh_bindings)

        if self._task_model is not None and self._task_model.status is TaskStatus.IN_PROGRESS:
            self._running = True
            self.call_after_refresh(
                lambda: self.run_worker(self.action_open_task_overlay(), exit_on_error=False)
            )
        elif self._task_model is not None and self._task_model.status is TaskStatus.BACKLOG:
            from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

            self.call_after_refresh(
                lambda: self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))
            )
        self._sync_stream_source_indicator()
        self._runtime_poll_timer = self.set_interval(1.0, self._schedule_runtime_refresh)

    def on_chat_panel_ready(self, _: ChatPanel.Ready) -> None:
        self._configure_overlay_chat()
        self._ensure_stream_worker()

    async def on_unmount(self) -> None:
        if self._stream_task is not None:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_task
            self._stream_task = None
        if self._chat_message_task is not None:
            self._chat_message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._chat_message_task
            self._chat_message_task = None
        if self._runtime_poll_timer is not None:
            self._runtime_poll_timer.stop()
            self._runtime_poll_timer = None
        if self._stream_refresh_timer is not None:
            self._stream_refresh_timer.stop()
            self._stream_refresh_timer = None
        self._pending_runtime_refresh = False
        self._pending_workspace_refresh = False
        self._pending_review_refresh = False

    def on_show(self) -> None:
        self._sync_overlay_layout_class()
        self._sync_action_bar()
        self.refresh_bindings()

    def action_back(self) -> None:
        panel = self._overlay_panel()
        # If chat overlay is fullscreen, exit fullscreen first (same as split-cycle shortcut)
        if panel.has_class("visible") and panel.has_class("fullscreen"):
            panel.set_fullscreen(False)
            self._overlay_layout_mode = "vertical"
            self._sync_overlay_layout_class()
            return
        # If chat overlay is visible (not fullscreen), close it
        if panel.has_class("visible"):
            panel.set_visible(False)
            panel.set_fullscreen(False)
            self._overlay_layout_mode = "vertical"
            self._sync_overlay_layout_class()
            return
        # Otherwise, go back to kanban
        self.app.pop_screen()

    def action_tab_detail(self) -> None:
        self._switch_tab("overview")

    def action_tab_diff(self) -> None:
        self._switch_tab("changes")

    def action_tab_overview(self) -> None:
        self._switch_tab("overview")

    def action_tab_changes(self) -> None:
        self._switch_tab("changes")

    def action_tab_review(self) -> None:
        self._switch_tab("review")

    def _switch_tab(self, tab_id: str, *, user_initiated: bool = True) -> None:
        tabs = self.query_one("#ts-tabs", TabbedContent)
        self.set_focus(None)
        tabs.active = tab_id
        self.call_after_refresh(lambda: self._focus_tab_after_switch(tab_id))
        self._sync_action_bar()
        self.refresh_bindings()
        if user_initiated:
            self._user_switched_tab = True

    def action_switch_tab(self, tab_id: str) -> None:
        self._switch_tab(tab_id)

    def on_tabbed_content_tab_activated(self) -> None:
        self._sync_action_bar()
        self.refresh_bindings()
        if self._active_tab() == "changes":
            self._schedule_runtime_refresh()

    def _focus_tab_after_switch(self, tab_id: str) -> None:
        if tab_id == "changes":
            with contextlib.suppress(NoMatches):
                self.set_focus(self.query_one(DiffFileTree))
                return

        if tab_id in {"overview", "review"}:
            for node in self.query(".ts-detail-criterion"):
                if isinstance(node, Checkbox):
                    self.set_focus(node)
                    return

    async def action_primary_action(self) -> None:
        if self._overlay_panel().has_class("visible") and self._focused_widget_accepts_text():
            return

        task = self._task_model

        def _approve_or_merge() -> None:
            if task is not None and self._review_approved:
                self.action_merge()
            else:
                self.action_approve()

        active = self._active_tab()
        if active == "overview":
            if task is not None and task.status is TaskStatus.REVIEW:
                _approve_or_merge()
                return
            self._switch_tab("changes")
            if self._running:
                self._set_status("Running")
                return
            self._running = True
            self._set_stream_source(StreamSource.WORKER)
            self._set_status("Running")
            self._output_stream().append_text("[started]")
            await self._start_or_attach_session()
            return

        if active in {"changes", "review"}:
            _approve_or_merge()
            return

        if task is not None and task.status is TaskStatus.REVIEW:
            _approve_or_merge()
            return
        if self._running:
            self._set_status("Running")
            return
        self._running = True
        self._set_stream_source(StreamSource.WORKER)
        self._set_status("Running")
        self._output_stream().append_text("[started]")
        await self._start_or_attach_session()

    async def action_cancel_run(self) -> None:
        self._running = False
        self._set_status("Stopped")
        self._output_stream().append_text("[stopped]")
        if self._task_id is not None and not self._simulated_session:
            with contextlib.suppress(KaganError, OSError, RuntimeError):
                await self.kagan_app.core.tasks.cancel(self._task_id)

    def action_edit_task(self) -> None:
        self.run_worker(self._edit_task_flow(), exit_on_error=False)

    async def _edit_task_flow(self) -> None:
        if self._task_id is None:
            return
        if self._task_model is None:
            with contextlib.suppress(NotFoundError):
                self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        if self._task_model is None:
            return

        from kagan.tui.screens.task_editor_modal import TaskEditorModal

        await self.app.push_screen_wait(TaskEditorModal(task=self._task_model))
        await self._refresh_runtime_state()

    def action_delete_task(self) -> None:
        self.run_worker(self._delete_task_flow(), exit_on_error=False)

    async def _delete_task_flow(self) -> None:
        if self._task_id is None:
            return
        if self._task_model is None:
            with contextlib.suppress(NotFoundError):
                self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        task = self._task_model
        if task is None:
            return

        from kagan.tui.screens.confirm import ConfirmModal

        worktree = await self.kagan_app.core.worktrees.get(task.id)
        warning_lines = ["This removes the task from the board and its persisted state."]
        if worktree is not None:
            warning_lines.append("⚠ The git worktree and branch will be removed.")
        confirmed = await self.app.push_screen_wait(
            ConfirmModal(
                title="Delete Task",
                message=f"Delete #{task.id[:8]} · {task.title}?",
                detail="\n".join(warning_lines),
                confirm_label="Delete",
                cancel_label="Cancel",
            )
        )
        if confirmed is not True:
            return
        await self.kagan_app.core.tasks.delete(task.id)
        self.action_back()

    def action_open_repo_picker(self) -> None:
        self.run_worker(self._open_repo_picker_flow(), exit_on_error=False)

    async def action_switch_session(self) -> None:
        panel = self._overlay_panel()
        if not panel.has_class("visible"):
            await self.action_open_task_overlay()
            panel = self._overlay_panel()
        self._open_overlay_session_picker(panel)

    async def action_open_session_picker(self) -> None:
        await self.action_switch_session()

    def _open_overlay_session_picker(self, panel: ChatPanel, *, initial_query: str = "") -> None:
        modal = panel.create_session_picker_modal(initial_query=initial_query)

        def _on_select(selected_key: str | None) -> None:
            if selected_key is None:
                return
            selector = panel.query_one("#chat-overlay-session-select", Select)
            selector.value = selected_key

        self.app.push_screen(modal, callback=_on_select)

    async def _open_repo_picker_flow(self) -> None:
        await self.app.push_screen_wait("repo-picker-modal")
        await self._hydrate_workspace_panels()
        await self._load_review_context()

    async def _start_or_attach_session(self, *, backend_hint: str | None = None) -> str | None:
        if self._effective_stream_source() == "worker":
            self._worker_session_id = None
            self._pending_reviewer_session_id = False
        if self._task_id is None:
            self._simulated_session = True
            self._output_stream().post_note("No task selected; running simulated output")
            return "No task selected"

        if self._task_model is None:
            self._task_model = await self.kagan_app.core.tasks.get(self._task_id)

        backend = backend_hint or await self._resolve_backend(self._task_model)
        try:
            await self._ensure_workspace()
            await self.kagan_app.core.tasks.run(self._task_id, agent_backend=backend)
            self._simulated_session = False
            self._output_stream().post_note(f"Session started with backend: {backend}")
            self._ensure_stream_worker()
            self._sync_stream_source_indicator()
            return None
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            self._simulated_session = True
            self._output_stream().post_note(f"Session unavailable, using local simulation: {exc}")
            self._sync_stream_source_indicator()
            return str(exc)

    async def _ensure_workspace(self) -> None:
        if self._task_id is None:
            return
        workspace = await self.kagan_app.core.worktrees.get(self._task_id)
        if workspace is None:
            await self.kagan_app.core.worktrees.create(self._task_id)

    async def _resolve_backend(self, task: Task) -> str:
        if task.agent_backend:
            return task.agent_backend
        settings = await self.kagan_app.core.settings.get()
        return resolve_default_agent_backend(settings)

    async def _hydrate_workspace_panels(self) -> None:
        await hydrate_workspace_panels(
            task_id=self._task_id,
            active_tab=self._active_tab(),
            diff_pane=self.query_one(TaskDiffPane),
            get_workspace=self.kagan_app.core.worktrees.get,
            get_workspace_diff=self.kagan_app.core.worktrees.diff,
            get_workspace_stats=self.kagan_app.core.worktrees.diff_stats,
            resolve_merged_fallback=self._resolve_merged_commit_diff_fallback,
        )

    async def _resolve_merged_commit_diff_fallback(
        self,
    ) -> tuple[str, dict[str, int], str, str, str] | None:
        if self._task_id is None:
            return None
        return await merged_commit_diff_fallback(
            task_id=self._task_id,
            task=self._task_model,
            get_task=self.kagan_app.core.tasks.get,
            latest_merge_event=lambda task_id: resolve_latest_merge_event(
                self.kagan_app.core.tasks.events,
                task_id,
            ),
            resolve_repo_path=self._task_repo_path,
        )

    async def _task_repo_path(self, project_id: str) -> tuple[str | None, str]:
        from kagan.core.errors import KaganError

        try:
            repo = await self.kagan_app.core.projects.resolve_repo(
                project_id,
                selected_repo_id=self.kagan_app.selected_repo_id,
            )
        except KaganError:
            return None, "main"
        return repo.path, repo.default_branch

    def _set_status(self, value: str) -> None:
        self._status_override = value
        self.query_one("#ts-status", Static).update(value)
        with contextlib.suppress(NoMatches):
            self.query_one("#ts-detail-status", Static).update(value)
        self._sync_stream_source_indicator()

    def _set_stream_source(self, source: str | None) -> None:
        if source in {StreamSource.WORKER, StreamSource.REVIEWER}:
            self._stream_source = source
        else:
            self._stream_source = None
        self._sync_stream_source_indicator()

    def _effective_stream_source(self) -> str:
        if self._stream_source in {StreamSource.WORKER, StreamSource.REVIEWER}:
            return self._stream_source
        if self._task_model is not None and self._task_model.status is TaskStatus.REVIEW:
            return StreamSource.REVIEWER
        return StreamSource.WORKER

    def _sync_stream_source_indicator(self) -> None:
        source = self._effective_stream_source()
        source_label = "AI REVIEWER" if source == StreamSource.REVIEWER else "WORKER"
        advisory = " (Advisory)" if source == StreamSource.REVIEWER else ""
        backend = ""
        if self._task_model is not None:
            backend = getattr(self._task_model, "agent_backend", "") or ""
        backend_suffix = f" · {backend}" if backend else ""
        if self._running:
            text = f"Stream: {source_label}{advisory} · LIVE{backend_suffix}"
            stream_title = f"{source_label} STREAM · LIVE{backend_suffix}"
        else:
            text = f"Stream: {source_label} · IDLE{backend_suffix}"
            stream_title = f"{source_label} STREAM{backend_suffix}"

        with contextlib.suppress(NoMatches):
            source_widget = self.query_one("#ts-detail-stream-source", Static)
            source_widget.update(text)
            source_widget.set_class(source == StreamSource.REVIEWER, "ts-source-reviewer")
            source_widget.set_class(source == StreamSource.WORKER, "ts-source-worker")
            source_widget.set_class(self._running, "ts-source-live")

        with contextlib.suppress(NoMatches):
            stream = self._output_stream()
            stream.border_title = stream_title
            show_hint = (
                not self._running
                and source == StreamSource.WORKER
                and self._task_model is not None
                and self._task_model.status is TaskStatus.REVIEW
            )
            stream.border_subtitle = (
                "Ctrl+Shift+P quick actions: AI review (advisory)" if show_hint else ""
            )

    def _refresh_header_labels(self) -> None:
        task = self._task_model
        if task is None:
            self.query_one("#ts-title", Label).update("Task")
            self.query_one("#ts-branch", Label).update("Branch: -")
            status = self._status_override or "Idle"
            self.query_one("#ts-status", Static).update(status)
            self.query_one(TaskDetailPane).task_data = None
            self._sync_stream_source_indicator()
            return

        self.query_one("#ts-title", Label).update(f"{task.title}")
        branch = task.base_branch or "main"
        self.query_one("#ts-branch", Label).update(f"task-{task.id[:8]} \u2192 {branch}")
        status_label = task.status.value.replace("_", " ").title()
        if self._review_approved:
            status_label += " \u00b7 APPROVED"
        status = self._status_override or status_label
        self.query_one("#ts-status", Static).update(status)

        detail_pane = self.query_one(TaskDetailPane)
        detail_pane.task_data = task
        detail_pane.review_approved = self._review_approved
        self._sync_stream_source_indicator()

    def _refresh_header(self) -> None:
        header = self.query_one(KaganHeader)
        project = self.kagan_app.project
        header.update_project(project.name if project is not None else "No project")
        header.update_repo(self.kagan_app.selected_repo_name or "")
        header.update_count(0 if self._task_model is None else 1)
        header.update_sessions(1 if self._running else 0)

    async def _refresh_header_context(self) -> None:
        header = self.query_one(KaganHeader)
        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
            tasks = await self.kagan_app.core.tasks.list()
            active = sum(1 for task in tasks if task.status is TaskStatus.IN_PROGRESS)
            review = sum(1 for task in tasks if task.status is TaskStatus.REVIEW)
            done = sum(1 for task in tasks if task.status is TaskStatus.DONE)
            header.update_health_strip(active=active, review=review, done=done)

        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
            repo_id = self.kagan_app.selected_repo_id
            project = self.kagan_app.project
            if repo_id and project is not None:
                repos = await self.kagan_app.core.projects.repos(project.id)
                repo = next((item for item in repos if item.id == repo_id), None)
                if repo is not None:
                    branch = await git.current_branch(repo.path)
                    if branch:
                        header.update_branch(branch)

    def on_diff_file_tree_file_selected(self, message: DiffFileTree.FileSelected) -> None:
        if message.entry is None:
            return
        with contextlib.suppress(NoMatches):
            current = self.query_one("#ts-workspace-bar", Static).content
            first_line = str(current).splitlines()[0] if str(current).strip() else "Workspace"
            self.query_one("#ts-workspace-bar", Static).update(
                f"{first_line}\nCurrent: {message.entry.path}"
            )

    async def on_key(self, event: events.Key) -> None:
        panel = self._overlay_panel()
        active = self._active_tab()

        if event.key == "ctrl+k":
            event.prevent_default()
            event.stop()
            await self.action_open_session_picker()
            return

        if event.key == "ctrl+f" and panel.has_class("visible"):
            event.prevent_default()
            event.stop()
            await self.action_expand_chat_overlay()
            return

        if event.key == "q":
            if panel.has_class("visible") or self._focused_widget_accepts_text():
                return
            event.prevent_default()
            event.stop()
            self.action_back()
            return

        if event.key == "escape":
            if panel.has_class("visible"):
                event.prevent_default()
                event.stop()
                panel.set_visible(False)
                panel.set_fullscreen(False)
                self._overlay_layout_mode = "vertical"
                self._sync_overlay_layout_class()
                return
            event.prevent_default()
            event.stop()
            self.action_back()
            return

        if self._focused_widget_accepts_text():
            if event.key == "enter" and panel.has_class("visible"):
                event.prevent_default()
                event.stop()
                panel.call_later(panel.action_send_message)
                return
            return

        if panel.has_class("visible"):
            return

        if active != "changes":
            return

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        del parameters
        if action in {"primary_action", "cancel_run"}:
            with contextlib.suppress(NoMatches):
                if (
                    self._overlay_panel().has_class("visible")
                    and self._focused_widget_accepts_text()
                ):
                    return False
        return True

    def _focused_widget_accepts_text(self) -> bool:
        focused = self.focused
        return isinstance(focused, Input | TextArea)

    def _sync_action_bar(self) -> None:
        action_bar = self.query_one(TaskActionBar)
        task = self._task_model
        panel = self._overlay_panel()
        action_bar.active_tab = self._active_tab()
        action_bar.task_data = task
        action_bar.task_running = self._running
        action_bar.review_approved = self._review_approved
        action_bar.chat_visible = panel.has_class("visible")
        action_bar.chat_fullscreen = panel.has_class("visible") and panel.has_class("fullscreen")
        criteria = (
            [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
            if task is not None
            else []
        )
        action_bar.has_criteria = bool(criteria)

    def _sync_overlay_layout_class(self) -> None:
        panel = self._overlay_panel()
        visible = panel.has_class("visible")
        fullscreen = visible and panel.has_class("fullscreen")
        self.set_class(visible, "ts-chat-visible")
        self.set_class(fullscreen, "ts-chat-fullscreen")
        self.set_class(
            visible and not fullscreen and self._overlay_layout_mode == "vertical",
            "ts-chat-vertical",
        )
        self.set_class(
            visible and not fullscreen and self._overlay_layout_mode == "horizontal",
            "ts-chat-horizontal",
        )
        self._sync_action_bar()

    def _active_tab(self) -> str:
        with contextlib.suppress(NoMatches, AttributeError):
            tabs = self.query_one("#ts-tabs", TabbedContent)
            active = getattr(tabs, "active", "")
            if isinstance(active, str) and active:
                return active
        return "overview"

    def _select_initial_tab(self) -> None:
        if self._task_model is not None and self._task_model.status is TaskStatus.REVIEW:
            self.query_one("#ts-tabs", TabbedContent).active = "review"
        else:
            self.query_one("#ts-tabs", TabbedContent).active = "overview"

    def _configure_overlay_chat(
        self,
        *,
        visible: bool = False,
        fullscreen: bool = False,
        mode: str = ChatMode.TASK,
        layout_mode: str | None = None,
        focus: bool = False,
    ) -> None:
        panel = self._overlay_panel()
        panel.set_visible(visible)
        panel.set_fullscreen(fullscreen)
        panel.set_overlay_shortcuts(split="Space", fullscreen="Ctrl+F")

        if layout_mode is not None:
            self._overlay_layout_mode = layout_mode

        if mode == ChatMode.ORCHESTRATOR:
            panel.set_mode_title("Orchestrator")
            panel.set_session_kind(SessionKind.ORCHESTRATOR)
        else:
            panel.set_mode_title("Task Chat")
            panel.set_session_kind(SessionKind.DETACHED)
            panel.set_sessions(
                build_session_options(self.kagan_app, self._task_session_options()),
                self._active_task_session_key(),
            )
            if self._task_id is not None:
                panel.set_mode_title(f"Task #{self._task_id[:8]}")

        if focus:
            panel.query_one("#chat-overlay-input", Input).focus()

        self._chat_mode = mode

    def _overlay_panel(self) -> ChatPanel:
        return self.query_one("#ts-chat-overlay", ChatPanel)
