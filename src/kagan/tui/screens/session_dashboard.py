import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, cast

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Label, Static

from kagan.cli.chat import resolve_default_agent_backend
from kagan.core import git, resolve_spawn_command
from kagan.core.enums import SessionStatus
from kagan.core.errors import KaganError, NotFoundError, SessionError, WorktreeError
from kagan.core.models import Session
from kagan.runtime_env import build_sanitized_subprocess_environment

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp
from kagan.tui.keybindings import SESSION_DASHBOARD_BINDINGS, get_key_for_action
from kagan.tui.screens._chat_runner import (
    acp_payload,
    stream_chunk_kind,
    stream_chunk_text,
    tool_call_args,
    tool_call_id,
    tool_call_kind,
    tool_call_result,
    tool_call_status,
    tool_call_title,
)
from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
from kagan.tui.widgets.agent_status import AgentStatusPanel
from kagan.tui.widgets.commits_panel import CommitsPanel
from kagan.tui.widgets.diff import DiffView
from kagan.tui.widgets.header import KaganHeader
from kagan.tui.widgets.hint_bar import action_hints_from_bindings, format_hint
from kagan.tui.widgets.persona_pipeline import PersonaPipelineMap
from kagan.tui.widgets.streaming import StreamingOutput
from kagan.tui.widgets.worktree_panel import WorktreePanel

if TYPE_CHECKING:
    from textual.timer import Timer

    from kagan.core.models import Task


SESSION_DASHBOARD_REPLAY_EVENT_LIMIT = 400


class DashboardStatusBar(Horizontal):
    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        yield Label("Task: -", id="dashboard-task-title")
        yield Static("", classes="dashboard-status-spacer")
        yield Label("Branch: -", id="dashboard-task-branch")
        yield Label("Idle", id="dashboard-task-status", classes="dashboard-status-badge")
        yield Label("Persona: -", id="dashboard-task-persona")

    def update_title(self, title: str) -> None:
        self.query_one("#dashboard-task-title", Label).update(f"Task: {title}")

    def update_branch(self, branch: str) -> None:
        self.query_one("#dashboard-task-branch", Label).update(f"Branch: {branch}")

    def update_status(self, status: str) -> None:
        badge = self.query_one("#dashboard-task-status", Label)
        badge.update(status)
        lowered = status.strip().lower()
        badge.set_class("run" in lowered or "running" in lowered, "status-running")
        badge.set_class("complete" in lowered, "status-completed")
        badge.set_class("fail" in lowered or "error" in lowered, "status-failed")
        badge.set_class("cancel" in lowered, "status-cancelled")

    def update_persona(self, summary: str) -> None:
        self.query_one("#dashboard-task-persona", Label).update(f"Persona: {summary}")


class SessionDashboardScreen(Screen[None]):
    BINDINGS = SESSION_DASHBOARD_BINDINGS

    def __init__(self, task_id: str) -> None:
        super().__init__(id="session-dashboard-screen")
        self._task_id = task_id
        self._task_model: Task | None = None
        self._running = False
        self._stream_task: asyncio.Task[None] | None = None
        self._agent_status_timer: Timer | None = None
        self._worktree_refresh_timer: Timer | None = None
        self._refresh_timer: Timer | None = None
        self._pending_agent_status_refresh = False
        self._pending_worktree_refresh = False
        self._pending_persona_refresh = False

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        yield KaganHeader()
        yield DashboardStatusBar(id="dashboard-status-bar")
        with Horizontal(id="dashboard-body"):
            with Vertical(id="dashboard-left-col"):
                yield AgentStatusPanel(id="dashboard-agent-status")
                yield PersonaPipelineMap(id="dashboard-persona-pipeline")
                yield StreamingOutput(id="dashboard-live-output")
            with Vertical(id="dashboard-right-col"):
                yield WorktreePanel(id="dashboard-worktree")
                yield CommitsPanel(id="dashboard-commits")
                yield DiffView(id="dashboard-diff-view", default_focus="content")
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        self.query_one("#dashboard-agent-status").border_title = "Agent Status"
        self.query_one("#dashboard-persona-pipeline").border_title = "Persona Pipeline"
        self.query_one("#dashboard-live-output").border_title = "Live Output"
        self.query_one("#dashboard-worktree").border_title = "Worktree"
        self.query_one("#dashboard-commits").border_title = "Commits"
        self.query_one("#dashboard-diff-view").border_title = "Diff View"

        with contextlib.suppress(NotFoundError):
            self._task_model = await self.kagan_app.core.tasks.get(self._task_id)

        self._refresh_header()
        self._refresh_status_bar_header()
        self._sync_action_bar()
        self._ensure_stream_worker()
        self._queue_refreshes(agent_status=True, worktree=True, persona=True, delay=0.0)
        self._agent_status_timer = self.set_interval(1.0, self._schedule_agent_status_refresh)
        self._worktree_refresh_timer = self.set_interval(
            5.0, self._schedule_worktree_panels_refresh
        )

    async def on_unmount(self) -> None:
        if self._stream_task is not None:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_task
            self._stream_task = None
        if self._agent_status_timer is not None:
            self._agent_status_timer.stop()
            self._agent_status_timer = None
        if self._worktree_refresh_timer is not None:
            self._worktree_refresh_timer.stop()
            self._worktree_refresh_timer = None
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        self._pending_agent_status_refresh = False
        self._pending_worktree_refresh = False
        self._pending_persona_refresh = False

    def action_back(self) -> None:
        self.app.pop_screen()

    async def action_cancel_run(self) -> None:
        self._running = False
        self._set_compact_status("Cancelled")
        self.query_one(StreamingOutput).post_note("Run cancelled")
        with contextlib.suppress(KaganError, OSError, RuntimeError):
            await self.kagan_app.core.tasks.cancel(self._task_id)

    async def action_stop_agent(self) -> None:
        await self.action_cancel_run()
        await self._refresh_agent_status()

    async def action_restart_agent(self) -> None:
        if self._running:
            await self.action_cancel_run()
        await self._start_or_attach_session()

    async def action_primary_action(self) -> None:
        if self._running:
            self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))
            return
        await self._start_or_attach_session()

    async def action_open_orchestrator_chat(self) -> None:
        self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))

    async def action_open_task_overlay(self) -> None:
        self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))

    async def action_fullscreen_chat(self) -> None:
        self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))

    async def action_toggle_chat(self) -> None:
        self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))

    def action_cycle_session(self) -> None:
        self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))

    def action_open_repo_picker(self) -> None:
        self.run_worker(self._open_repo_picker_flow(), exit_on_error=False)

    async def _open_repo_picker_flow(self) -> None:
        await self.app.push_screen_wait("repo-picker-modal")
        self._queue_refreshes(worktree=True, delay=0.0)

    async def action_switch_session(self) -> None:
        self.app.push_screen(OrchestratorOverlay(task_id=self._task_id))

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.action_back()
            return

    def _sync_action_bar(self) -> None:
        hint = self.query_one("#dashboard-action-hint", Static)
        bindings = SESSION_DASHBOARD_BINDINGS
        specs: list[tuple[str | tuple[str, ...], str]] = []

        if self._running:
            specs.extend(
                [
                    ("primary_action", "assistant"),
                    ("stop_run", "stop"),
                    ("restart_run", "restart"),
                ]
            )
        else:
            specs.append(("primary_action", "start"))

        specs.extend(
            [
                ("switch_session", "sessions"),
                ("toggle_chat", "overlay"),
                ("fullscreen_chat", "fullscreen"),
                ("open_repo_picker", "repos"),
            ]
        )

        hints = [("Next", "")]
        hints.extend(action_hints_from_bindings(bindings, specs))
        hints.append((get_key_for_action(bindings, "back", default="Esc"), "back"))
        hint.update(format_hint(hints))

    def _ensure_stream_worker(self) -> None:
        if self._stream_task is not None and not self._stream_task.done():
            return
        self._stream_task = asyncio.create_task(self._stream_events(self._task_id))

    async def _stream_events(self, task_id: str) -> None:
        output = self.query_one(StreamingOutput)
        try:
            async for event in self.kagan_app.core.tasks.events.stream(
                task_id,
                replay_limit=SESSION_DASHBOARD_REPLAY_EVENT_LIMIT,
            ):
                payload = event.payload or {}
                match event.event_type:
                    case "output_chunk":
                        self._render_stream_chunk(output, payload)
                    case "tool_call_start":
                        output.upsert_tool_call(
                            tool_call_id(payload),
                            tool_call_title(payload),
                            status=tool_call_status(payload, default="running"),
                            args=tool_call_args(payload),
                            result=tool_call_result(payload),
                            kind=tool_call_kind(payload),
                        )
                    case "tool_call_update":
                        output.update_tool_status(
                            tool_call_id(payload),
                            tool_call_status(payload, default="updated"),
                            result=tool_call_result(payload),
                        )
                    case "agent_status":
                        output.post_note(self._payload_text(payload) or "Agent status update")
                        usage = payload.get("usage")
                        if isinstance(usage, dict):
                            try:
                                panel = self.query_one(AgentStatusPanel)
                                panel.set_usage_info(
                                    usage.get("used"),
                                    usage.get("size"),
                                    usage.get("cost"),
                                    usage.get("cost_currency"),
                                )
                            except Exception:
                                pass
                    case "agent_completed":
                        self._running = False
                        self._set_compact_status("Completed")
                        output.post_note("Agent completed")
                        self._queue_refreshes(
                            agent_status=True, worktree=True, persona=True, delay=0.0
                        )
                    case "agent_failed":
                        self._running = False
                        self._set_compact_status("Failed")
                        output.post_note(self._payload_text(payload) or "Agent failed")
                        self._queue_refreshes(
                            agent_status=True, worktree=True, persona=True, delay=0.0
                        )
                    case _:
                        continue
        except asyncio.CancelledError:
            return
        except (KaganError, NoMatches, AttributeError, OSError, RuntimeError) as exc:
            output.post_note(f"Session stream stopped: {exc}")

    async def _start_or_attach_session(self) -> None:
        if self._task_model is None:
            self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        task = self._task_model
        if task is None:
            return

        settings = await self.kagan_app.core.settings.get()
        backend = task.agent_backend or resolve_default_agent_backend(settings)

        workspace = await self.kagan_app.core.worktrees.get(self._task_id)
        if workspace is None:
            await self.kagan_app.core.worktrees.create(self._task_id)

        await self.kagan_app.core.tasks.run(self._task_id, agent_backend=backend)
        self._running = True
        self._set_compact_status("Running")
        self.query_one(StreamingOutput).post_note(f"Session started with backend: {backend}")
        self._ensure_stream_worker()
        await self._refresh_agent_status()
        await self._refresh_persona_pipeline()

    def _schedule_agent_status_refresh(self) -> None:
        if not self.is_mounted:
            return
        self._queue_refreshes(agent_status=True)

    def _schedule_worktree_panels_refresh(self) -> None:
        if not self.is_mounted:
            return
        self._queue_refreshes(worktree=True, persona=True)

    def _queue_refreshes(
        self,
        *,
        agent_status: bool = False,
        worktree: bool = False,
        persona: bool = False,
        delay: float = 0.12,
    ) -> None:
        if not self.is_mounted:
            return
        self._pending_agent_status_refresh = self._pending_agent_status_refresh or agent_status
        self._pending_worktree_refresh = self._pending_worktree_refresh or worktree
        self._pending_persona_refresh = self._pending_persona_refresh or persona
        if self._refresh_timer is not None:
            return
        self._refresh_timer = self.set_timer(delay, self._flush_refreshes)

    def _flush_refreshes(self) -> None:
        self._refresh_timer = None
        agent_status = self._pending_agent_status_refresh
        worktree = self._pending_worktree_refresh
        persona = self._pending_persona_refresh
        self._pending_agent_status_refresh = False
        self._pending_worktree_refresh = False
        self._pending_persona_refresh = False
        if not self.is_mounted:
            return
        if agent_status:
            self.run_worker(
                self._refresh_agent_status(),
                group="session-dashboard-agent",
                exclusive=True,
            )
        if worktree:
            self.run_worker(
                self._refresh_worktree_panels(),
                group="session-dashboard-worktree",
                exclusive=True,
            )
        if persona:
            self.run_worker(
                self._refresh_persona_pipeline(),
                group="session-dashboard-persona",
                exclusive=True,
            )

    async def _refresh_agent_status(self) -> None:
        latest = await self._latest_run()
        panel = self.query_one(AgentStatusPanel)
        if latest is None:
            panel.set_run_info("-", "idle", None, "-", None)
            self._running = False
            self._set_compact_status("Idle")
            return

        status_text = latest.status.value.lower()
        panel.set_run_info(
            latest.agent_backend,
            status_text,
            latest.started_at,
            latest.id,
            latest.pid,
        )
        panel.tick()
        self._running = latest.status in {SessionStatus.PENDING, SessionStatus.RUNNING}
        self._set_compact_status(latest.status.value.title())

    async def _refresh_worktree_panels(self) -> None:
        worktree_panel = self.query_one(WorktreePanel)
        commits_panel = self.query_one(CommitsPanel)
        diff_view = self.query_one(DiffView)
        worktree_panel.set_loading()
        commits_panel.set_loading()

        workspace = await self.kagan_app.core.worktrees.get(self._task_id)
        if workspace is None:
            worktree_panel.set_empty("No workspace yet")
            commits_panel.set_empty("No workspace yet")
            diff_view.set_diff("")
            return

        diff_text = ""
        with contextlib.suppress(SessionError, WorktreeError):
            diff_text = await self.kagan_app.core.worktrees.diff(self._task_id)

        stats: dict[str, int] = {"files": 0, "insertions": 0, "deletions": 0}
        with contextlib.suppress(SessionError, WorktreeError, ValueError, TypeError):
            raw_stats = await self.kagan_app.core.worktrees.diff_stats(self._task_id)
            stats = {
                "files": int(raw_stats.get("files", 0)),
                "insertions": int(raw_stats.get("insertions", 0)),
                "deletions": int(raw_stats.get("deletions", 0)),
            }

        files = git.parse_diff_file_entries(diff_text)
        if files:
            worktree_panel.set_changes(files, stats)
        else:
            worktree_panel.set_empty("No local changes")

        diff_view.set_diff(diff_text)
        if files:
            diff_view.set_selected_file(str(files[0].get("path", "")))

        base_branch = (
            self._task_model.base_branch if self._task_model is not None else None
        ) or "main"
        commits = await self._load_commits(workspace.worktree_path, base_branch)
        if commits:
            commits_panel.set_commits(commits, workspace.branch_name, base_branch)
        else:
            commits_panel.set_empty("No task-branch commits")

    async def _refresh_persona_pipeline(self) -> None:
        runs = await self._all_runs()
        panel = self.query_one(PersonaPipelineMap)
        if not runs:
            panel.set_pipeline([])
            self.query_one(DashboardStatusBar).update_persona("-")
            return

        pipeline: list[tuple[str, str]] = [
            (self._persona_name(run.persona), run.status.value.lower()) for run in runs
        ]
        panel.set_pipeline(pipeline)
        summary = " -> ".join(name for name, _status in pipeline)
        self.query_one(DashboardStatusBar).update_persona(summary)

    async def _latest_run(self) -> Session | None:
        return await self.kagan_app.core.tasks.sessions.get_latest_for_task(self._task_id)

    async def _all_runs(self) -> list[Session]:
        return await self.kagan_app.core.tasks.sessions.list_for_task(self._task_id)

    async def _load_commits(self, worktree_path: str, base_branch: str) -> list[tuple[str, str]]:
        resolved = resolve_spawn_command(
            "git", "-C", worktree_path, "log", "--pretty=format:%h%x09%s", f"{base_branch}..HEAD"
        )
        proc = await asyncio.create_subprocess_exec(
            *resolved,
            env=build_sanitized_subprocess_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _stderr = await proc.communicate()
        if proc.returncode != 0 or not stdout:
            return []

        commits: list[tuple[str, str]] = []
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            short_hash, _tab, message = line.partition("\t")
            if short_hash and message:
                commits.append((short_hash.strip(), message.strip()))
        return commits

    def _refresh_header(self) -> None:
        header = self.query_one(KaganHeader)
        project = self.kagan_app.project
        header.update_project(project.name if project is not None else "No project")
        header.update_repo(self.kagan_app.selected_repo_name or "")
        header.update_count(0 if self._task_model is None else 1)

    def _refresh_status_bar_header(self) -> None:
        status = self.query_one(DashboardStatusBar)
        if self._task_model is None:
            status.update_title("-")
            status.update_branch("-")
            status.update_status("Idle")
            status.update_persona("-")
            return

        title = self._task_model.title[:60].strip() or self._task_id
        branch = f"task-{self._task_id[:8]} -> {(self._task_model.base_branch or 'main')}"
        status.update_title(title)
        status.update_branch(branch)

    def _set_compact_status(self, value: str) -> None:
        self.query_one(DashboardStatusBar).update_status(value)
        self._sync_action_bar()

    def _render_stream_chunk(self, output: StreamingOutput, payload: dict[str, Any]) -> None:
        text = stream_chunk_text(payload)
        kind = stream_chunk_kind(payload)
        if not text:
            return
        if kind in {"assistant", "thought", "note", "user"}:
            output.append_chunk(text, kind=cast("Any", kind), merge=True)
            return
        output.append_text(text)

    def _payload_text(self, payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            text = stream_chunk_text(payload)
            if text:
                return text
            nested = acp_payload(payload)
            if nested:
                if "title" in nested:
                    return str(nested["title"])
                if "status" in nested and "sessionUpdate" in nested:
                    return str(nested["status"])
            if "message" in payload:
                return str(payload["message"])
            return " ".join(f"{key}={value}" for key, value in payload.items())
        return str(payload)

    @staticmethod
    def _persona_name(value: str | None) -> str:
        if value is None:
            return "DEFAULT"
        cleaned = value.strip()
        return cleaned.upper() if cleaned else "DEFAULT"
