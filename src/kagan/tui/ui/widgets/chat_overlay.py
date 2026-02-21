"""Native Textual orchestrator overlay backed by ACP agent and AgentStreamRouter.

Orchestrator chat: plan tasks, manage workflow, start/stop agents, and more.
Fullscreen by default when opening project; ``Ctrl+P`` toggles fullscreen and
``Ctrl+O`` toggles docked overlay.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import random
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

from acp.schema import ToolCall as AcpToolCall
from textual import on
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Input, Select, Static

from kagan.core.acp import messages
from kagan.core.agents.agent_factory import AgentFactory, create_agent
from kagan.core.agents.orchestrator import build_orchestrator_prompt
from kagan.core.config import get_fallback_agent_config
from kagan.core.constants import BOX_DRAWING, KAGAN_LOGO, KAGAN_LOGO_SMALL
from kagan.core.domain.enums import MessageType, StreamPhase, TaskStatus, TaskType
from kagan.core.policy import AgentPermissionScope, resolve_auto_approve
from kagan.core.services.jobs import JobStatus
from kagan.core.ux_text import normalize_interaction_verbosity
from kagan.tui.ui.constants import (
    CHAT_OVERLAY_AUTO_STREAM_POLL_FAST_SECONDS,
    CHAT_OVERLAY_AUTO_STREAM_POLL_IDLE_SECONDS,
    CHAT_OVERLAY_AUTO_STREAM_POLL_MEDIUM_SECONDS,
    CHAT_OVERLAY_AUTO_STREAM_RECONCILE_INTERVAL_SECONDS,
    CHAT_OVERLAY_CHAT_TARGETS_CACHE_TTL_SECONDS,
    CHAT_OVERLAY_COMPACT_ENTRY_MAX_CHARS,
    CHAT_OVERLAY_COMPACT_MAX_HISTORY_ITEMS,
    CHAT_OVERLAY_COMPACT_PREVIEW_MAX_CHARS,
    CHAT_OVERLAY_COMPACT_SNAPSHOT_MAX_CHARS,
    CHAT_OVERLAY_ORCHESTRATOR_PROMPT_TIMEOUT_SECONDS,
    CHAT_OVERLAY_SKILL_DESCRIPTION_MAX_CHARS,
    CHAT_OVERLAY_SKILL_DISCOVERY_DISPLAY_LIMIT,
    CHAT_OVERLAY_SKILL_DISCOVERY_MAX_FILES,
    CHAT_OVERLAY_SKILL_METADATA_MAX_BYTES,
)
from kagan.tui.ui.utils.agent_stream_router import AgentStreamRouter
from kagan.tui.ui.utils.helpers import copy_with_notification, is_graceful_agent_termination
from kagan.tui.ui.utils.job_results import job_message, job_result_payload
from kagan.tui.ui.utils.slash_registry import (
    SlashCommand,
    SlashCommandRegistry,
    parse_slash_command_call,
)
from kagan.tui.ui.widgets.chat_overlay_collaborators import (
    ChatOverlaySlashCommandExecutor,
    ChatOverlayStreamCoordinator,
    ChatOverlayTargetManager,
)
from kagan.tui.ui.widgets.chat_overlay_helpers import (
    ChatTarget,
    ChatTargetKind,
    DiscoveredSkill,
    TaskContext,
    build_auto_follow_up_payload,
    build_review_follow_up_payload,
    discover_local_skills_for_roots,
    normalize_agent_failure_for_ui,
    snapshot_preview,
    task_context,
    trusted_skill_roots,
)
from kagan.tui.ui.widgets.plan_approval import PlanApprovalWidget
from kagan.tui.ui.widgets.slash_complete import SlashComplete
from kagan.tui.ui.widgets.status_bar import StatusBar
from kagan.tui.ui.widgets.streaming_output import StreamingOutput

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from acp.schema import AvailableCommand
    from textual import events
    from textual.app import ComposeResult
    from textual.timer import Timer
    from textual.widget import Widget

    from kagan.core.acp import Agent

type ChatOverlaySlashHandler = Callable[[str], None | Awaitable[None]]


class ChatOverlay(Vertical):
    """Orchestrator overlay with fullscreen default and mode cycling support."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "escape_overlay", show=False, priority=True),
        Binding("ctrl+c", "ctrl_c", show=False, priority=True),
    ]

    _ORCHESTRATOR_PROMPT_TIMEOUT_SECONDS = CHAT_OVERLAY_ORCHESTRATOR_PROMPT_TIMEOUT_SECONDS
    _INTRO_HEADING = "What are we building?"
    _INTRO_QUOTE_PROBABILITY = 0.35
    _INTRO_QUOTES: tuple[tuple[str, str], ...] = (
        ("Funny", "A clean backlog is just organized ambition."),
        ("Funny", "If the plan survives Monday, ship it."),
        ("Funny", "Ship small. Celebrate often. Blame the cache last."),
        ("Wise", "Clarity today beats heroics tomorrow."),
        ("Wise", "Momentum comes from finishing the next smallest thing."),
        ("Wise", "Good systems reward honesty about tradeoffs."),
    )
    _EXAMPLES: tuple[str, ...] = (
        '"Plan a rollout for GitHub issue sync"',
        '"Break this feature into parallel tasks"',
        '"Draft acceptance criteria for the milestone"',
    )
    _FULLSCREEN_LOGO = KAGAN_LOGO
    _POPUP_LOGO = KAGAN_LOGO_SMALL
    _COMPACT_MAX_HISTORY_ITEMS = CHAT_OVERLAY_COMPACT_MAX_HISTORY_ITEMS
    _COMPACT_ENTRY_MAX_CHARS = CHAT_OVERLAY_COMPACT_ENTRY_MAX_CHARS
    _COMPACT_SNAPSHOT_MAX_CHARS = CHAT_OVERLAY_COMPACT_SNAPSHOT_MAX_CHARS
    _COMPACT_PREVIEW_MAX_CHARS = CHAT_OVERLAY_COMPACT_PREVIEW_MAX_CHARS
    _CHAT_TARGETS_CACHE_TTL_SECONDS = CHAT_OVERLAY_CHAT_TARGETS_CACHE_TTL_SECONDS
    _SKILL_METADATA_MAX_BYTES = CHAT_OVERLAY_SKILL_METADATA_MAX_BYTES
    _SKILL_DESCRIPTION_MAX_CHARS = CHAT_OVERLAY_SKILL_DESCRIPTION_MAX_CHARS
    _SKILL_DISCOVERY_MAX_FILES = CHAT_OVERLAY_SKILL_DISCOVERY_MAX_FILES
    _SKILL_DISCOVERY_DISPLAY_LIMIT = CHAT_OVERLAY_SKILL_DISCOVERY_DISPLAY_LIMIT
    _AUTO_STREAM_POLL_FAST_SECONDS = CHAT_OVERLAY_AUTO_STREAM_POLL_FAST_SECONDS
    _AUTO_STREAM_POLL_MEDIUM_SECONDS = CHAT_OVERLAY_AUTO_STREAM_POLL_MEDIUM_SECONDS
    _AUTO_STREAM_POLL_IDLE_SECONDS = CHAT_OVERLAY_AUTO_STREAM_POLL_IDLE_SECONDS
    _AUTO_STREAM_RECONCILE_INTERVAL_SECONDS = CHAT_OVERLAY_AUTO_STREAM_RECONCILE_INTERVAL_SECONDS
    _SESSION_SWITCH_NOTIFY_DEBOUNCE_SECONDS = 0.2
    _RECENT_SESSION_LIMIT = 6
    _ORCHESTRATOR_INPUT_PLACEHOLDER = "Describe your task... (/ for commands)"
    _AGENT_COMMAND_GROUP = "agent"
    _REMOVED_SLASH_COMMAND_NAMES: frozenset[str] = frozenset(
        {
            "consent",
            "textual",
        }
    )
    _SUPPRESSED_AGENT_COMMAND_NAMES: frozenset[str] = frozenset(
        {
            "emotion-best-practice",
            "emotion-best-practices",
            "remotion-best-practice",
            "remotion-best-practices",
            "textual",
        }
    )

    def __init__(
        self,
        agent_factory: AgentFactory = create_agent,
        *,
        embedded: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._agent_factory = agent_factory
        self._embedded = embedded
        self._agent: Agent | None = None
        initial_scope = self._new_orchestrator_session_scope_id()
        self._orchestrator_session_scope_ids: list[str] = [initial_scope]
        self._orchestrator_session_labels: dict[str, str] = {initial_scope: "Orchestrator"}
        self._orchestrator_session_label_counter: int = 1
        self._active_orchestrator_session_scope_id: str = initial_scope
        # Backward-compatible alias used by existing tests and integrations.
        self._orchestrator_session_scope_id: str = initial_scope
        self._conversation_history_by_target_key: dict[str, list[tuple[str, str]]] = {}
        self._pending_compact_snapshot_by_target_key: dict[str, str] = {}
        self._clearing: bool = False
        self._current_mode: str = ""
        self._available_modes: dict[str, messages.Mode] = {}
        self._available_commands: list[AvailableCommand] = []
        self._slash_complete: SlashComplete | None = None
        self._slash_registry: SlashCommandRegistry[ChatOverlaySlashHandler] = SlashCommandRegistry()
        self._chat_targets: list[ChatTarget] = [self._orchestrator_target(initial_scope)]
        self._active_target_index: int = 0
        self._task_context_by_id: dict[str, TaskContext] = {}
        self._requested_task_id: str | None = None
        self._requested_task_context: TaskContext | None = None
        self._focused_task_context: TaskContext | None = None
        self._target_scope_task_id: str | None = None
        self._chat_targets_cache_at: float = 0.0
        self._chat_targets_cache_key: tuple[object, ...] | None = None
        self._focus_return_target: Widget | None = None
        self._agent_stream_router: AgentStreamRouter | None = None
        self._cancel_requested: bool = False
        self._discovered_skills: list[DiscoveredSkill] = []
        self._skills_loaded: bool = False
        self._auto_stream_task_id: str | None = None
        self._auto_stream_execution_id: str | None = None
        self._auto_stream_entry_offsets: dict[str, int] = {}
        self._auto_stream_wait_noted: bool = False
        self._auto_stream_idle_noted: bool = False
        self._auto_stream_poll_interval_seconds: float = self._AUTO_STREAM_POLL_FAST_SECONDS
        self._auto_stream_last_reconcile_at: float = 0.0
        self._synchronizing_session_selector: bool = False
        self._session_selector_options_cache: list[tuple[str, str]] = []
        self._last_overlay_visibility_state: tuple[bool, bool] | None = None
        self._drafts_by_target_key: dict[str, str] = {}
        self._output_snapshot_by_target_key: dict[str, str] = {}
        self._active_input_target_key: str | None = None
        self._session_switch_in_flight: int = 0
        self._chat_input_disable_depth: int = 0
        self._recent_target_keys: list[str] = []
        self._session_switch_notify_timer: Timer | None = None
        self._pending_session_notify_label: str | None = None
        self._last_submitted_prompt: str = ""
        self._target_manager = ChatOverlayTargetManager(self)
        self._slash_executor = ChatOverlaySlashCommandExecutor(self)
        self._stream_coordinator = ChatOverlayStreamCoordinator(self)
        self._intro_quote: str = self._build_intro_quote()
        self.set_class(bool(self._intro_quote), "chat-overlay-has-quote")
        self.set_class(self._embedded, "embedded")
        self._register_slash_commands()

    def compose(self) -> ComposeResult:
        with Container(id="chat-overlay-main"):
            with Vertical(id="chat-overlay-content"):
                with Vertical(id="chat-overlay-empty-state", classes="chat-overlay-empty-state"):
                    with Vertical(classes="chat-overlay-empty-content"):
                        with Vertical(classes="chat-overlay-empty-card"):
                            yield Static(KAGAN_LOGO, id="chat-overlay-logo")
                            yield Static(
                                self._INTRO_HEADING,
                                id="chat-overlay-empty-heading",
                            )
                            yield Static(self._intro_quote, id="chat-overlay-empty-quote")
                            yield Static(
                                "Describe the work. Kagan plans, executes, and reviews.",
                                id="chat-overlay-empty-description",
                            )
                            with Vertical(id="chat-overlay-empty-examples"):
                                yield Static(
                                    "Examples:",
                                    classes="chat-overlay-empty-section-title",
                                )
                                for example in self._EXAMPLES:
                                    yield Static(
                                        f"  {BOX_DRAWING['BULLET']} {example}",
                                        classes="chat-overlay-empty-example",
                                    )
                yield StreamingOutput(id="chat-overlay-output")
            with Vertical(id="chat-overlay-bottom"):
                yield StatusBar(id="chat-overlay-status")
                with Horizontal(id="chat-overlay-command-line"):
                    yield Static(">", id="chat-overlay-input-prompt")
                    yield Input(
                        placeholder=self._ORCHESTRATOR_INPUT_PLACEHOLDER,
                        id="chat-overlay-input",
                    )
                with Horizontal(id="chat-overlay-session-switcher"):
                    with Horizontal(id="chat-overlay-session-current-wrap"):
                        yield Static("Docked", id="chat-overlay-mode-badge")
                        yield Static(
                            "●",
                            id="chat-overlay-session-indicator",
                            classes="session-kind-orchestrator",
                        )
                        yield Static(
                            "Orchestrator",
                            id="chat-overlay-session-current",
                        )
                    with Horizontal(id="chat-overlay-session-toggle"):
                        yield Static("Session", id="chat-overlay-session-toggle-label")
                        yield Select[str](
                            options=[("Orchestrator", ChatTargetKind.ORCHESTRATOR.value)],
                            value=ChatTargetKind.ORCHESTRATOR.value,
                            id="chat-overlay-session-select",
                            allow_blank=False,
                            compact=True,
                        )

    @property
    def output(self) -> StreamingOutput:
        return self.query_one("#chat-overlay-output", StreamingOutput)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one("#chat-overlay-status", StatusBar)

    def _build_intro_quote(self) -> str:
        if random.random() >= self._INTRO_QUOTE_PROBABILITY:
            return ""
        _, quote = random.choice(self._INTRO_QUOTES)
        return f'"{quote}"'

    def _refresh_intro_quote(self) -> None:
        self._intro_quote = self._build_intro_quote()
        self.set_class(bool(self._intro_quote), "chat-overlay-has-quote")
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-empty-quote", Static).update(self._intro_quote)

    def _auto_skill_discovery_enabled(self) -> bool:
        with contextlib.suppress(Exception):
            config = getattr(self.app, "config", None)
            general = getattr(config, "general", None)
            return bool(getattr(general, "auto_skill_discovery", False))
        return False

    @classmethod
    def _discover_local_skills_for_roots(cls, roots: list[Path]) -> list[DiscoveredSkill]:
        return discover_local_skills_for_roots(
            roots,
            discovery_max_files=cls._SKILL_DISCOVERY_MAX_FILES,
            metadata_max_bytes=cls._SKILL_METADATA_MAX_BYTES,
            description_max_chars=cls._SKILL_DESCRIPTION_MAX_CHARS,
        )

    def _discover_local_skills(self, *, force_refresh: bool = False) -> list[DiscoveredSkill]:
        if not self._auto_skill_discovery_enabled():
            self._discovered_skills = []
            self._skills_loaded = False
            return []
        if self._skills_loaded and not force_refresh:
            return list(self._discovered_skills)
        roots = trusted_skill_roots(self._skill_project_root())
        self._discovered_skills = self._discover_local_skills_for_roots(roots)
        self._skills_loaded = True
        return list(self._discovered_skills)

    def _skill_project_root(self) -> Path:
        project_root = Path.cwd()
        with contextlib.suppress(Exception):
            project_root = Path(getattr(self.app, "project_root", project_root))
        return project_root

    async def _discover_local_skills_async(
        self,
        *,
        force_refresh: bool = False,
    ) -> list[DiscoveredSkill]:
        if not self._auto_skill_discovery_enabled():
            self._discovered_skills = []
            self._skills_loaded = False
            return []
        if self._skills_loaded and not force_refresh:
            return list(self._discovered_skills)
        roots = trusted_skill_roots(self._skill_project_root())
        discovered = await asyncio.to_thread(self._discover_local_skills_for_roots, roots)
        self._discovered_skills = discovered
        self._skills_loaded = True
        return list(self._discovered_skills)

    @classmethod
    def _task_context(cls, task: object) -> TaskContext | None:
        return task_context(task)

    @staticmethod
    def _orchestrator_target_key(scope_id: str) -> str:
        return f"{ChatTargetKind.ORCHESTRATOR.value}:{scope_id}"

    @staticmethod
    def _parse_orchestrator_scope_from_key(target_key: str) -> str | None:
        if target_key == ChatTargetKind.ORCHESTRATOR.value:
            return None
        prefix = f"{ChatTargetKind.ORCHESTRATOR.value}:"
        if not target_key.startswith(prefix):
            return None
        normalized = target_key[len(prefix) :].strip()
        return normalized or None

    def _active_orchestrator_target_key(self) -> str:
        return self._orchestrator_target_key(self._active_orchestrator_session_scope_id)

    def _orchestrator_target(self, scope_id: str | None = None) -> ChatTarget:
        active_scope = scope_id or self._active_orchestrator_session_scope_id
        return ChatTarget(
            key=self._orchestrator_target_key(active_scope),
            kind=ChatTargetKind.ORCHESTRATOR,
            label=self._orchestrator_session_labels.get(active_scope, "Orchestrator"),
            task_id=None,
        )

    def _orchestrator_targets(self) -> list[ChatTarget]:
        targets: list[ChatTarget] = []
        for scope_id in self._orchestrator_session_scope_ids:
            targets.append(self._orchestrator_target(scope_id))
        return targets

    def _create_orchestrator_session(self) -> str:
        scope_id = self._new_orchestrator_session_scope_id()
        self._orchestrator_session_label_counter += 1
        label = f"Orchestrator {self._orchestrator_session_label_counter}"
        self._orchestrator_session_scope_ids.append(scope_id)
        self._orchestrator_session_labels[scope_id] = label
        self._chat_targets_cache_key = None
        self._chat_targets_cache_at = 0.0
        return scope_id

    def _drop_orchestrator_session_data(self, scope_id: str) -> None:
        target_key = self._orchestrator_target_key(scope_id)
        self._drafts_by_target_key.pop(target_key, None)
        self._output_snapshot_by_target_key.pop(target_key, None)
        self._conversation_history_by_target_key.pop(target_key, None)
        self._pending_compact_snapshot_by_target_key.pop(target_key, None)
        self._recent_target_keys = [key for key in self._recent_target_keys if key != target_key]

    def _remove_orchestrator_session(self, scope_id: str) -> bool:
        if scope_id not in self._orchestrator_session_scope_ids:
            return False
        if len(self._orchestrator_session_scope_ids) <= 1:
            return False
        self._orchestrator_session_scope_ids = [
            existing_scope
            for existing_scope in self._orchestrator_session_scope_ids
            if existing_scope != scope_id
        ]
        self._orchestrator_session_labels.pop(scope_id, None)
        self._drop_orchestrator_session_data(scope_id)
        if self._active_orchestrator_session_scope_id == scope_id:
            self._active_orchestrator_session_scope_id = self._orchestrator_session_scope_ids[0]
            self._orchestrator_session_scope_id = self._active_orchestrator_session_scope_id
        self._chat_targets_cache_key = None
        self._chat_targets_cache_at = 0.0
        return True

    def _reset_orchestrator_sessions(self) -> str:
        for scope_id in list(self._orchestrator_session_scope_ids):
            self._drop_orchestrator_session_data(scope_id)
        fresh_scope = self._new_orchestrator_session_scope_id()
        self._orchestrator_session_scope_ids = [fresh_scope]
        self._orchestrator_session_labels = {fresh_scope: "Orchestrator"}
        self._orchestrator_session_label_counter = 1
        self._active_orchestrator_session_scope_id = fresh_scope
        self._orchestrator_session_scope_id = fresh_scope
        self._chat_targets_cache_key = None
        self._chat_targets_cache_at = 0.0
        return fresh_scope

    @staticmethod
    def _new_orchestrator_session_scope_id() -> str:
        return f"orchestrator-{uuid4().hex[:12]}"

    def _fallback_scoped_target(self, task_id: str) -> ChatTarget:
        short_id = task_id[:8]
        return ChatTarget(
            key=f"{ChatTargetKind.AUTO.value}:{task_id}",
            kind=ChatTargetKind.AUTO,
            label=f"AUTO #{short_id}",
            task_id=task_id,
        )

    def _active_target(self) -> ChatTarget:
        if not self._chat_targets:
            return self._orchestrator_target()
        if self._active_target_index >= len(self._chat_targets):
            self._active_target_index = 0
        return self._chat_targets[self._active_target_index]

    @staticmethod
    def _append_target_if_missing(targets: list[ChatTarget], target: ChatTarget | None) -> None:
        if target is None:
            return
        if any(existing.key == target.key for existing in targets):
            return
        targets.append(target)

    @staticmethod
    def _context_target_kind(context: TaskContext) -> ChatTargetKind:
        if context.status is TaskStatus.DONE:
            return ChatTargetKind.ORCHESTRATOR
        if context.status is TaskStatus.REVIEW:
            return ChatTargetKind.REVIEW
        if context.task_type is TaskType.AUTO:
            return ChatTargetKind.AUTO
        return ChatTargetKind.ORCHESTRATOR

    @staticmethod
    def _target_label_prefix(kind: ChatTargetKind) -> str:
        if kind is ChatTargetKind.AUTO:
            return "AUTO"
        if kind is ChatTargetKind.REVIEW:
            return "REVIEW"
        if kind is ChatTargetKind.PAIR:
            return "PAIR"
        raise ValueError(f"Unsupported chat target kind for task context: {kind.value}")

    def _target_for_kind(self, context: TaskContext, kind: ChatTargetKind) -> ChatTarget | None:
        if kind is ChatTargetKind.ORCHESTRATOR:
            return None
        label_prefix = self._target_label_prefix(kind)
        return ChatTarget(
            key=f"{kind.value}:{context.task_id}",
            kind=kind,
            label=f"{label_prefix} #{context.short_id} · {context.title}",
            task_id=context.task_id,
        )

    def _target_from_context(self, context: TaskContext) -> ChatTarget | None:
        kind = self._context_target_kind(context)
        return self._target_for_kind(context, kind)

    def _scoped_targets_for_context(self, context: TaskContext) -> list[ChatTarget]:
        targets: list[ChatTarget] = []
        if context.task_type is TaskType.AUTO:
            self._append_target_if_missing(
                targets,
                self._target_for_kind(context, ChatTargetKind.AUTO),
            )
            self._append_target_if_missing(
                targets,
                self._target_for_kind(context, ChatTargetKind.REVIEW),
            )
            return targets
        self._append_target_if_missing(targets, self._target_from_context(context))
        return targets

    def _preferred_target_key_for_context(
        self,
        context: TaskContext,
        targets: list[ChatTarget],
    ) -> str:
        preferred_kind = self._context_target_kind(context)
        if preferred_kind is not ChatTargetKind.ORCHESTRATOR:
            expected_key = f"{preferred_kind.value}:{context.task_id}"
            if any(target.key == expected_key for target in targets):
                return expected_key
        for target in targets:
            if target.task_id == context.task_id:
                return target.key
        return self._active_orchestrator_target_key()

    async def _refresh_chat_targets(self, *, force: bool = False) -> None:
        await self._target_manager.refresh_chat_targets(force=force)

    def _session_selector_options(self, *, active_target: ChatTarget) -> list[tuple[str, str]]:
        targets = self._chat_targets or [active_target]
        return [(target.label, target.key) for target in targets]

    @staticmethod
    def _target_icon(target: ChatTarget, context: TaskContext | None) -> str:
        if target.kind is ChatTargetKind.REVIEW:
            return "◎"
        if target.kind is ChatTargetKind.ORCHESTRATOR:
            return "●"
        if target.kind is ChatTargetKind.AUTO:
            if context is not None and context.status is TaskStatus.IN_PROGRESS:
                return "◉"
            return "○"
        return "○"

    def _attention_targets(self) -> list[ChatTarget]:
        """Subset of scoped targets that need immediate attention."""
        active_targets: list[ChatTarget] = []
        for target in self._chat_targets:
            if target.kind is ChatTargetKind.REVIEW:
                active_targets.append(target)
                continue
            if target.kind is ChatTargetKind.AUTO and target.task_id:
                context = self._task_context_by_id.get(target.task_id)
                if context is not None and context.status is TaskStatus.IN_PROGRESS:
                    active_targets.append(target)
        return active_targets if active_targets else list(self._chat_targets)

    @staticmethod
    def _task_id_from_target_key(target_key: str) -> str | None:
        prefix, separator, suffix = target_key.partition(":")
        if not separator:
            return None
        if prefix not in {
            ChatTargetKind.AUTO.value,
            ChatTargetKind.REVIEW.value,
            ChatTargetKind.PAIR.value,
        }:
            return None
        normalized = suffix.strip()
        return normalized or None

    @staticmethod
    def _target_role_label(target: ChatTarget) -> str:
        if target.kind is ChatTargetKind.ORCHESTRATOR:
            return "Orchestrator"
        if target.kind is ChatTargetKind.AUTO:
            return "Worker"
        if target.kind is ChatTargetKind.REVIEW:
            return "Reviewer"
        if target.kind is ChatTargetKind.PAIR:
            return "Pair"
        return target.kind.value.title()

    def _store_output_snapshot_for_target(self, target_key: str) -> None:
        with contextlib.suppress(NoMatches):
            snapshot = self.output.get_text_content().strip()
            if snapshot:
                self._output_snapshot_by_target_key[target_key] = snapshot
            else:
                self._output_snapshot_by_target_key.pop(target_key, None)

    async def _restore_output_for_target(self, target: ChatTarget) -> None:
        if target.kind is ChatTargetKind.AUTO:
            # AUTO targets hydrate from live execution logs and status notes.
            self._show_output()
            return
        snapshot = self._output_snapshot_by_target_key.get(target.key, "").strip()
        if not snapshot:
            self.remove_class("has-content")
            self._refresh_intro_quote()
            return
        self._show_output()
        await self.output.post_note(snapshot, classes="session-snapshot")

    async def _activate_orchestrator_session_scope(self, scope_id: str) -> None:
        if scope_id not in self._orchestrator_session_scope_ids:
            return
        previous_scope = self._active_orchestrator_session_scope_id
        self._active_orchestrator_session_scope_id = scope_id
        self._orchestrator_session_scope_id = scope_id
        if previous_scope == scope_id:
            return
        if self._agent is not None:
            with contextlib.suppress(Exception):
                await self._agent.stop()
            self._agent = None
        await self._ensure_agent()

    def _begin_session_switch(self) -> None:
        self._session_switch_in_flight += 1
        self._set_chat_input_disabled(True)
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            chat_input.value = ""
        if self._active_input_target_key:
            self._drafts_by_target_key[self._active_input_target_key] = ""
        self._sync_meta_chips("")

    def _end_session_switch(self) -> None:
        if self._session_switch_in_flight > 0:
            self._session_switch_in_flight -= 1
        self._set_chat_input_disabled(False)

    def _record_recent_target(self, target_key: str) -> None:
        normalized_key = str(target_key).strip()
        if not normalized_key:
            return
        self._recent_target_keys = [
            key for key in self._recent_target_keys if key != normalized_key
        ]
        self._recent_target_keys.insert(0, normalized_key)
        if len(self._recent_target_keys) > self._RECENT_SESSION_LIMIT:
            self._recent_target_keys = self._recent_target_keys[: self._RECENT_SESSION_LIMIT]

    def _cancel_session_switch_notification_timer(self) -> None:
        if self._session_switch_notify_timer is None:
            self._pending_session_notify_label = None
            return
        self._session_switch_notify_timer.stop()
        self._session_switch_notify_timer = None
        self._pending_session_notify_label = None

    def _schedule_session_switch_notification(self, label: str) -> None:
        normalized_label = str(label).strip()
        if not normalized_label:
            return
        self._cancel_session_switch_notification_timer()
        self._pending_session_notify_label = normalized_label

        def _notify_session_switch() -> None:
            self._session_switch_notify_timer = None
            pending_label = self._pending_session_notify_label
            self._pending_session_notify_label = None
            if pending_label:
                self.notify(f"Chat session: {pending_label}", severity="information")

        self._session_switch_notify_timer = self.set_timer(
            self._SESSION_SWITCH_NOTIFY_DEBOUNCE_SECONDS,
            _notify_session_switch,
        )

    async def _switch_active_target_by_key(self, selected_key: str, *, notify: bool = True) -> None:
        current_target = self._active_target()
        selected_orchestrator_scope = self._parse_orchestrator_scope_from_key(selected_key)
        if selected_key == ChatTargetKind.ORCHESTRATOR.value:
            selected_orchestrator_scope = self._active_orchestrator_session_scope_id
        if selected_orchestrator_scope is not None:
            selected_key = self._orchestrator_target_key(selected_orchestrator_scope)
        if selected_key == current_target.key:
            return

        self._begin_session_switch()
        try:
            if current_target.kind is not ChatTargetKind.AUTO:
                self._store_output_snapshot_for_target(current_target.key)
            await self.output.clear()
            self.remove_class("has-content")

            target_found = False
            for index, target in enumerate(self._chat_targets):
                if target.key != selected_key:
                    continue
                self._active_target_index = index
                target_found = True
                break

            if not target_found:
                await self._refresh_chat_targets()
                for index, target in enumerate(self._chat_targets):
                    if target.key != selected_key:
                        continue
                    self._active_target_index = index
                    target_found = True
                    break

            if not target_found:
                if selected_orchestrator_scope is not None:
                    self._target_scope_task_id = None
                    self._requested_task_id = None
                    self._requested_task_context = None
                    if selected_orchestrator_scope in self._orchestrator_session_scope_ids:
                        await self._activate_orchestrator_session_scope(selected_orchestrator_scope)
                    self._chat_targets_cache_key = None
                    self._chat_targets_cache_at = 0.0
                    await self._refresh_chat_targets(force=True)
                elif task_id := self._task_id_from_target_key(selected_key):
                    self._target_scope_task_id = task_id
                    self._chat_targets_cache_key = None
                    self._chat_targets_cache_at = 0.0
                    self._requested_task_id = task_id
                    context = self._task_context_by_id.get(task_id)
                    if context is not None:
                        self._requested_task_context = context
                    await self._refresh_chat_targets(force=True)

                for index, target in enumerate(self._chat_targets):
                    if target.key != selected_key:
                        continue
                    self._active_target_index = index
                    target_found = True
                    break

            if not target_found:
                self._active_target_index = 0

            active_target = self._active_target()
            if active_target.kind is ChatTargetKind.ORCHESTRATOR:
                active_scope = self._parse_orchestrator_scope_from_key(active_target.key)
                if active_scope is None:
                    active_scope = self._active_orchestrator_session_scope_id
                await self._activate_orchestrator_session_scope(active_scope)

            self._record_recent_target(active_target.key)
            self._sync_active_target_ui(notify=notify)
            await self._restore_output_for_target(active_target)
            with contextlib.suppress(Exception):
                await self._sync_active_target_session()
        finally:
            self._end_session_switch()

    def _sync_session_selector_ui(self, target: ChatTarget) -> None:
        self._sync_overlay_mode_badge()
        total_targets = len(self._chat_targets) or 1
        current_position = min(self._active_target_index + 1, total_targets)
        self.set_class(total_targets > 1, "chat-overlay-multi-session")
        current_text = target.label
        if total_targets > 1:
            current_text = f"{current_text} ({current_position}/{total_targets})"
        with contextlib.suppress(NoMatches):
            current = self.query_one("#chat-overlay-session-current", Static)
            current.update(current_text)
        with contextlib.suppress(NoMatches):
            indicator = self.query_one("#chat-overlay-session-indicator", Static)
            indicator.update("●")
            indicator.set_class(
                target.kind is ChatTargetKind.ORCHESTRATOR,
                "session-kind-orchestrator",
            )
            indicator.set_class(target.kind is ChatTargetKind.AUTO, "session-kind-auto")
            indicator.set_class(target.kind is ChatTargetKind.REVIEW, "session-kind-review")
            indicator.set_class(target.kind is ChatTargetKind.PAIR, "session-kind-pair")
        with contextlib.suppress(NoMatches):
            selector = self.query_one("#chat-overlay-session-select", Select)
            options = self._session_selector_options(active_target=target)
            self._synchronizing_session_selector = True
            try:
                if self._session_selector_options_cache != options:
                    selector.set_options(options)
                    self._session_selector_options_cache = list(options)
                if selector.value != target.key:
                    selector.value = target.key
            finally:
                self._synchronizing_session_selector = False

    @staticmethod
    def _mode_bucket(mode_id: str, mode_name: str = "") -> str:
        descriptor = f"{mode_id} {mode_name}".lower()
        if any(token in descriptor for token in ("plan", "planner", "tasks")):
            return "plan"
        if any(
            token in descriptor
            for token in ("exec", "worker", "implement", "code", "edit", "review")
        ):
            return "execute"
        return "ask"

    def _active_mode_bucket(self) -> str:
        if self._current_mode and self._current_mode in self._available_modes:
            mode = self._available_modes[self._current_mode]
            return self._mode_bucket(self._current_mode, mode.name)
        if self._current_mode:
            return self._mode_bucket(self._current_mode)
        return "ask"

    def _mode_for_bucket(self, bucket: str) -> str | None:
        for mode_id, mode in self._available_modes.items():
            if self._mode_bucket(mode_id, mode.name) == bucket:
                return mode_id
        return None

    def _should_default_to_execute_mode(self) -> bool:
        """Check if current context warrants defaulting to execute mode.

        PAIR task sessions should default to execute mode since the task context
        is already defined. Ask and Plan modes add unnecessary friction when
        the user is actively collaborating on a concrete task.
        """
        context = self._focused_task_context or self._requested_task_context
        if context is None:
            return False
        return context.task_type is TaskType.PAIR

    def _apply_pair_mode_default(self) -> None:
        """Apply execute mode default for PAIR task sessions.

        When in a PAIR task context and execute mode is available, switch to it
        automatically. Users can still switch modes explicitly via slash command.
        """
        if not self._should_default_to_execute_mode():
            return
        if self._active_mode_bucket() == "execute":
            return
        execute_mode_id = self._mode_for_bucket("execute")
        if execute_mode_id is None:
            return
        self._run_overlay_worker(
            self._switch_to_execute_mode(execute_mode_id),
            group="chat-overlay-pair-mode-default",
            exclusive=True,
        )

    async def _switch_to_execute_mode(self, mode_id: str) -> None:
        """Switch to execute mode without user notification."""
        await self._ensure_agent()
        if self._agent is None or not hasattr(self._agent, "set_mode"):
            return
        error = await self._agent.set_mode(mode_id)
        if error:
            return
        self._current_mode = mode_id
        self._sync_mode_chip_ui()
        self._sync_meta_chips()

    def _sync_mode_chip_ui(self) -> None:
        # Command rail is intentionally minimal: mode chips were removed.
        return

    def _sync_meta_chips(self, text: str | None = None) -> None:
        _ = text
        # Meta chips and submit intent were removed from the command rail.
        return

    def _sync_active_target_ui(self, *, notify: bool = False) -> None:
        target = self._active_target()
        if target.task_id:
            context = self._task_context_by_id.get(target.task_id)
            if context is not None:
                self._focused_task_context = context
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            previous_key = self._active_input_target_key
            if previous_key and previous_key != target.key:
                self._drafts_by_target_key[previous_key] = ""
            if previous_key != target.key:
                self._active_input_target_key = target.key
                self._drafts_by_target_key[target.key] = ""
                chat_input.value = ""
            else:
                self._active_input_target_key = target.key
            if target.kind is ChatTargetKind.ORCHESTRATOR:
                chat_input.placeholder = self._ORCHESTRATOR_INPUT_PLACEHOLDER
            elif target.kind is ChatTargetKind.AUTO:
                chat_input.placeholder = f"Send follow-up to {target.label}"
            else:
                chat_input.placeholder = f"Queue review follow-up for {target.label}"
        self._sync_session_selector_ui(target)
        self._sync_mode_chip_ui()
        self._sync_meta_chips()
        with contextlib.suppress(NoMatches):
            if self.status_bar.status == "ready":
                self.status_bar.update_status("ready", self._ready_hint(target))
        if notify:
            self._schedule_session_switch_notification(target.label)

    @staticmethod
    def _state_attr(
        state: object | None, name: str, default: object | None = None
    ) -> object | None:
        if state is None:
            return default
        if isinstance(state, dict):
            return state.get(name, default)
        return getattr(state, name, default)

    def _reset_auto_stream_state(self, *, task_id: str | None = None) -> None:
        if task_id is not None and self._auto_stream_task_id != task_id:
            return
        self._auto_stream_task_id = None
        self._auto_stream_execution_id = None
        self._auto_stream_entry_offsets.clear()
        self._auto_stream_wait_noted = False
        self._auto_stream_idle_noted = False
        self._auto_stream_poll_interval_seconds = self._AUTO_STREAM_POLL_FAST_SECONDS
        self._auto_stream_last_reconcile_at = 0.0

    def _set_auto_stream_poll_interval(self, interval_seconds: float) -> None:
        self._auto_stream_poll_interval_seconds = max(
            self._AUTO_STREAM_POLL_FAST_SECONDS,
            min(interval_seconds, self._AUTO_STREAM_POLL_IDLE_SECONDS),
        )

    def _is_active_auto_stream_target(self, task_id: str) -> bool:
        if not self.has_class("visible"):
            return False
        target = self._active_target()
        return target.kind is ChatTargetKind.AUTO and target.task_id == task_id

    async def _sync_active_target_session(self) -> None:
        target = self._active_target()
        if target.kind is not ChatTargetKind.AUTO or not target.task_id:
            self._reset_auto_stream_state()
            return
        if not self.has_class("visible"):
            self._reset_auto_stream_state()
            return
        self._show_output()
        self.output.action_jump_to_live()
        await self._refresh_auto_stream_for_task(target.task_id)
        self._run_overlay_worker(
            self._run_auto_stream_loop(target.task_id),
            group="chat-overlay-auto-stream",
            exclusive=True,
        )

    async def _run_auto_stream_loop(self, task_id: str) -> None:
        while self.has_class("visible"):
            target = self._active_target()
            if target.kind is not ChatTargetKind.AUTO or target.task_id != task_id:
                return
            await self._refresh_auto_stream_for_task(task_id)
            await asyncio.sleep(self._auto_stream_poll_interval_seconds)

    async def _refresh_auto_stream_for_task(self, task_id: str) -> None:
        if not self._is_active_auto_stream_target(task_id):
            return
        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            return

        if self._auto_stream_task_id != task_id:
            self._auto_stream_task_id = task_id
            self._auto_stream_execution_id = None
            self._auto_stream_entry_offsets.clear()
            self._auto_stream_wait_noted = False
            self._auto_stream_idle_noted = False
            self._auto_stream_poll_interval_seconds = self._AUTO_STREAM_POLL_FAST_SECONDS
            self._auto_stream_last_reconcile_at = 0.0

        now = monotonic()
        if (
            self._auto_stream_last_reconcile_at <= 0
            or now - self._auto_stream_last_reconcile_at
            >= self._AUTO_STREAM_RECONCILE_INTERVAL_SECONDS
        ):
            with contextlib.suppress(Exception):
                await ctx.api.reconcile_running_tasks([task_id])
            self._auto_stream_last_reconcile_at = now
            if not self._is_active_auto_stream_target(task_id):
                return

        readiness = None
        with contextlib.suppress(Exception):
            readiness = await ctx.api.prepare_auto_output(task_id)
        if not self._is_active_auto_stream_target(task_id):
            return
        is_running = bool(self._state_attr(readiness, "is_running", False))
        execution_id = self._state_attr(readiness, "execution_id")
        execution_id_str = str(execution_id).strip() if execution_id is not None else ""

        if not execution_id_str and is_running:
            with contextlib.suppress(Exception):
                latest_execution = await ctx.api.get_latest_execution_for_task(task_id)
                latest_id = self._state_attr(latest_execution, "id")
                execution_id_str = str(latest_id).strip() if latest_id is not None else ""
            if not self._is_active_auto_stream_target(task_id):
                return

        if not execution_id_str:
            if is_running and not self._auto_stream_wait_noted:
                await self.output.post_note("Waiting for live AUTO stream...", classes="warning")
                self._auto_stream_wait_noted = True
                self._auto_stream_idle_noted = False
                self._set_auto_stream_poll_interval(self._AUTO_STREAM_POLL_MEDIUM_SECONDS)
            elif not is_running and not self._auto_stream_idle_noted:
                await self.output.post_note(
                    "AUTO run is idle. Send a follow-up or `/restart` to run a new iteration.",
                    classes="info",
                )
                self._auto_stream_idle_noted = True
                self._auto_stream_wait_noted = False
                self._set_auto_stream_poll_interval(self._AUTO_STREAM_POLL_IDLE_SECONDS)
            return

        if self._auto_stream_execution_id != execution_id_str:
            self._auto_stream_execution_id = execution_id_str
            self._auto_stream_entry_offsets.clear()
            self._auto_stream_wait_noted = False
            self._auto_stream_idle_noted = False
            await self.output.post_note(
                f"Watching AUTO execution `{execution_id_str[:8]}`.",
                classes="info",
            )

        try:
            entries = await ctx.api.get_execution_log_entries(execution_id_str)
        except Exception:
            return
        if not self._is_active_auto_stream_target(task_id):
            return
        if not entries:
            if is_running and not self._auto_stream_wait_noted:
                await self.output.post_note(
                    "Connected to AUTO stream; waiting for first output chunk...",
                    classes="warning",
                )
                self._auto_stream_wait_noted = True
                self._auto_stream_idle_noted = False
                self._set_auto_stream_poll_interval(self._AUTO_STREAM_POLL_MEDIUM_SECONDS)
            elif not is_running and not self._auto_stream_idle_noted:
                await self.output.post_note(
                    "AUTO run is idle. Send a follow-up or `/restart` to run a new iteration.",
                    classes="info",
                )
                self._auto_stream_idle_noted = True
                self._auto_stream_wait_noted = False
                self._set_auto_stream_poll_interval(self._AUTO_STREAM_POLL_IDLE_SECONDS)
            return

        rendered = False
        for index, entry in enumerate(entries):
            entry_id = self._state_attr(entry, "id", f"idx-{index}")
            normalized_id = str(entry_id)
            logs = self._state_attr(entry, "logs")
            if not isinstance(logs, str) or not logs:
                continue
            offset = self._auto_stream_entry_offsets.get(normalized_id, 0)
            if offset < 0 or offset > len(logs):
                offset = 0
            new_chunk = logs[offset:]
            self._auto_stream_entry_offsets[normalized_id] = len(logs)
            if not new_chunk:
                continue
            for line in new_chunk.splitlines():
                if not self._is_active_auto_stream_target(task_id):
                    return
                rendered = True
                await self._render_auto_log_line(line)
        if rendered:
            self._auto_stream_wait_noted = False
            self._auto_stream_idle_noted = False
            self._set_auto_stream_poll_interval(self._AUTO_STREAM_POLL_FAST_SECONDS)
        else:
            self._set_auto_stream_poll_interval(self._AUTO_STREAM_POLL_MEDIUM_SECONDS)

    async def _render_auto_log_line(self, log_line: str) -> None:
        normalized_line = log_line.strip()
        if not normalized_line:
            return
        try:
            data = json.loads(normalized_line)
        except json.JSONDecodeError:
            await self.output.post_note(normalized_line, classes="info")
            return

        message_entries = data.get("messages", [])
        for msg in message_entries:
            msg_type = msg.get("type", "")
            if msg_type == MessageType.RESPONSE:
                content = msg.get("content", "")
                if content:
                    await self.output.post_response(content)
            elif msg_type == MessageType.THINKING:
                content = msg.get("content", "")
                if content:
                    await self.output.post_thought(content)
            elif msg_type == MessageType.TOOL_CALL or msg_type == MessageType.TOOL_CALL_UPDATE:
                with contextlib.suppress(Exception):
                    tool_call = AcpToolCall.model_validate(
                        {
                            "toolCallId": msg.get("id", "unknown"),
                            "title": msg.get("title", "Tool call"),
                            "kind": msg.get("kind") or None,
                            "status": msg.get("status") or None,
                            "content": msg.get("content"),
                            "rawInput": msg.get("raw_input"),
                            "rawOutput": msg.get("raw_output"),
                        }
                    )
                    await self.output.upsert_tool_call(tool_call)
            elif msg_type == MessageType.PLAN:
                plan_entries = msg.get("entries", [])
                if plan_entries:
                    await self.output.post_plan(plan_entries)
            elif msg_type == MessageType.AGENT_READY:
                await self.output.post_note("AUTO agent ready", classes="success")
            elif msg_type == MessageType.AGENT_FAIL:
                error_msg = msg.get("message", "Unknown error")
                friendly_message, remediation = normalize_agent_failure_for_ui(error_msg)
                await self.output.post_note(
                    f"AUTO run issue: {friendly_message}",
                    classes="warning",
                )
                if remediation:
                    await self.output.post_note(remediation, classes="info")
                self.notify(friendly_message, severity="warning")
                details = msg.get("details")
                if details:
                    await self.output.post_note(details)

        if not message_entries:
            response_text = data.get("response_text", "")
            if response_text:
                await self.output.post_response(response_text)

    def _interaction_verbosity(self) -> str:
        config = getattr(self.app, "config", None)
        general = getattr(config, "general", None)
        configured = getattr(general, "interaction_verbosity", None)
        return normalize_interaction_verbosity(configured)

    def _ready_hint(self, target: ChatTarget | None = None) -> str:
        verbosity = self._interaction_verbosity()
        base_hint = "Ctrl+K sessions · Tab cycle · /help"
        if verbosity == "tldr":
            base_hint = "Ctrl+K · Tab · /help"
        elif verbosity == "technical":
            base_hint = (
                "Ctrl+K sessions · Tab linear in task scope · Ctrl+P fullscreen · Ctrl+O docked · "
                "/help lists commands · /mode <id> switches mode"
            )

        if target is None:
            return base_hint
        if target.kind is ChatTargetKind.ORCHESTRATOR:
            return base_hint
        if target.kind is ChatTargetKind.REVIEW:
            return f"Pinned to REVIEW · {target.label} · {base_hint}"
        return f"{target.label} · {base_hint}"

    async def _cycle_chat_target(self) -> None:
        await self._refresh_chat_targets()
        if not self._chat_targets:
            return
        if len(self._chat_targets) == 1:
            await self._open_session_picker()
            return
        pool = list(self._chat_targets) if self._target_scope_task_id else self._attention_targets()
        if not pool:
            return
        current_key = self._active_target().key
        pool_index = next(
            (index for index, target in enumerate(pool) if target.key == current_key),
            -1,
        )
        next_target = pool[(pool_index + 1) % len(pool)]
        await self._switch_active_target_by_key(next_target.key, notify=True)

    async def _open_session_picker(self) -> None:
        """Open grouped quick-pick palette for available chat sessions."""
        await self._refresh_chat_targets()
        contexts_by_id: dict[str, TaskContext] = dict(self._task_context_by_id)
        ctx = getattr(self.app, "ctx", None)
        project_id = getattr(ctx, "active_project_id", None) if ctx is not None else None
        if ctx is not None and project_id:
            for status in (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW):
                with contextlib.suppress(Exception):
                    tasks = await ctx.api.list_tasks(project_id=project_id, status=status)
                    for task in tasks or []:
                        task_context = self._task_context(task)
                        if task_context is None:
                            continue
                        contexts_by_id[task_context.task_id] = task_context
                        self._task_context_by_id[task_context.task_id] = task_context
        if (
            ctx is not None
            and self._target_scope_task_id
            and self._target_scope_task_id not in contexts_by_id
        ):
            with contextlib.suppress(Exception):
                scoped_task = await ctx.api.get_task(self._target_scope_task_id)
                scoped_context = (
                    self._task_context(scoped_task) if scoped_task is not None else None
                )
                if scoped_context is not None:
                    contexts_by_id[scoped_context.task_id] = scoped_context
                    self._task_context_by_id[scoped_context.task_id] = scoped_context

        from kagan.tui.ui.modals.session_picker import (
            SessionPickerGroup,
            SessionPickerModal,
            SessionPickerOption,
        )
        from kagan.tui.ui.screen_result import await_screen_result

        active_target = self._active_target()
        orchestrator_options = tuple(
            SessionPickerOption(
                key=target.key,
                icon=self._target_icon(target, None),
                label=target.label,
                search_text=(
                    f"{target.label} {self._parse_orchestrator_scope_from_key(target.key) or ''}"
                ),
            )
            for target in self._orchestrator_targets()
        )
        picker_groups: list[SessionPickerGroup] = []
        if orchestrator_options:
            picker_groups.append(
                SessionPickerGroup(
                    group_id="group:orchestrator",
                    icon="●",
                    label="Orchestrators",
                    subtitle=f"{len(orchestrator_options)} session(s)",
                    search_text="orchestrator sessions",
                    options=orchestrator_options,
                )
            )

        status_rank = {
            TaskStatus.IN_PROGRESS: 0,
            TaskStatus.REVIEW: 1,
        }
        sorted_contexts = sorted(
            contexts_by_id.values(),
            key=lambda item: (
                status_rank.get(item.status, 2),
                item.short_id.casefold(),
                item.title.casefold(),
            ),
        )
        for context in sorted_contexts:
            candidates = [
                candidate
                for candidate in self._scoped_targets_for_context(context)
                if candidate.kind is not ChatTargetKind.ORCHESTRATOR
            ]
            if not candidates:
                continue
            option_rows: list[SessionPickerOption] = []
            for candidate in candidates:
                role = self._target_role_label(candidate)
                option_rows.append(
                    SessionPickerOption(
                        key=candidate.key,
                        icon=self._target_icon(candidate, context),
                        label=f"{role} · {candidate.label}",
                        search_text=(
                            f"{candidate.key} {candidate.kind.value} {role} "
                            f"{context.task_id} {context.short_id} {context.title}"
                        ),
                    )
                )
            status_label = context.status.value if context.status is not None else "UNKNOWN"
            type_label = context.task_type.value if context.task_type is not None else "TASK"
            picker_groups.append(
                SessionPickerGroup(
                    group_id=f"group:{context.task_id}",
                    icon="▸",
                    label=f"#{context.short_id} · {context.title}",
                    subtitle=f"{type_label} · {status_label}",
                    search_text=(
                        f"{context.task_id} {context.short_id} {context.title} "
                        f"{status_label} {type_label}"
                    ),
                    options=tuple(option_rows),
                )
            )

        options_by_key: dict[str, SessionPickerOption] = {}
        for group in picker_groups:
            for option in group.options:
                options_by_key[option.key] = option

        recent_options: list[SessionPickerOption] = []
        for target_key in self._recent_target_keys:
            if target_key == active_target.key:
                continue
            option = options_by_key.get(target_key)
            if option is None:
                continue
            recent_options.append(option)
            if len(recent_options) >= self._RECENT_SESSION_LIMIT:
                break
        if recent_options:
            picker_groups.insert(
                0,
                SessionPickerGroup(
                    group_id="group:recent",
                    icon="↺",
                    label="Recent sessions",
                    subtitle=f"{len(recent_options)} recent",
                    search_text="recent sessions history mru",
                    options=tuple(recent_options),
                ),
            )

        selected_key = await await_screen_result(
            self.app,
            SessionPickerModal(groups=picker_groups, active_key=active_target.key),
        )
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-input", Input).focus()
        if not selected_key:
            return
        await self._switch_active_target_by_key(selected_key, notify=True)

    def _run_overlay_worker(
        self,
        work: object,
        *,
        group: str | None = None,
        exclusive: bool = False,
    ) -> None:
        normalized_work = work
        if inspect.iscoroutinefunction(work):
            normalized_work = work()
        elif callable(work) and not inspect.isawaitable(work):
            # Support callables that produce awaitables (for example lambda wrappers).
            async def _invoke_callable() -> None:
                result = work()
                if inspect.isawaitable(result):
                    await result

            normalized_work = _invoke_callable()
        try:
            self.run_worker(
                normalized_work,
                group=group,
                exclusive=exclusive,
                exit_on_error=False,
            )
        except Exception:
            if inspect.iscoroutine(normalized_work):
                with contextlib.suppress(Exception):
                    normalized_work.close()

    def _get_agent_stream(self) -> AgentStreamRouter:
        if self._agent_stream_router is None:
            self._agent_stream_router = AgentStreamRouter(
                get_output=lambda: self.output,
                show_output=self._show_output,
                on_update=self._handle_agent_update,
                on_thinking=self._handle_thinking,
                on_ready=self._handle_agent_ready,
                on_fail=self._handle_agent_fail,
                on_complete=self._handle_agent_complete,
                on_tool_call=self._handle_tool_call,
                on_request_permission=self._handle_request_permission,
                on_set_modes=self._handle_set_modes,
                on_mode_update=self._handle_mode_update,
                on_commands_update=self._handle_commands_update,
                ignore_fail=lambda _: self._clearing,
            )
        return self._agent_stream_router

    def _show_output(self) -> None:
        self.add_class("has-content")

    def _set_logo_variant(self, *, fullscreen: bool) -> None:
        """Update logo size for fullscreen vs popup overlay modes."""
        with contextlib.suppress(NoMatches):
            logo = self.query_one("#chat-overlay-logo", Static)
            logo.update(self._FULLSCREEN_LOGO if fullscreen else self._POPUP_LOGO)

    def _sync_overlay_mode_badge(self) -> None:
        with contextlib.suppress(NoMatches):
            badge = self.query_one("#chat-overlay-mode-badge", Static)
            if not self.has_class("visible"):
                badge.display = False
                return
            fullscreen = self.has_class("fullscreen")
            badge.display = True
            badge.update("Fullscreen" if fullscreen else "Docked")
            badge.set_class(fullscreen, "mode-fullscreen")
            badge.set_class(not fullscreen, "mode-docked")

    def _apply_overlay_mode_styles(self, *, fullscreen: bool) -> None:
        if fullscreen:
            self.styles.height = "1fr"
            self.styles.max_height = "1fr"
            self.styles.min_height = "0"
            return
        docked_height = 8
        estimate_docked = getattr(self.screen, "_estimated_docked_overlay_height", None)
        if callable(estimate_docked):
            with contextlib.suppress(Exception):
                estimated = int(estimate_docked())
                if estimated > 0:
                    docked_height = estimated
        self.styles.height = str(docked_height)
        self.styles.max_height = str(docked_height)
        self.styles.min_height = "3"

    def _sync_screen_overlay_visibility(self) -> None:
        """Reflect overlay visibility onto the owning screen for board chrome rules."""
        if self._embedded:
            return
        visible = self.has_class("visible")
        fullscreen = visible and self.has_class("fullscreen")
        state = (visible, fullscreen)
        if state == self._last_overlay_visibility_state:
            return
        self._last_overlay_visibility_state = state
        with contextlib.suppress(Exception):
            self.screen.set_class(visible, "chat-overlay-visible")
            overlay_visibility_changed = getattr(
                self.screen, "on_chat_overlay_visibility_changed", None
            )
            if callable(overlay_visibility_changed):
                # Sync immediately to avoid one-frame board/overlay desync on first open.
                overlay_visibility_changed(visible, fullscreen)
                self.screen.call_after_refresh(
                    overlay_visibility_changed,
                    visible,
                    fullscreen,
                )
                return
            sync_empty_placeholders = getattr(
                self.screen, "sync_empty_placeholders_for_overlay", None
            )
            if callable(sync_empty_placeholders):
                sync_empty_placeholders()
                self.screen.call_after_refresh(sync_empty_placeholders)

    def _capture_focus_return_target(self) -> None:
        if self._embedded:
            return
        self._focus_return_target = None
        get_focused_card = getattr(self.screen, "get_focused_card", None)
        if callable(get_focused_card):
            with contextlib.suppress(Exception):
                card = get_focused_card()
                if card is not None:
                    self._focus_return_target = card
                    return
        focused = getattr(self.app, "focused", None)
        if focused is not None and focused is not self:
            self._focus_return_target = focused

    def show_for_task(self, task: object, *, fullscreen: bool = False) -> None:
        """Show overlay scoped to the selected task context."""
        context = self._task_context(task)
        if context is not None:
            self._requested_task_context = context
            self._requested_task_id = context.task_id
            self._focused_task_context = context
            self.show(task_id=context.task_id, fullscreen=fullscreen)
            return
        self.show(fullscreen=fullscreen)

    def set_target_scope(self, task_id: str | None) -> None:
        """Restrict discoverable chat targets to a single task when provided."""
        normalized_task_id = str(task_id or "").strip() or None
        self._target_scope_task_id = normalized_task_id
        self._chat_targets_cache_key = None
        self._chat_targets_cache_at = 0.0
        if normalized_task_id is not None:
            self._requested_task_id = normalized_task_id
        if self.has_class("visible"):
            self._run_overlay_worker(
                self._refresh_chat_targets(force=True),
                group="chat-overlay-targets",
                exclusive=True,
            )

    def show(self, task_id: str | None = None, *, fullscreen: bool = False) -> None:
        """Show overlay and activate orchestrator session."""
        if task_id is not None:
            normalized_task_id = str(task_id).strip()
            self._requested_task_id = normalized_task_id or None
            self._chat_targets_cache_key = None
            self._chat_targets_cache_at = 0.0
        was_visible = self.has_class("visible")
        if was_visible and self.has_class("fullscreen") == fullscreen and task_id is None:
            with contextlib.suppress(NoMatches):
                self.query_one("#chat-overlay-input", Input).focus()
            return
        if not was_visible and not self._embedded:
            self._capture_focus_return_target()
        if not fullscreen:
            prepare_docked_overlay_open = getattr(
                self.screen,
                "prepare_for_docked_overlay_open",
                None,
            )
            if callable(prepare_docked_overlay_open):
                with contextlib.suppress(Exception):
                    prepare_docked_overlay_open()
        self.add_class("visible")
        if fullscreen:
            self.add_class("fullscreen")
            self.remove_class("docked")
        else:
            self.remove_class("fullscreen")
            self.add_class("docked")
        self._apply_overlay_mode_styles(fullscreen=fullscreen)
        self._set_logo_variant(fullscreen=fullscreen)
        self._sync_overlay_mode_badge()
        self._sync_screen_overlay_visibility()
        if not was_visible and not self.has_class("has-content"):
            self._refresh_intro_quote()
        if was_visible:
            with contextlib.suppress(NoMatches):
                self.query_one("#chat-overlay-input", Input).focus()
            if task_id is not None:
                self.call_after_refresh(
                    lambda: self._run_overlay_worker(
                        self._refresh_chat_targets(force=True),
                        group="chat-overlay-targets",
                        exclusive=True,
                    )
                )
            elif self._active_target().kind is ChatTargetKind.AUTO:
                self.call_after_refresh(
                    lambda: self._run_overlay_worker(
                        self._sync_active_target_session(),
                        group="chat-overlay-target-session",
                        exclusive=True,
                    )
                )
            return
        self.call_after_refresh(
            lambda: self._run_overlay_worker(
                self._activate,
                group="chat-overlay-activate",
                exclusive=True,
            )
        )

    def hide(self) -> None:
        """Hide overlay."""
        self.remove_class("visible")
        self.remove_class("fullscreen")
        self.remove_class("docked")
        self._sync_overlay_mode_badge()
        self._reset_auto_stream_state()
        self._sync_screen_overlay_visibility()
        if self._embedded:
            return
        target = self._focus_return_target
        self._focus_return_target = None
        if target is not None:
            with contextlib.suppress(Exception):
                self.screen.set_focus(target)
                return
        focus_first_card = getattr(self.screen, "focus_first_card", None)
        if callable(focus_first_card):
            with contextlib.suppress(Exception):
                focus_first_card()
                return
        self.screen.set_focus(None)

    def toggle(self, task_id: str | None = None, *, fullscreen: bool = False) -> bool:
        """Toggle visibility. Returns True if now visible."""
        if self.has_class("visible"):
            self.hide()
            return False
        self.show(task_id, fullscreen=fullscreen)
        return True

    def cycle_chat_session(self) -> None:
        """Cycle active chat session target when overlay is visible."""
        if not self.has_class("visible"):
            return
        self._run_overlay_worker(
            self._cycle_chat_target,
            group="chat-overlay-targets",
            exclusive=True,
        )

    def action_escape_overlay(self) -> None:
        self.handle_escape()

    def action_ctrl_c(self) -> None:
        self.handle_ctrl_c()

    def on_key(self, event: events.Key) -> None:
        if not self.has_class("visible"):
            return
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self._run_overlay_worker(
                self._cycle_chat_target,
                group="chat-overlay-targets",
                exclusive=True,
            )
            return
        if event.key == "ctrl+k":
            event.prevent_default()
            event.stop()
            self._run_overlay_worker(
                self._open_session_picker,
                group="chat-overlay-targets",
                exclusive=True,
            )
            return
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            if (
                event.key == "up"
                and self.app.focused is chat_input
                and not chat_input.value
                and self._last_submitted_prompt
            ):
                event.prevent_default()
                event.stop()
                chat_input.value = self._last_submitted_prompt
                self._sync_meta_chips(chat_input.value)
                return
            if self._slash_complete is not None and chat_input.value.startswith("/"):
                if event.key == "pageup":
                    event.prevent_default()
                    event.stop()
                    self._slash_complete.action_page_up()
                    return
                if event.key == "pagedown":
                    event.prevent_default()
                    event.stop()
                    self._slash_complete.action_page_down()
                    return
                if event.key == "home":
                    event.prevent_default()
                    event.stop()
                    self._slash_complete.action_first()
                    return
                if event.key == "end":
                    event.prevent_default()
                    event.stop()
                    self._slash_complete.action_last()
                    return
                if event.key == "up":
                    event.prevent_default()
                    event.stop()
                    self._slash_complete.action_cursor_up()
                    return
                if event.key == "down":
                    event.prevent_default()
                    event.stop()
                    self._slash_complete.action_cursor_down()
                    return
                if event.key == "enter":
                    event.prevent_default()
                    event.stop()
                    self._slash_complete.action_select()
                    return
                if event.key == "escape":
                    if self._embedded:
                        return
                    event.prevent_default()
                    event.stop()
                    chat_input.value = ""
                    self._run_overlay_worker(self._hide_slash_complete)
                    return
        if event.key == "escape":
            if self._embedded:
                return
            event.prevent_default()
            event.stop()
            self.action_escape_overlay()

    def _is_interruptible_stream_active(self) -> bool:
        with contextlib.suppress(NoMatches):
            if self.output.phase not in {StreamPhase.THINKING, StreamPhase.STREAMING}:
                return False

        target = self._active_target()
        if target.kind is ChatTargetKind.ORCHESTRATOR:
            return self.status_bar.status in {"initializing", "thinking"}

        if target.kind is ChatTargetKind.AUTO and target.task_id:
            if self._auto_stream_task_id != target.task_id:
                return False
            ctx = getattr(self.app, "ctx", None)
            if ctx is None:
                return False
            with contextlib.suppress(Exception):
                runtime_view = ctx.api.get_runtime_view(target.task_id)
                return bool(self._state_attr(runtime_view, "is_running", False))
        return False

    async def _interrupt_active_stream(self) -> None:
        target = self._active_target()
        runtime_task_id = await self._resolve_auto_runtime_task_id_for_target(target)
        if runtime_task_id:
            await self._execute_stop("")
            return
        await self._cancel_active_prompt()

    async def _handle_escape(self) -> None:
        if not self.has_class("visible"):
            return
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            if self._slash_complete is not None and chat_input.value.startswith("/"):
                if self._embedded:
                    return
                chat_input.value = ""
                await self._hide_slash_complete()
                return
        if self._embedded:
            return
        if self._is_interruptible_stream_active():
            await self._interrupt_active_stream()
            return
        self.hide()
        await self._cancel_active_prompt()

    async def _handle_ctrl_c(self) -> None:
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            chat_input.value = ""
            if self._active_input_target_key:
                self._drafts_by_target_key[self._active_input_target_key] = ""
            chat_input.focus()
        self._sync_meta_chips("")
        await self._hide_slash_complete()

    def handle_escape(self) -> None:
        """Dismiss popup first, interrupt active stream, otherwise close overlay."""
        self._run_overlay_worker(
            self._handle_escape(),
            group="chat-overlay-escape",
            exclusive=True,
        )

    def handle_ctrl_c(self) -> None:
        """Clear chat input and keep running stream state unchanged."""
        self._run_overlay_worker(
            self._handle_ctrl_c(),
            group="chat-overlay-clear-input",
            exclusive=True,
        )

    @on(Input.Submitted, "#chat-overlay-input")
    async def _on_input_submitted(self, event: Input.Submitted) -> None:
        if self._session_switch_in_flight > 0:
            event.control.value = ""
            self._sync_meta_chips("")
            return
        text = event.value.strip()
        if text:
            self._last_submitted_prompt = text
        event.control.value = ""
        if self._active_input_target_key:
            self._drafts_by_target_key[self._active_input_target_key] = ""
        self._sync_meta_chips("")
        if not text:
            await self._hide_slash_complete()
            return
        if slash_call := parse_slash_command_call(text):
            handled = await self._execute_slash_command(slash_call.name, slash_call.args)
            await self._hide_slash_complete()
            if handled:
                return
        self._run_overlay_worker(
            self._send_message(text),
            group="chat-overlay-send",
            exclusive=True,
        )

    @on(Input.Changed, "#chat-overlay-input")
    async def _on_input_changed(self, event: Input.Changed) -> None:
        if self._session_switch_in_flight > 0:
            return
        if self._active_input_target_key:
            self._drafts_by_target_key[self._active_input_target_key] = event.value
        self._sync_meta_chips(event.value)
        await self._check_slash_trigger(event.value)

    @on(Select.Changed, "#chat-overlay-session-select")
    async def _on_session_select_changed(self, event: Select.Changed) -> None:
        if self._session_switch_in_flight > 0:
            return
        if self._synchronizing_session_selector:
            return
        if not bool(event.control.display):
            return
        if self.app.focused is not event.control:
            return
        selected_key = event.value
        if selected_key is Select.BLANK or not isinstance(selected_key, str):
            return
        if selected_key == self._active_target().key:
            return
        await self._switch_active_target_by_key(selected_key, notify=True)

    @on(SlashComplete.Completed)
    async def _on_slash_completed(self, event: SlashComplete.Completed) -> None:
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            chat_input.value = ""
        await self._hide_slash_complete()
        await self._execute_slash_command(event.command, "")
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-input", Input).focus()

    @on(SlashComplete.Dismissed)
    async def _on_slash_dismissed(self, _event: SlashComplete.Dismissed) -> None:
        await self._hide_slash_complete()
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-input", Input).focus()

    async def _activate(self) -> None:
        self._update_status("ready", self._ready_hint(self._active_target()))
        self.query_one("#chat-overlay-input", Input).focus()
        await self._ensure_agent()
        await self._refresh_chat_targets()
        self._sync_mode_chip_ui()
        self._sync_meta_chips()
        if self._auto_skill_discovery_enabled() and not self._skills_loaded:
            self._run_overlay_worker(
                self._discover_local_skills_async(),
                group="chat-overlay-skill-discovery",
                exclusive=True,
            )

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return
        app = self.app
        project_root = Path(getattr(app, "project_root", Path.cwd()))
        config = getattr(app, "config", None)
        if config is None:
            return
        agent_config = config.get_worker_agent() or get_fallback_agent_config()
        agent = self._agent_factory(project_root, agent_config, read_only=False)
        maybe_set_external_session_scope = getattr(agent, "set_external_session_scope", None)
        if callable(maybe_set_external_session_scope):
            maybe_set_external_session_scope(self._active_orchestrator_session_scope_id)
        auto_approve = resolve_auto_approve(
            scope=AgentPermissionScope.ORCHESTRATOR,
            planner_auto_approve=config.general.auto_approve,
        )
        agent.set_auto_approve(auto_approve)
        agent.start(self)
        self._agent = agent
        try:
            await agent.wait_ready(timeout=30.0)
        except TimeoutError:
            self.notify("Agent did not become ready within 30s", severity="warning")

    async def _send_message(self, text: str) -> None:
        self._show_output()
        output = self.output
        output.reset_turn()
        await output.post_user_input(text)
        target = self._active_target()
        if target.kind is ChatTargetKind.ORCHESTRATOR:
            await self._send_orchestrator_message(text)
            return
        if target.kind is ChatTargetKind.AUTO:
            await self._send_auto_follow_up(target, text)
            return
        if target.kind is ChatTargetKind.REVIEW:
            await self._send_review_follow_up(target, text)
            return
        await self._send_orchestrator_message(text)

    def _resolve_orchestrator_persona(self, target: ChatTarget) -> str | None:
        config = getattr(self.app, "config", None)
        if config is None:
            return None
        general = getattr(config, "general", None)
        if general is None:
            return None

        context = self._focused_task_context
        reviewer_persona = getattr(general, "pr_reviewer_persona", None)
        worker_persona = getattr(general, "worker_persona", None)
        orchestrator_persona = getattr(general, "orchestrator_persona", None)

        if target.kind is ChatTargetKind.REVIEW or (
            context is not None and context.status is TaskStatus.REVIEW
        ):
            if isinstance(reviewer_persona, str) and reviewer_persona.strip():
                return reviewer_persona

        if context is not None and isinstance(worker_persona, str) and worker_persona.strip():
            return worker_persona

        if isinstance(orchestrator_persona, str) and orchestrator_persona.strip():
            return orchestrator_persona
        return None

    def _orchestrator_history_for_target_key(self, target_key: str) -> list[tuple[str, str]]:
        history = self._conversation_history_by_target_key.get(target_key)
        if history is None:
            history = []
            self._conversation_history_by_target_key[target_key] = history
        return history

    async def _send_orchestrator_message(self, text: str) -> None:
        self._cancel_requested = False
        try:
            self._set_chat_input_disabled(True)
            establishing_connection = self._agent is None
            if establishing_connection:
                await self.output.post_thinking_indicator(label="Initializing...")
                self._update_status("initializing", "Establishing orchestrator connection…")
            else:
                await self.output.post_thinking_indicator()
                self._update_status("thinking", "Waiting for orchestrator response…")
            await self._ensure_agent()
            if self._agent is None:
                await self.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
                self._update_status("error", "Orchestrator agent unavailable")
                self.notify("Orchestrator agent unavailable", severity="error")
                return
            if establishing_connection:
                await self.output.post_thinking_indicator()
                self._update_status("thinking", "Waiting for orchestrator response…")
            active_target = self._active_target()
            orchestrator_persona = self._resolve_orchestrator_persona(active_target)
            target_key = (
                active_target.key
                if active_target.kind is ChatTargetKind.ORCHESTRATOR
                else self._active_orchestrator_target_key()
            )
            conversation_history = self._orchestrator_history_for_target_key(target_key)
            conversation_history.append(("user", text))
            snapshot_for_next_prompt = self._pending_compact_snapshot_by_target_key.get(target_key)
            prompt = build_orchestrator_prompt(
                text,
                conversation_history=conversation_history[:-1],
                session_snapshot=snapshot_for_next_prompt,
                persona=orchestrator_persona,
            )
            try:
                async with asyncio.timeout(self._ORCHESTRATOR_PROMPT_TIMEOUT_SECONDS):
                    await self._agent.send_prompt(prompt)
                response_text = self._agent.get_response_text()
                if response_text:
                    conversation_history.append(("assistant", response_text))
                self._pending_compact_snapshot_by_target_key.pop(target_key, None)
                self._cancel_requested = False
                # Defensive fallback when no lifecycle update arrived:
                # leave thinking state explicitly.
                if self.status_bar.status in {"initializing", "thinking"}:
                    await self.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
                    self._update_status("ready", self._ready_hint(self._active_target()))
            except TimeoutError:
                await self.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
                self._update_status("error", "Orchestrator response timed out")
                self.notify(
                    "Orchestrator response timed out while waiting for completion",
                    severity="error",
                )
                with contextlib.suppress(Exception):
                    await self._cancel_active_prompt()
            except Exception as exc:  # pragma: no cover
                await self.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
                if self._cancel_requested:
                    self._cancel_requested = False
                    self._update_status("ready", self._ready_hint(self._active_target()))
                    return
                self._update_status("error", "Failed to send orchestrator prompt")
                self.notify(f"Send failed: {exc}", severity="error")
        finally:
            self._set_chat_input_disabled(False)

    async def _cancel_active_prompt(self) -> None:
        if self._agent is None:
            return
        self._cancel_requested = True
        with contextlib.suppress(Exception):
            await self._agent.cancel()

    def _build_compact_snapshot(self) -> str:
        return self._stream_coordinator.build_compact_snapshot()

    def _snapshot_preview(self, snapshot: str) -> str:
        return snapshot_preview(snapshot, max_chars=self._COMPACT_PREVIEW_MAX_CHARS)

    async def _send_auto_follow_up(self, target: ChatTarget, text: str) -> None:
        task_id = target.task_id
        if not task_id:
            self.notify("AUTO target unavailable", severity="warning")
            return
        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            self.notify("App not initialized", severity="error")
            return
        try:
            payload = self._build_auto_follow_up_payload(text)
            await ctx.api.queue_message(
                task_id,
                payload,
                lane="implementation",
                author="orchestrator-overlay",
                metadata={
                    "source": "chat_overlay",
                    "target": "auto",
                },
            )
            submitted = await ctx.api.submit_job(task_id, "start_agent")
            terminal = await ctx.api.wait_job(
                submitted.job_id,
                task_id=task_id,
                timeout_seconds=0.6,
            )
            payload_result = job_result_payload(terminal)
            if terminal is not None and terminal.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
                await self.output.post_note(
                    "Queued follow-up accepted, but worker restart failed: "
                    + job_message(terminal, "Unknown restart failure"),
                    classes="warning",
                )
                return
            if payload_result is None:
                await self.output.post_note(
                    "Queued follow-up accepted. Worker restart requested; waiting for scheduler.",
                    classes="info",
                )
                return
            if not bool(payload_result.get("success", False)):
                await self.output.post_note(
                    "Queued follow-up accepted, but restart reported failure: "
                    + job_message(terminal, "Worker restart failed"),
                    classes="warning",
                )
                return
            await self.output.post_note(
                "Follow-up queued. Worker restart requested with user-priority context.",
                classes="success",
            )
        finally:
            self._run_overlay_worker(
                self._sync_active_target_session(),
                group="chat-overlay-target-session",
                exclusive=True,
            )

    async def _send_review_follow_up(self, target: ChatTarget, text: str) -> None:
        task_id = target.task_id
        if not task_id:
            self.notify("REVIEW target unavailable", severity="warning")
            return
        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            self.notify("App not initialized", severity="error")
            return
        payload = self._build_review_follow_up_payload(text)
        await ctx.api.queue_message(
            task_id,
            payload,
            lane="review",
            author="orchestrator-overlay",
            metadata={
                "source": "chat_overlay",
                "target": "review",
            },
        )
        await self.output.post_note(
            "Review follow-up queued. Open the task review stream to process queued feedback.",
            classes="success",
        )

    async def _resolve_auto_runtime_task_id_for_target(self, target: ChatTarget) -> str | None:
        task_id = str(target.task_id or "").strip()
        if not task_id:
            return None
        if target.kind is ChatTargetKind.AUTO:
            return task_id
        if target.kind is not ChatTargetKind.REVIEW:
            return None

        context = self._task_context_by_id.get(task_id)
        if context is None:
            ctx = getattr(self.app, "ctx", None)
            if ctx is not None:
                with contextlib.suppress(Exception):
                    task = await ctx.api.get_task(task_id)
                    context = self._task_context(task) if task is not None else None
                    if context is not None:
                        self._task_context_by_id[task_id] = context
        if context is not None and context.task_type is TaskType.AUTO:
            return task_id
        return None

    async def _resolve_active_auto_runtime_target(
        self, *, command_name: str
    ) -> tuple[str, ChatTarget] | None:
        target = self._active_target()
        runtime_task_id = await self._resolve_auto_runtime_task_id_for_target(target)
        if not runtime_task_id:
            self.notify(
                f"/{command_name} is available only for AUTO runtime tasks",
                severity="warning",
            )
            return None
        if target.kind is ChatTargetKind.AUTO and target.task_id == runtime_task_id:
            return runtime_task_id, target
        return runtime_task_id, ChatTarget(
            key=f"{ChatTargetKind.AUTO.value}:{runtime_task_id}",
            kind=ChatTargetKind.AUTO,
            label=target.label,
            task_id=runtime_task_id,
        )

    def _build_auto_follow_up_payload(self, text: str) -> str:
        return build_auto_follow_up_payload(text)

    @staticmethod
    def _build_review_follow_up_payload(text: str) -> str:
        return build_review_follow_up_payload(text)

    @on(messages.AgentMessage)
    async def _on_agent_message(self, message: messages.AgentMessage) -> None:
        """Route ACP agent messages to stream router."""
        await self._stream_coordinator.on_agent_message(message)

    async def _handle_agent_update(self, msg: messages.AgentUpdate) -> None:
        await self._stream_coordinator.handle_agent_update(msg)

    async def _handle_thinking(self, msg: messages.Thinking) -> None:
        await self._stream_coordinator.handle_thinking(msg)

    async def _handle_agent_ready(self, _msg: messages.AgentReady) -> None:
        await self._stream_coordinator.handle_agent_ready()

    async def _handle_agent_complete(self, _msg: messages.AgentComplete) -> None:
        await self.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
        self._update_status("ready", self._ready_hint(self._active_target()))

    async def _handle_agent_fail(self, msg: messages.AgentFail) -> None:
        await self.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
        if is_graceful_agent_termination(msg.message):
            self._update_status("ready", "Agent stream ended (cancelled)")
            await self.output.post_note(
                "Agent stream ended by cancellation (SIGTERM).",
                classes="dismissed",
            )
            return
        friendly_message, remediation = normalize_agent_failure_for_ui(msg.message)
        self._update_status("error", friendly_message)
        await self.output.post_note(friendly_message, classes="warning")
        if remediation:
            await self.output.post_note(remediation, classes="info")
        if msg.details:
            await self.output.post_note(msg.details)
        self.notify(friendly_message, severity="warning")

    async def _handle_tool_call(self, msg: messages.ToolCall) -> None:
        """Intercept plan_tasks/plan_submit to show approval widget; else default."""
        await self._stream_coordinator.handle_tool_call(msg)

    async def _handle_request_permission(self, msg: messages.RequestPermission) -> None:
        await self.output.post_permission_request(
            msg.options,
            msg.tool_call,
            msg.result_future,
            timeout=300.0,
        )

    def _handle_set_modes(self, msg: messages.SetModes) -> None:
        self._current_mode = msg.current_mode
        self._available_modes = msg.modes
        self._sync_mode_chip_ui()
        self._sync_meta_chips()
        # Default PAIR task sessions to execute mode since task context is already defined.
        # Ask and Plan modes add unnecessary friction when the user is actively collaborating.
        self._apply_pair_mode_default()

    def _handle_mode_update(self, msg: messages.ModeUpdate) -> None:
        self._current_mode = msg.current_mode
        self._sync_mode_chip_ui()
        self._sync_meta_chips()

    def _handle_commands_update(self, msg: messages.AvailableCommandsUpdate) -> None:
        self._available_commands = [
            command for command in msg.commands if not self._is_suppressed_agent_command(command)
        ]
        self._refresh_slash_complete_commands()

    def _register_slash_commands(self) -> None:
        @self._slash_registry.command()
        async def clear(args: str) -> None:
            """Clear active chat session (`/clear all sessions` resets all sessions)."""
            await self._execute_clear_command(args)

        @self._slash_registry.command()
        async def new(args: str) -> None:
            """Create a new orchestrator session (`/new session`)."""
            await self._execute_new(args)

        @self._slash_registry.command()
        async def close(args: str) -> None:
            """Close active orchestrator session (`/close session`)."""
            await self._execute_close(args)

        @self._slash_registry.command()
        async def compact(args: str) -> None:
            """Compact context (native agent compaction when available)."""
            await self._execute_compact(args)

        @self._slash_registry.command()
        async def export(args: str) -> None:
            """Export active session transcript to clipboard (`/export`)."""
            await self._execute_export(args)

        @self._slash_registry.command()
        async def restart(args: str) -> None:
            """Restart active AUTO runtime (`/restart` or `/restart <extra context>`)."""
            await self._execute_restart(args)

        @self._slash_registry.command()
        async def stop(args: str) -> None:
            """Stop active AUTO runtime (`/stop`)."""
            await self._execute_stop(args)

        @self._slash_registry.command()
        async def help(_args: str) -> None:
            await self._execute_help()

        @self._slash_registry.command()
        async def mode(args: str) -> None:
            await self._execute_mode(args)

        @self._slash_registry.command()
        async def sessions(args: str) -> None:
            """Open the session quick-pick (`/sessions`)."""
            await self._execute_sessions(args)

        @self._slash_registry.command()
        async def agent(args: str) -> None:
            """Run grouped agent commands (`/agent <command> [args]`)."""
            await self._execute_agent_group(args)

    async def _execute_slash_command(self, command_name: str, args: str) -> bool:
        normalized_command = command_name.strip().lower()
        if self._is_removed_command_name(command_name):
            self._show_output()
            await self.output.post_note(
                f"`/{command_name}` is not available in Kagan TUI.",
                classes="warning",
            )
            return True
        local_command = self._slash_registry.find_command(normalized_command)
        if local_command is not None:
            result = local_command.func(args)
            if asyncio.iscoroutine(result):
                await result
            return True
        if normalized_command in {"attach", "browse", "target", "targets", "skill", "skills"}:
            self.notify(
                "This command was removed. Use `/sessions` or `/agent <command>`.",
                severity="warning",
            )
            return True
        if self._find_agent_command(normalized_command) is not None:
            self.notify(
                f"Use `/{self._AGENT_COMMAND_GROUP} {normalized_command}` for agent commands.",
                severity="warning",
            )
            return True
        return False

    @staticmethod
    def _normalize_command_args(args: str) -> str:
        return " ".join(args.strip().lower().split())

    async def _execute_clear_command(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if not normalized:
            await self._execute_clear(notification="Conversation cleared")
            return
        if normalized in {"session"}:
            await self._execute_clear(notification="Conversation cleared")
            return
        if normalized in {"all", "sessions", "all session", "all sessions"}:
            await self._execute_clear_all_sessions()
            return
        self.notify("Usage: /clear [session] or /clear all sessions", severity="warning")

    async def _execute_new(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if normalized not in {"", "session", "orchestrator", "orchestrator session"}:
            self.notify("Usage: /new session", severity="warning")
            return
        new_scope = self._create_orchestrator_session()
        await self._switch_active_target_by_key(
            self._orchestrator_target_key(new_scope),
            notify=False,
        )
        self.notify("Started new orchestrator session", severity="information")

    async def _execute_close(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if normalized not in {"", "session", "orchestrator", "orchestrator session"}:
            self.notify("Usage: /close session", severity="warning")
            return
        target = self._active_target()
        if target.kind is not ChatTargetKind.ORCHESTRATOR:
            self.notify(
                "/close session is available only for orchestrator sessions",
                severity="warning",
            )
            return
        active_scope = self._parse_orchestrator_scope_from_key(target.key)
        if active_scope is None:
            active_scope = self._active_orchestrator_session_scope_id

        if len(self._orchestrator_session_scope_ids) <= 1:
            await self._execute_clear(notification=None)
            self.notify("Cleared active orchestrator session", severity="information")
            return

        next_scope = next(
            (
                scope_id
                for scope_id in self._orchestrator_session_scope_ids
                if scope_id != active_scope
            ),
            None,
        )
        removed = self._remove_orchestrator_session(active_scope)
        if not removed or next_scope is None:
            self.notify("Failed to close orchestrator session", severity="warning")
            return
        await self._switch_active_target_by_key(
            self._orchestrator_target_key(next_scope),
            notify=False,
        )
        self.notify("Closed orchestrator session", severity="information")

    async def _execute_export(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if normalized:
            self.notify("Usage: /export", severity="warning")
            return
        target = self._active_target()
        transcript = self.output.get_text_content().strip()
        if not transcript:
            self.notify("Nothing to export for the active session", severity="warning")
            return
        export_lines = [
            f"Session: {target.label}",
            f"Type: {target.kind.value}",
        ]
        if target.task_id:
            export_lines.append(f"Task: {target.task_id}")
        export_lines.append("")
        export_lines.append(transcript)
        copy_with_notification(
            self.app,
            "\n".join(export_lines),
            f"{target.kind.value.upper()} session transcript",
        )

    async def _execute_restart(self, args: str) -> None:
        resolved_target = await self._resolve_active_auto_runtime_target(command_name="restart")
        if resolved_target is None:
            return
        runtime_task_id, auto_target = resolved_target
        self._show_output()
        extra_context = args.strip()
        if extra_context:
            await self._send_auto_follow_up(auto_target, extra_context)
            return

        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            self.notify("App not initialized", severity="error")
            return

        submitted = await ctx.api.submit_job(runtime_task_id, "start_agent")
        terminal = await ctx.api.wait_job(
            submitted.job_id,
            task_id=runtime_task_id,
            timeout_seconds=0.6,
        )
        payload_result = job_result_payload(terminal)
        if terminal is not None and terminal.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
            await self.output.post_note(
                job_message(terminal, "Failed to restart AUTO run"),
                classes="warning",
            )
        elif payload_result is None:
            await self.output.post_note(
                "AUTO restart requested; waiting for scheduler.",
                classes="info",
            )
        elif not bool(payload_result.get("success", False)):
            await self.output.post_note(
                job_message(terminal, "Failed to restart AUTO run"),
                classes="warning",
            )
        else:
            await self.output.post_note("AUTO restart requested.", classes="success")
        self._run_overlay_worker(
            self._sync_active_target_session(),
            group="chat-overlay-target-session",
            exclusive=True,
        )

    async def _execute_stop(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if normalized:
            self.notify("Usage: /stop", severity="warning")
            return

        resolved_target = await self._resolve_active_auto_runtime_target(command_name="stop")
        if resolved_target is None:
            return
        runtime_task_id, _auto_target = resolved_target
        self._show_output()

        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            self.notify("App not initialized", severity="error")
            return

        submitted = await ctx.api.submit_job(runtime_task_id, "stop_agent")
        terminal = await ctx.api.wait_job(
            submitted.job_id,
            task_id=runtime_task_id,
            timeout_seconds=0.6,
        )
        payload_result = job_result_payload(terminal)
        if terminal is not None and terminal.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
            await self.output.post_note(
                job_message(terminal, "No running AUTO agent to stop"),
                classes="warning",
            )
        elif payload_result is None:
            await self.output.post_note(
                "AUTO stop requested; waiting for scheduler.",
                classes="info",
            )
        elif not bool(payload_result.get("success", False)):
            await self.output.post_note(
                job_message(terminal, "Failed to stop AUTO run"),
                classes="warning",
            )
        else:
            await self.output.post_note("AUTO stop requested.", classes="success")
        self._run_overlay_worker(
            self._sync_active_target_session(),
            group="chat-overlay-target-session",
            exclusive=True,
        )

    async def _execute_sessions(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if normalized:
            self.notify("Usage: /sessions", severity="warning")
            return
        self._run_overlay_worker(
            self._open_session_picker,
            group="chat-overlay-targets",
            exclusive=True,
        )

    async def _execute_agent_group(self, args: str) -> None:
        cleaned = args.strip()
        if not cleaned:
            await self._post_agent_group_help()
            return

        command_name, _, command_args = cleaned.partition(" ")
        normalized_command = command_name.strip().lower()
        if not normalized_command:
            await self._post_agent_group_help()
            return
        if normalized_command == "skills":
            await self._execute_skills(command_args)
            return
        handled = await self._execute_agent_slash_command(
            normalized_command,
            command_args,
            display_name=f"{self._AGENT_COMMAND_GROUP} {normalized_command}",
        )
        if handled:
            return
        self.notify(f"Unknown agent command: {normalized_command}", severity="warning")
        await self._post_agent_group_help()

    async def _post_agent_group_help(self) -> None:
        self._show_output()
        lines = [
            "**Agent Commands:**",
            "",
            "- `/agent skills [list|refresh]` - List discovered local skills.",
        ]
        for command in sorted(self._available_commands, key=lambda item: item.name.lower()):
            description = str(getattr(command, "description", "")).strip() or "No description"
            hint_suffix = ""
            input_hint = self._agent_input_hint(command)
            if input_hint:
                hint_suffix = f" (input: {input_hint})"
            lines.append(
                f"- `/{self._AGENT_COMMAND_GROUP} {command.name}` - {description}{hint_suffix}"
            )
        if len(lines) == 3:
            lines.append("- No ACP commands are currently available for this agent.")
        await self.output.post_note("\n".join(lines))

    async def _execute_agent_slash_command(
        self,
        command_name: str,
        args: str,
        *,
        display_name: str | None = None,
    ) -> bool:
        command = self._find_agent_command(command_name)
        if command is None:
            return False
        display_command = display_name or command_name
        hint = self._agent_input_hint(command)
        if hint and not args.strip():
            with contextlib.suppress(NoMatches):
                chat_input = self.query_one("#chat-overlay-input", Input)
                chat_input.value = f"/{display_command} "
                chat_input.focus()
            self.notify(f"/{display_command} expects input: {hint}", severity="warning")
            return True
        message = f"/{command_name}"
        display_message = f"/{display_command}"
        cleaned_args = args.strip()
        if cleaned_args:
            message = f"{message} {cleaned_args}"
            display_message = f"{display_message} {cleaned_args}"
        await self.output.post_user_input(display_message)
        self._show_output()
        await self._send_orchestrator_message(message)
        return True

    def _find_agent_command(self, command_name: str) -> AvailableCommand | None:
        normalized_command = command_name.strip().lower()
        for command in self._available_commands:
            if command.name.strip().lower() == normalized_command:
                return command
        return None

    def _is_suppressed_agent_command(self, command: AvailableCommand) -> bool:
        command_name = str(getattr(command, "name", "")).strip().lower()
        if not command_name:
            return False
        if self._is_removed_command_name(command_name):
            return True
        if command_name in self._SUPPRESSED_AGENT_COMMAND_NAMES:
            return True
        return "remotion" in command_name

    def _is_removed_command_name(self, command_name: str) -> bool:
        normalized = command_name.strip().lower().replace("_", "-")
        if normalized in self._REMOVED_SLASH_COMMAND_NAMES:
            return True
        return normalized.startswith("textual:")

    def _agent_input_hint(self, command: AvailableCommand) -> str:
        input_spec = getattr(command, "input", None)
        if input_spec is None:
            return ""
        root = getattr(input_spec, "root", None)
        if root is None:
            return ""
        hint = getattr(root, "hint", "")
        return hint.strip() if isinstance(hint, str) else ""

    def _slash_popup_commands(self) -> list[SlashCommand[ChatOverlaySlashHandler]]:
        return list(self._slash_registry.list_commands())

    @staticmethod
    def _slash_popup_query(text: str) -> str | None:
        if not text.startswith("/"):
            return None
        query = text[1:]
        if not query:
            return ""
        if query[0].isspace():
            return None
        if any(char.isspace() for char in query):
            return None
        return query

    async def _check_slash_trigger(self, text: str) -> None:
        if (query := self._slash_popup_query(text)) is not None:
            await self._show_slash_complete(query)
            return
        if self._slash_complete is not None:
            await self._hide_slash_complete()

    async def _show_slash_complete(self, query: str) -> None:
        if self._slash_complete is None:
            self._slash_complete = SlashComplete(id="slash-complete")
            self._slash_complete.slash_commands = self._slash_popup_commands()
            self._slash_complete.slash_query = query
            main = self.query_one("#chat-overlay-main", Container)
            chat_input = self.query_one("#chat-overlay-input", Input)
            await main.mount(self._slash_complete)
            chat_input.focus()
            return
        self._refresh_slash_complete_commands(query)

    async def _hide_slash_complete(self) -> None:
        if self._slash_complete is None:
            return
        await self._slash_complete.remove()
        self._slash_complete = None

    def _refresh_slash_complete_commands(self, query: str | None = None) -> None:
        if self._slash_complete is None:
            return
        if query is None:
            query = self._slash_complete.slash_query
        self._slash_complete.slash_commands = self._slash_popup_commands()
        self._slash_complete.slash_query = query

    async def _execute_clear(self, *, notification: str | None = "Conversation cleared") -> None:
        self._clearing = True
        active_target = self._active_target()
        active_target_key = active_target.key
        self._output_snapshot_by_target_key.pop(active_target_key, None)
        self._drafts_by_target_key.pop(active_target_key, None)
        if active_target.kind is ChatTargetKind.ORCHESTRATOR:
            self._conversation_history_by_target_key.pop(active_target_key, None)
            self._pending_compact_snapshot_by_target_key.pop(active_target_key, None)
        self.remove_class("has-content")
        self._refresh_intro_quote()
        await self.output.clear()
        if self._agent is not None:
            with contextlib.suppress(Exception):
                await self._agent.stop()
        self._agent = None
        await self._ensure_agent()
        self._clearing = False
        self._update_status("ready", self._ready_hint(self._active_target()))
        if notification:
            self.notify(notification, severity="information")

    async def _execute_clear_all_sessions(self) -> None:
        fresh_scope = self._reset_orchestrator_sessions()
        self._requested_task_id = None
        self._requested_task_context = None
        self._focused_task_context = None
        self._target_scope_task_id = None
        self._recent_target_keys.clear()
        self._drafts_by_target_key.clear()
        self._output_snapshot_by_target_key.clear()
        self._conversation_history_by_target_key.clear()
        self._pending_compact_snapshot_by_target_key.clear()
        self._chat_targets = [self._orchestrator_target(fresh_scope)]
        self._active_target_index = 0
        await self._execute_clear(notification=None)
        await self._refresh_chat_targets(force=True)
        self._sync_active_target_ui()
        self.notify("Cleared all overlay chat sessions", severity="information")

    def _supports_native_compact(self) -> bool:
        return self._find_agent_command("compact") is not None

    async def _execute_compact(self, args: str = "") -> None:
        cleaned_args = args.strip()
        if self._supports_native_compact():
            await self._execute_agent_slash_command("compact", cleaned_args)
            return
        self._show_output()
        snapshot = self._build_compact_snapshot()
        if not snapshot:
            await self.output.post_note(
                "Nothing to compact yet. Send at least one message first.",
                classes="info",
            )
            return
        if cleaned_args:
            await self.output.post_note(
                "Native `/compact <instructions>` is unavailable for this agent; "
                "using Kagan snapshot compaction fallback.",
                classes="info",
            )
        target = self._active_target()
        target_key = (
            target.key
            if target.kind is ChatTargetKind.ORCHESTRATOR
            else self._active_orchestrator_target_key()
        )
        self._pending_compact_snapshot_by_target_key[target_key] = snapshot
        self._conversation_history_by_target_key.pop(target_key, None)
        if self._agent is not None:
            with contextlib.suppress(Exception):
                await self._agent.stop()
        self._agent = None
        await self._ensure_agent()
        preview = self._snapshot_preview(snapshot)
        await self.output.post_note(
            "Compacted chat via Kagan snapshot fallback for the next fresh session prompt.\n\n"
            f"```text\n{preview}\n```",
            classes="success",
        )
        self._update_status("ready", self._ready_hint(self._active_target()))

    async def _execute_help(self) -> None:
        await self._slash_executor.execute_help()

    async def _execute_modes(self) -> None:
        self._show_output()
        if not self._available_modes:
            await self.output.post_note("No agent modes available.", classes="info")
            return
        lines = ["**Agent Modes:**", ""]
        for mode_id, mode in sorted(self._available_modes.items(), key=lambda item: item[0]):
            marker = " (current)" if mode_id == self._current_mode else ""
            description = f" - {mode.description}" if mode.description else ""
            lines.append(f"- `{mode_id}`{marker}: {mode.name}{description}")
        await self.output.post_note("\n".join(lines))

    async def _execute_mode(self, args: str) -> None:
        mode_id = args.strip()
        if not mode_id:
            await self._execute_modes()
            return
        if mode_id not in self._available_modes:
            self.notify(f"Unknown mode: {mode_id}", severity="warning")
            await self._execute_modes()
            return
        await self._ensure_agent()
        if self._agent is None or not hasattr(self._agent, "set_mode"):
            self.notify("Mode switching is unavailable for this agent", severity="warning")
            return
        error = await self._agent.set_mode(mode_id)  # type: ignore[attr-defined]
        if error:
            self.notify(f"Failed to set mode: {error}", severity="error")
            return
        self._current_mode = mode_id
        mode_name = self._available_modes[mode_id].name
        self._sync_mode_chip_ui()
        self._sync_meta_chips()
        await self.output.post_note(
            f"Switched mode to `{mode_id}` ({mode_name}).",
            classes="success",
        )

    async def _execute_skills(self, args: str) -> None:
        await self._slash_executor.execute_skills(args)

    async def _noop_slash_handler(self, _args: str) -> None:
        return

    @on(PlanApprovalWidget.Approved)
    async def _on_plan_approved(self, event: PlanApprovalWidget.Approved) -> None:
        tasks = event.tasks
        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            self.notify("App not initialized", severity="error")
            return
        project_id = ctx.active_project_id or ""
        if not project_id:
            self.notify("No active project", severity="error")
            return
        try:
            for task in tasks:
                await ctx.api.create_task(
                    task.title,
                    task.description or "",
                    project_id=project_id,
                    task_type=task.task_type,
                    priority=task.priority,
                    acceptance_criteria=task.acceptance_criteria or [],
                )
            self.notify(f"Created {len(tasks)} task(s)", severity="success")
            screen = self.screen
            if hasattr(screen, "prepare_for_orchestrator_return"):
                await screen.prepare_for_orchestrator_return()
        except Exception as exc:
            self.notify(f"Failed to create tasks: {exc}", severity="error")

    @on(PlanApprovalWidget.Dismissed)
    def _on_plan_dismissed(self) -> None:
        self.notify("Plan dismissed", severity="information")

    def _update_status(self, status: str, hint: str) -> None:
        with contextlib.suppress(NoMatches):
            self.status_bar.update_status(status, hint)
        self._sync_meta_chips()

    def _focus_chat_input(self) -> None:
        if self._session_switch_in_flight > 0:
            return
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            if chat_input.disabled or not self.has_class("visible"):
                return
            chat_input.focus()

    def _set_chat_input_disabled(self, disabled: bool) -> None:
        if disabled:
            self._chat_input_disable_depth += 1
        else:
            self._chat_input_disable_depth = max(0, self._chat_input_disable_depth - 1)
        is_disabled = self._chat_input_disable_depth > 0
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            chat_input.disabled = is_disabled
        if not is_disabled:
            self._focus_chat_input()
            self.call_after_refresh(self._focus_chat_input)

    async def on_unmount(self) -> None:
        self._cancel_session_switch_notification_timer()
        await self._hide_slash_complete()
        self._reset_auto_stream_state()
        if self._agent is not None:
            self._agent.set_message_target(None)
            with contextlib.suppress(Exception):
                await self._agent.stop()
        self._agent = None
        self._agent_stream_router = None


__all__ = ["ChatOverlay"]
