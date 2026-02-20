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
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from acp.schema import ToolCall as AcpToolCall
from textual import on
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.css.query import NoMatches
from textual.widgets import Input, Static

from kagan.core.acp import messages
from kagan.core.agents.agent_factory import AgentFactory, create_agent
from kagan.core.agents.orchestrator import build_orchestrator_prompt
from kagan.core.config import get_fallback_agent_config
from kagan.core.constants import BOX_DRAWING, KAGAN_LOGO, KAGAN_LOGO_SMALL
from kagan.core.domain.enums import ChatRole, MessageType, StreamPhase, TaskStatus, TaskType
from kagan.core.policy import AgentPermissionScope, resolve_auto_approve
from kagan.core.safety import (
    QUEUE_MESSAGE_MAX_CHARS,
    normalize_untrusted_text,
    redact_sensitive_text,
)
from kagan.core.services.jobs import JobStatus
from kagan.core.ux_text import normalize_interaction_verbosity
from kagan.tui.ui.utils.agent_stream_router import AgentStreamRouter
from kagan.tui.ui.utils.helpers import is_graceful_agent_termination
from kagan.tui.ui.utils.job_results import job_message, job_result_payload
from kagan.tui.ui.utils.slash_registry import (
    SlashCommand,
    SlashCommandRegistry,
    parse_slash_command_call,
)
from kagan.tui.ui.widgets.plan_approval import PlanApprovalWidget
from kagan.tui.ui.widgets.slash_complete import SlashComplete
from kagan.tui.ui.widgets.status_bar import StatusBar
from kagan.tui.ui.widgets.streaming_output import StreamingOutput
from kagan.tui.ui.widgets.chat_overlay_collaborators import (
    ChatOverlaySlashCommandExecutor,
    ChatOverlayStreamCoordinator,
    ChatOverlayTargetManager,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from acp.schema import AvailableCommand
    from textual import events
    from textual.app import ComposeResult
    from textual.widget import Widget

    from kagan.core.acp import Agent

type ChatOverlaySlashHandler = Callable[[str], None | Awaitable[None]]


class ChatTargetKind(StrEnum):
    ORCHESTRATOR = "orchestrator"
    AUTO = "auto"
    PAIR = "pair"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ChatTarget:
    key: str
    kind: ChatTargetKind
    label: str
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class TaskContext:
    task_id: str
    short_id: str
    title: str
    task_type: TaskType | None
    status: TaskStatus | None


@dataclass(frozen=True, slots=True)
class DiscoveredSkill:
    name: str
    description: str
    location: Path
    source_root: Path


class ChatOverlay(Vertical):
    """Orchestrator overlay with fullscreen default and mode cycling support."""

    BINDINGS: list[BindingType] = [
        Binding("escape", "escape_overlay", show=False, priority=True),
        Binding("ctrl+c", "ctrl_c", show=False, priority=True),
    ]

    _ORCHESTRATOR_PROMPT_TIMEOUT_SECONDS = 300.0
    _CTRL_C_DOUBLE_PRESS_WINDOW_SECONDS = 0.8
    _INTRO_HEADING = "🎯 Orchestrate Your Work"
    _INTRO_QUOTE_PROBABILITY = 0.35
    _INTRO_QUOTES: tuple[tuple[str, str], ...] = (
        ("Funny", "A clean backlog is just organized optimism."),
        ("Funny", "If the plan survives Monday, it is probably production-ready."),
        ("Funny", "Ship small, celebrate often, and blame the cache last."),
        ("Wise", "Clear scope today beats heroic rewrites tomorrow."),
        ("Wise", "Momentum comes from finishing the next smallest thing."),
        ("Wise", "Good systems reward honesty about tradeoffs."),
    )
    _EXAMPLES: tuple[str, ...] = (
        '"Plan a rollout for GitHub issue sync in this repo"',
        '"Break this feature into AUTO and PAIR tasks"',
        '"Draft acceptance criteria for the current milestone"',
    )
    _FULLSCREEN_LOGO = KAGAN_LOGO
    _POPUP_LOGO = KAGAN_LOGO_SMALL
    _COMPACT_MAX_HISTORY_ITEMS = 24
    _COMPACT_ENTRY_MAX_CHARS = 600
    _COMPACT_SNAPSHOT_MAX_CHARS = 8_000
    _COMPACT_PREVIEW_MAX_CHARS = 1_200
    _SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
    _SKILL_METADATA_MAX_BYTES = 16_384
    _SKILL_DESCRIPTION_MAX_CHARS = 220
    _SKILL_DISCOVERY_MAX_FILES = 256
    _SKILL_DISCOVERY_DISPLAY_LIMIT = 60
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
        self._conversation_history: list[tuple[str, str]] = []
        self._clearing: bool = False
        self._current_mode: str = ""
        self._available_modes: dict[str, messages.Mode] = {}
        self._available_commands: list[AvailableCommand] = []
        self._slash_complete: SlashComplete | None = None
        self._slash_registry: SlashCommandRegistry[ChatOverlaySlashHandler] = SlashCommandRegistry()
        self._chat_targets: list[ChatTarget] = [self._orchestrator_target()]
        self._active_target_index: int = 0
        self._task_context_by_id: dict[str, TaskContext] = {}
        self._requested_task_id: str | None = None
        self._requested_task_context: TaskContext | None = None
        self._focused_task_context: TaskContext | None = None
        self._focus_return_target: Widget | None = None
        self._agent_stream_router: AgentStreamRouter | None = None
        self._pending_compact_snapshot: str | None = None
        self._cancel_requested: bool = False
        self._discovered_skills: list[DiscoveredSkill] = []
        self._skills_loaded: bool = False
        self._auto_stream_task_id: str | None = None
        self._auto_stream_execution_id: str | None = None
        self._auto_stream_entry_ids: set[str] = set()
        self._auto_stream_wait_noted: bool = False
        self._auto_stream_idle_noted: bool = False
        self._last_ctrl_c_press_at: float | None = None
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
                                "Describe what you want to build or accomplish.\n"
                                "Kagan can plan tasks, manage execution, and guide review.",
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
                yield Input(
                    placeholder=(
                        "Describe your task... "
                        "(/ for commands, Ctrl+C clears input; Ctrl+C Ctrl+C stops stream)"
                    ),
                    id="chat-overlay-input",
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

    @staticmethod
    def _trusted_skill_roots(project_root: Path) -> list[Path]:
        home = Path.home()
        candidates = [
            project_root / ".agents" / "skills",
            project_root / ".pi" / "skills",
            project_root / ".claude" / "skills",
            home / ".agents" / "skills",
            home / ".pi" / "skills",
            home / ".claude" / "skills",
            home / ".codex" / "skills",
            home / ".vtcode" / "skills",
        ]
        roots: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.expanduser().resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            roots.append(resolved)
        return roots

    @staticmethod
    def _path_within_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @classmethod
    def _normalize_skill_description(cls, raw: str) -> str:
        normalized = normalize_untrusted_text(raw, max_chars=cls._SKILL_DESCRIPTION_MAX_CHARS)
        redacted = redact_sensitive_text(normalized, redact_pii=True)
        return " ".join(redacted.split())

    @staticmethod
    def _parse_skill_frontmatter(text: str) -> dict[str, str]:
        content = text.lstrip("\ufeff")
        if not content.startswith("---\n"):
            return {}
        terminator = "\n---"
        end_index = content.find(terminator, 4)
        if end_index == -1:
            return {}
        frontmatter = content[4:end_index]
        metadata: dict[str, str] = {}
        for line in frontmatter.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            normalized_key = key.strip().lower()
            if normalized_key not in {"name", "description"}:
                continue
            cleaned_value = value.strip().strip('"').strip("'")
            if cleaned_value:
                metadata[normalized_key] = cleaned_value
        return metadata

    @classmethod
    def _extract_skill_metadata(cls, skill_file: Path, *, root: Path) -> DiscoveredSkill | None:
        resolved_file = skill_file.resolve(strict=False)
        if not cls._path_within_root(resolved_file, root):
            return None
        if resolved_file.name != "SKILL.md":
            return None
        try:
            with resolved_file.open("rb") as handle:
                raw = handle.read(cls._SKILL_METADATA_MAX_BYTES)
        except OSError:
            return None

        metadata = cls._parse_skill_frontmatter(raw.decode("utf-8", "replace"))
        skill_name = metadata.get("name", "").strip().lower()
        if not skill_name:
            skill_name = resolved_file.parent.name.strip().lower()
        if not cls._SKILL_NAME_PATTERN.fullmatch(skill_name):
            return None
        description = cls._normalize_skill_description(metadata.get("description", ""))
        return DiscoveredSkill(
            name=skill_name,
            description=description,
            location=resolved_file,
            source_root=root,
        )

    @classmethod
    def _discover_local_skills_for_roots(cls, roots: list[Path]) -> list[DiscoveredSkill]:
        discovered: dict[str, DiscoveredSkill] = {}
        scanned_files = 0
        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            try:
                candidates = sorted(root.rglob("SKILL.md"))
            except OSError:
                continue
            for skill_file in candidates:
                scanned_files += 1
                if scanned_files > cls._SKILL_DISCOVERY_MAX_FILES:
                    break
                discovered_skill = cls._extract_skill_metadata(skill_file, root=root)
                if discovered_skill is None:
                    continue
                if discovered_skill.name not in discovered:
                    discovered[discovered_skill.name] = discovered_skill
            if scanned_files > cls._SKILL_DISCOVERY_MAX_FILES:
                break
        return sorted(discovered.values(), key=lambda item: item.name)

    def _discover_local_skills(self, *, force_refresh: bool = False) -> list[DiscoveredSkill]:
        if not self._auto_skill_discovery_enabled():
            self._discovered_skills = []
            self._skills_loaded = False
            return []
        if self._skills_loaded and not force_refresh:
            return list(self._discovered_skills)
        project_root = Path.cwd()
        with contextlib.suppress(Exception):
            project_root = Path(getattr(self.app, "project_root", project_root))
        roots = self._trusted_skill_roots(project_root)
        self._discovered_skills = self._discover_local_skills_for_roots(roots)
        self._skills_loaded = True
        return list(self._discovered_skills)

    @staticmethod
    def _task_value(task: object, key: str) -> object:
        if isinstance(task, dict):
            return task.get(key)
        return getattr(task, key, None)

    @classmethod
    def _task_id(cls, task: object) -> str | None:
        task_id = cls._task_value(task, "id")
        if task_id is None:
            task_id = cls._task_value(task, "task_id")
        normalized = str(task_id).strip() if task_id is not None else ""
        return normalized or None

    @classmethod
    def _task_short_id(cls, task: object) -> str:
        short_id = cls._task_value(task, "short_id")
        if isinstance(short_id, str) and short_id:
            return short_id
        task_id = cls._task_id(task) or "unknown"
        return task_id[:8]

    @classmethod
    def _task_title(cls, task: object) -> str:
        title = str(cls._task_value(task, "title") or "").strip()
        if not title:
            return "Untitled task"
        return title[:44] + ("…" if len(title) > 44 else "")

    @classmethod
    def _task_type_is(cls, task: object, expected: TaskType) -> bool:
        value = cls._task_value(task, "task_type")
        if value == expected:
            return True
        if isinstance(value, str):
            return value.lower() == expected.value
        return getattr(value, "value", None) == expected.value

    @classmethod
    def _task_type(cls, task: object) -> TaskType | None:
        value = cls._task_value(task, "task_type")
        if isinstance(value, TaskType):
            return value
        normalized: str | None = None
        if isinstance(value, str):
            normalized = value.strip().lower()
        else:
            enum_value = getattr(value, "value", None)
            if isinstance(enum_value, str):
                normalized = enum_value.strip().lower()
        if normalized is None:
            return None
        for task_type in TaskType:
            if normalized == task_type.value:
                return task_type
        return None

    @classmethod
    def _task_status(cls, task: object) -> TaskStatus | None:
        value = cls._task_value(task, "status")
        if isinstance(value, TaskStatus):
            return value
        normalized: str | None = None
        if isinstance(value, str):
            normalized = value.strip().lower()
        else:
            enum_value = getattr(value, "value", None)
            if isinstance(enum_value, str):
                normalized = enum_value.strip().lower()
        if normalized is None:
            return None
        for status in TaskStatus:
            if normalized == status.value:
                return status
        return None

    @classmethod
    def _task_context(cls, task: object) -> TaskContext | None:
        task_id = cls._task_id(task)
        if not task_id:
            return None
        return TaskContext(
            task_id=task_id,
            short_id=cls._task_short_id(task),
            title=cls._task_title(task),
            task_type=cls._task_type(task),
            status=cls._task_status(task),
        )

    def _orchestrator_target(self) -> ChatTarget:
        return ChatTarget(
            key=ChatTargetKind.ORCHESTRATOR.value,
            kind=ChatTargetKind.ORCHESTRATOR,
            label="Orchestrator",
            task_id=None,
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

    def _target_from_context(self, context: TaskContext) -> ChatTarget | None:
        kind = self._context_target_kind(context)
        if kind is ChatTargetKind.ORCHESTRATOR:
            return None
        label_prefix = {
            ChatTargetKind.AUTO: "AUTO",
            ChatTargetKind.REVIEW: "REVIEW",
        }[kind]
        return ChatTarget(
            key=f"{kind.value}:{context.task_id}",
            kind=kind,
            label=f"{label_prefix} #{context.short_id} · {context.title}",
            task_id=context.task_id,
        )

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
        return ChatTargetKind.ORCHESTRATOR.value

    async def _refresh_chat_targets(self) -> None:
        current_key = self._active_target().key
        targets: list[ChatTarget] = [self._orchestrator_target()]
        self._task_context_by_id = {}
        ctx = getattr(self.app, "ctx", None)
        requested_task_id = self._requested_task_id
        requested_context = self._requested_task_context

        if ctx is not None and getattr(ctx, "active_project_id", None):
            project_id = ctx.active_project_id
            in_progress: list[object] = []
            in_review: list[object] = []
            try:
                in_progress_result, in_review_result = await asyncio.gather(
                    ctx.api.list_tasks(
                        project_id=project_id,
                        status=TaskStatus.IN_PROGRESS.value,
                    ),
                    ctx.api.list_tasks(
                        project_id=project_id,
                        status=TaskStatus.REVIEW.value,
                    ),
                    return_exceptions=True,
                )
                if not isinstance(in_progress_result, Exception):
                    in_progress = list(in_progress_result)
                if not isinstance(in_review_result, Exception):
                    in_review = list(in_review_result)
            except Exception:
                in_progress = []
                in_review = []

            for task in in_progress:
                context = self._task_context(task)
                if context is None:
                    continue
                self._task_context_by_id[context.task_id] = context
                self._append_target_if_missing(targets, self._target_from_context(context))

            for task in in_review:
                context = self._task_context(task)
                if context is None:
                    continue
                self._task_context_by_id[context.task_id] = context
                self._append_target_if_missing(targets, self._target_from_context(context))

        if requested_context is None and requested_task_id:
            requested_context = self._task_context_by_id.get(requested_task_id)
        if requested_context is None and requested_task_id and ctx is not None:
            try:
                fetched_task = await ctx.api.get_task(requested_task_id)
            except Exception:
                fetched_task = None
            if fetched_task is not None:
                requested_context = self._task_context(fetched_task)
                if requested_context is not None:
                    self._task_context_by_id[requested_context.task_id] = requested_context

        preferred_key: str | None = None
        if requested_context is not None:
            self._focused_task_context = requested_context
            self._append_target_if_missing(targets, self._target_from_context(requested_context))
            preferred_key = self._preferred_target_key_for_context(requested_context, targets)
        elif requested_task_id:
            for target in targets:
                if target.task_id == requested_task_id:
                    preferred_key = target.key
                    break

        self._chat_targets = targets
        selected_index: int | None = None
        if preferred_key is not None:
            for index, target in enumerate(self._chat_targets):
                if target.key == preferred_key:
                    selected_index = index
                    break
        if selected_index is None:
            for index, target in enumerate(self._chat_targets):
                if target.key == current_key:
                    selected_index = index
                    break
        self._active_target_index = selected_index if selected_index is not None else 0
        self._requested_task_id = None
        self._requested_task_context = None
        self._sync_active_target_ui()
        with contextlib.suppress(Exception):
            await self._sync_active_target_session()

    def _sync_active_target_ui(self, *, notify: bool = False) -> None:
        target = self._active_target()
        if target.task_id:
            context = self._task_context_by_id.get(target.task_id)
            if context is not None:
                self._focused_task_context = context
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            if target.kind is ChatTargetKind.ORCHESTRATOR:
                chat_input.placeholder = (
                    "Describe your task... "
                    "(/ for commands, Ctrl+C clears input; Ctrl+C Ctrl+C stops stream)"
                )
            elif target.kind is ChatTargetKind.AUTO:
                chat_input.placeholder = f"Send follow-up to {target.label} (Tab to switch session)"
            else:
                chat_input.placeholder = (
                    f"Queue review follow-up for {target.label} (Tab to switch session)"
                )
        with contextlib.suppress(NoMatches):
            if self.status_bar.status == "ready":
                self.status_bar.update_status("ready", self._ready_hint(target))
        if notify:
            self.notify(f"Chat session: {target.label}", severity="information")

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
        self._auto_stream_entry_ids.clear()
        self._auto_stream_wait_noted = False
        self._auto_stream_idle_noted = False

    async def _sync_active_target_session(self) -> None:
        target = self._active_target()
        if target.kind is not ChatTargetKind.AUTO or not target.task_id:
            self._reset_auto_stream_state()
            return
        self._show_output()
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
            await asyncio.sleep(0.35)

    async def _refresh_auto_stream_for_task(self, task_id: str) -> None:
        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            return

        if self._auto_stream_task_id != task_id:
            self._auto_stream_task_id = task_id
            self._auto_stream_execution_id = None
            self._auto_stream_entry_ids.clear()
            self._auto_stream_wait_noted = False
            self._auto_stream_idle_noted = False

        with contextlib.suppress(Exception):
            await ctx.api.reconcile_running_tasks([task_id])

        readiness = None
        with contextlib.suppress(Exception):
            readiness = await ctx.api.prepare_auto_output(task_id)
        is_running = bool(self._state_attr(readiness, "is_running", False))
        execution_id = self._state_attr(readiness, "execution_id")
        execution_id_str = str(execution_id).strip() if execution_id is not None else ""

        if not execution_id_str:
            with contextlib.suppress(Exception):
                latest_execution = await ctx.api.get_latest_execution_for_task(task_id)
                latest_id = self._state_attr(latest_execution, "id")
                execution_id_str = str(latest_id).strip() if latest_id is not None else ""

        if not execution_id_str:
            if is_running and not self._auto_stream_wait_noted:
                await self.output.post_note("Waiting for live AUTO stream...", classes="warning")
                self._auto_stream_wait_noted = True
                self._auto_stream_idle_noted = False
            elif not is_running and not self._auto_stream_idle_noted:
                await self.output.post_note(
                    "AUTO run is idle. Send a follow-up or `/restart` to run a new iteration.",
                    classes="info",
                )
                self._auto_stream_idle_noted = True
                self._auto_stream_wait_noted = False
            return

        if self._auto_stream_execution_id != execution_id_str:
            self._auto_stream_execution_id = execution_id_str
            self._auto_stream_entry_ids.clear()
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

        for index, entry in enumerate(entries):
            entry_id = self._state_attr(entry, "id", f"idx-{index}")
            normalized_id = str(entry_id)
            if normalized_id in self._auto_stream_entry_ids:
                continue
            self._auto_stream_entry_ids.add(normalized_id)
            logs = self._state_attr(entry, "logs")
            if not isinstance(logs, str) or not logs:
                continue
            for line in logs.splitlines():
                await self._render_auto_log_line(line)

    async def _render_auto_log_line(self, log_line: str) -> None:
        try:
            data = json.loads(log_line)
        except json.JSONDecodeError:
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
                await self.output.post_note(f"AUTO agent failed: {error_msg}", classes="error")
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
        base_hint = "Tab switches session · /help lists commands"
        if verbosity == "tldr":
            base_hint = "Tab session · /help"
        elif verbosity == "technical":
            base_hint = "Tab switches session · /help lists commands · /mode <id> switches mode"

        if target is None:
            return base_hint
        if target.kind is ChatTargetKind.ORCHESTRATOR:
            return base_hint
        return f"{target.label} · {base_hint}"

    async def _cycle_chat_target(self) -> None:
        await self._refresh_chat_targets()
        if not self._chat_targets:
            return
        self._active_target_index = (self._active_target_index + 1) % len(self._chat_targets)
        self._sync_active_target_ui(notify=True)
        with contextlib.suppress(Exception):
            await self._sync_active_target_session()

    def _run_overlay_worker(
        self,
        work: object,
        *,
        group: str | None = None,
        exclusive: bool = False,
    ) -> None:
        try:
            self.run_worker(
                work,
                group=group,
                exclusive=exclusive,
                exit_on_error=False,
            )
        except Exception:
            if inspect.iscoroutine(work):
                with contextlib.suppress(Exception):
                    work.close()

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

    def _sync_screen_overlay_visibility(self) -> None:
        """Reflect overlay visibility onto the owning screen for board chrome rules."""
        if self._embedded:
            return
        with contextlib.suppress(Exception):
            self.screen.set_class(self.has_class("visible"), "chat-overlay-visible")
            sync_empty_placeholders = getattr(
                self.screen, "sync_empty_placeholders_for_overlay", None
            )
            if callable(sync_empty_placeholders):
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

    def show(self, task_id: str | None = None, *, fullscreen: bool = False) -> None:
        """Show overlay and activate orchestrator session."""
        if task_id is not None:
            normalized_task_id = str(task_id).strip()
            self._requested_task_id = normalized_task_id or None
        was_visible = self.has_class("visible")
        if not was_visible and not self._embedded:
            self._capture_focus_return_target()
        self.add_class("visible")
        if fullscreen:
            self.add_class("fullscreen")
        else:
            self.remove_class("fullscreen")
        self._set_logo_variant(fullscreen=fullscreen)
        self._sync_screen_overlay_visibility()
        if not was_visible and not self.has_class("has-content"):
            self._refresh_intro_quote()
        if was_visible:
            with contextlib.suppress(NoMatches):
                self.query_one("#chat-overlay-input", Input).focus()
            self._run_overlay_worker(
                self._refresh_chat_targets,
                group="chat-overlay-targets",
                exclusive=True,
            )
            return
        self._run_overlay_worker(
            self._activate,
            group="chat-overlay-activate",
            exclusive=True,
        )

    def hide(self) -> None:
        """Hide overlay."""
        self.remove_class("visible")
        self.remove_class("fullscreen")
        self._reset_auto_stream_state()
        self._last_ctrl_c_press_at = None
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
        """Handle Escape consistently from overlay context."""
        if not self.has_class("visible"):
            return
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            if self._slash_complete is not None and chat_input.value.startswith("/"):
                if self._embedded:
                    return
                chat_input.value = ""
                self._run_overlay_worker(self._hide_slash_complete)
                return
        if self._embedded:
            return
        self.hide()
        self._run_overlay_worker(
            self._cancel_active_prompt,
            group="chat-overlay-cancel",
            exclusive=True,
        )

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
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
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

    def _is_double_ctrl_c_press(self) -> bool:
        now = monotonic()
        if (
            self._last_ctrl_c_press_at is not None
            and now - self._last_ctrl_c_press_at <= self._CTRL_C_DOUBLE_PRESS_WINDOW_SECONDS
        ):
            self._last_ctrl_c_press_at = None
            return True
        self._last_ctrl_c_press_at = now
        return False

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
        if target.kind is ChatTargetKind.AUTO and target.task_id:
            await self._execute_stop("")
            return
        await self._cancel_active_prompt()

    async def _handle_ctrl_c(self) -> None:
        if self._is_double_ctrl_c_press():
            if self._is_interruptible_stream_active():
                await self._interrupt_active_stream()
            return
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            chat_input.value = ""
            chat_input.focus()
        await self._hide_slash_complete()

    def handle_ctrl_c(self) -> None:
        """Single press clears input; double press interrupts active stream."""
        self._run_overlay_worker(
            self._handle_ctrl_c(),
            group="chat-overlay-interrupt",
            exclusive=True,
        )

    @on(Input.Submitted, "#chat-overlay-input")
    async def _on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.control.value = ""
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
        await self._check_slash_trigger(event.value)

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
        self._discover_local_skills()

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
        await self.output.post_user_input(text)
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
            orchestrator_persona = self._resolve_orchestrator_persona(self._active_target())
            self._conversation_history.append(("user", text))
            snapshot_for_next_prompt = self._pending_compact_snapshot
            prompt = build_orchestrator_prompt(
                text,
                conversation_history=self._conversation_history[:-1],
                session_snapshot=snapshot_for_next_prompt,
                persona=orchestrator_persona,
            )
            try:
                async with asyncio.timeout(self._ORCHESTRATOR_PROMPT_TIMEOUT_SECONDS):
                    await self._agent.send_prompt(prompt)
                response_text = self._agent.get_response_text()
                if response_text:
                    self._conversation_history.append(("assistant", response_text))
                self._pending_compact_snapshot = None
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
        if not self._conversation_history:
            return ""
        lines: list[str] = []
        for role, content in self._conversation_history[-self._COMPACT_MAX_HISTORY_ITEMS :]:
            role_token = str(role).strip().lower()
            role_label = (
                "User"
                if role_token in {str(ChatRole.USER), ChatRole.USER.value, "user"}
                else "Assistant"
            )
            sanitized = redact_sensitive_text(
                normalize_untrusted_text(content, max_chars=self._COMPACT_ENTRY_MAX_CHARS),
                redact_pii=True,
            ).strip()
            if not sanitized:
                continue
            lines.append(f"{role_label}: {sanitized}")
        snapshot = "\n".join(lines).strip()
        if len(snapshot) > self._COMPACT_SNAPSHOT_MAX_CHARS:
            return snapshot[: self._COMPACT_SNAPSHOT_MAX_CHARS - 1].rstrip() + "…"
        return snapshot

    def _snapshot_preview(self, snapshot: str) -> str:
        if len(snapshot) <= self._COMPACT_PREVIEW_MAX_CHARS:
            return snapshot
        return snapshot[: self._COMPACT_PREVIEW_MAX_CHARS - 1].rstrip() + "…"

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

    def _build_auto_follow_up_payload(self, text: str) -> str:
        sanitized_text = redact_sensitive_text(
            normalize_untrusted_text(text, max_chars=QUEUE_MESSAGE_MAX_CHARS),
            redact_pii=True,
        )
        policy_lines = [
            "UNIVERSAL_CHAT_FOLLOW_UP",
            "Priority order:",
            "1) Address the latest user instruction first in your next response/output.",
            "2) Then continue task implementation.",
            "3) Keep task metadata edits aligned with the latest user instruction and task scope.",
        ]
        policy_lines.append("latest_user_instruction:")
        policy_lines.append(sanitized_text)
        return "\n".join(policy_lines)

    @staticmethod
    def _build_review_follow_up_payload(text: str) -> str:
        return redact_sensitive_text(
            normalize_untrusted_text(text, max_chars=QUEUE_MESSAGE_MAX_CHARS),
            redact_pii=True,
        )

    @on(messages.AgentMessage)
    async def _on_agent_message(self, message: messages.AgentMessage) -> None:
        """Route ACP agent messages to stream router."""
        await self._get_agent_stream().dispatch(message)

    async def _handle_agent_update(self, msg: messages.AgentUpdate) -> None:
        await self.output.post_response(msg.text)

    async def _handle_thinking(self, msg: messages.Thinking) -> None:
        await self.output.post_thought(msg.text)

    async def _handle_agent_ready(self, _msg: messages.AgentReady) -> None:
        self._clearing = False
        await self.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
        self._update_status("ready", self._ready_hint(self._active_target()))

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
        self._update_status("error", msg.message)
        await self.output.post_note(f"Error: {msg.message}", classes="error")
        if msg.details:
            await self.output.post_note(msg.details)

    async def _handle_tool_call(self, msg: messages.ToolCall) -> None:
        """Intercept plan_tasks/plan_submit to show approval widget; else default."""
        tool = msg.tool_call
        tool_id = (
            getattr(tool, "tool_call_id", None) or getattr(tool, "toolCallId", None) or "unknown"
        )
        tool_name = (getattr(tool, "name", None) or getattr(tool, "title", None) or "").lower()
        if "plan_tasks" not in tool_name and "plan_submit" not in tool_name:
            await self.output.upsert_tool_call(tool)
            return
        tasks, _todos, err = parse_proposed_plan({tool_id: tool})
        if err or not tasks:
            await self.output.post_note(err or "Could not parse plan", classes="error")
            return
        await self.output.post_plan_approval(tasks)

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

    def _handle_mode_update(self, msg: messages.ModeUpdate) -> None:
        self._current_mode = msg.current_mode

    def _handle_commands_update(self, msg: messages.AvailableCommandsUpdate) -> None:
        self._available_commands = [
            command for command in msg.commands if not self._is_suppressed_agent_command(command)
        ]
        self._refresh_slash_complete_commands()

    def _register_slash_commands(self) -> None:
        @self._slash_registry.command(aliases=["cls"])
        async def clear(args: str) -> None:
            """Clear chat output (`/clear all sessions` resets all session targets)."""
            await self._execute_clear_command(args)

        @self._slash_registry.command()
        async def new(args: str) -> None:
            """Start a new chat session (`/new session`)."""
            await self._execute_new(args)

        @self._slash_registry.command()
        async def compact(args: str) -> None:
            """Compact context (native agent compaction when available)."""
            await self._execute_compact(args)

        @self._slash_registry.command(aliases=["rerun"])
        async def restart(args: str) -> None:
            """Restart active AUTO target (`/restart` or `/restart <extra context>`)."""
            await self._execute_restart(args)

        @self._slash_registry.command()
        async def stop(args: str) -> None:
            """Stop active AUTO run (`/stop`)."""
            await self._execute_stop(args)

        @self._slash_registry.command(aliases=["h", "?"])
        async def help(_args: str) -> None:
            await self._execute_help()

        @self._slash_registry.command(aliases=["modes"])
        async def mode(args: str) -> None:
            await self._execute_mode(args)

        @self._slash_registry.command()
        async def browse(_args: str) -> None:
            """Browse active chat sessions/targets."""
            await self._execute_targets()

        @self._slash_registry.command()
        async def attach(args: str) -> None:
            """Attach to a chat session by task id, target kind, or label fragment."""
            await self._execute_attach(args)

        @self._slash_registry.command(aliases=["sessions"])
        async def targets(_args: str) -> None:
            await self._execute_targets()

        @self._slash_registry.command(aliases=["skill"])
        async def skills(args: str) -> None:
            """List discovered local skills (`/skills` or `/skills refresh`)."""
            await self._execute_skills(args)

    async def _execute_slash_command(self, command_name: str, args: str) -> bool:
        if self._is_removed_command_name(command_name):
            self._show_output()
            await self.output.post_note(
                f"`/{command_name}` is not available in Kagan TUI.",
                classes="warning",
            )
            return True
        local_command = self._slash_registry.find_command(command_name)
        if local_command is not None:
            result = local_command.func(args)
            if asyncio.iscoroutine(result):
                await result
            return True
        return await self._execute_agent_slash_command(command_name, args)

    @staticmethod
    def _normalize_command_args(args: str) -> str:
        return " ".join(args.strip().lower().split())

    async def _execute_clear_command(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if not normalized:
            await self._execute_clear(notification="Conversation cleared")
            return
        if normalized in {"all", "sessions", "all session", "all sessions"}:
            await self._execute_clear_all_sessions()
            return
        self.notify("Usage: /clear or /clear all sessions", severity="warning")

    async def _execute_new(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if normalized not in {"", "session"}:
            self.notify("Usage: /new session", severity="warning")
            return
        await self._execute_clear(notification=None)
        self.notify("Started a new chat session", severity="information")

    async def _execute_restart(self, args: str) -> None:
        target = self._active_target()
        if target.kind is not ChatTargetKind.AUTO or not target.task_id:
            self.notify("/restart is available only for AUTO targets", severity="warning")
            return
        self._show_output()
        extra_context = args.strip()
        if extra_context:
            await self._send_auto_follow_up(target, extra_context)
            return

        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            self.notify("App not initialized", severity="error")
            return

        submitted = await ctx.api.submit_job(target.task_id, "start_agent")
        terminal = await ctx.api.wait_job(
            submitted.job_id,
            task_id=target.task_id,
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

        target = self._active_target()
        if target.kind is not ChatTargetKind.AUTO or not target.task_id:
            self.notify("/stop is available only for AUTO targets", severity="warning")
            return
        self._show_output()

        ctx = getattr(self.app, "ctx", None)
        if ctx is None:
            self.notify("App not initialized", severity="error")
            return

        submitted = await ctx.api.submit_job(target.task_id, "stop_agent")
        terminal = await ctx.api.wait_job(
            submitted.job_id,
            task_id=target.task_id,
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

    def _resolve_attach_target_index(self, raw_query: str) -> int | None:
        query = raw_query.strip().lower()
        if not query:
            return None

        exact_task_query = query.removeprefix("#")
        for index, target in enumerate(self._chat_targets):
            if target.key.lower() == query:
                return index
            if target.kind.value == query:
                return index
            if target.task_id and target.task_id.lower() == exact_task_query:
                return index

        for index, target in enumerate(self._chat_targets):
            if target.task_id and target.task_id.lower().startswith(exact_task_query):
                return index

        for index, target in enumerate(self._chat_targets):
            if query in target.label.lower():
                return index
        return None

    async def _execute_attach(self, args: str) -> None:
        query = args.strip()
        if not query:
            self.notify("Usage: /attach <task-id|kind|label>", severity="warning")
            await self._execute_targets()
            return
        await self._refresh_chat_targets()
        index = self._resolve_attach_target_index(query)
        if index is None:
            self._show_output()
            await self.output.post_note(
                f"No chat session matched `{query}`. Use `/browse` to list available sessions.",
                classes="warning",
            )
            return
        self._active_target_index = index
        self._sync_active_target_ui(notify=True)
        self._show_output()
        await self.output.post_note(
            f"Attached to session `{self._active_target().label}`.",
            classes="success",
        )
        with contextlib.suppress(Exception):
            await self._sync_active_target_session()

    async def _execute_agent_slash_command(self, command_name: str, args: str) -> bool:
        command = self._find_agent_command(command_name)
        if command is None:
            return False
        hint = self._agent_input_hint(command)
        if hint and not args.strip():
            with contextlib.suppress(NoMatches):
                chat_input = self.query_one("#chat-overlay-input", Input)
                chat_input.value = f"/{command_name} "
                chat_input.focus()
            self.notify(f"/{command_name} expects input: {hint}", severity="warning")
            return True
        message = f"/{command_name}"
        cleaned_args = args.strip()
        if cleaned_args:
            message = f"{message} {cleaned_args}"
        await self.output.post_user_input(message)
        self._show_output()
        await self._send_orchestrator_message(message)
        return True

    def _find_agent_command(self, command_name: str) -> AvailableCommand | None:
        for command in self._available_commands:
            if command.name == command_name:
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
        commands: list[SlashCommand[ChatOverlaySlashHandler]] = list(
            self._slash_registry.list_commands()
        )
        existing_names = {command.command for command in commands}
        for command in sorted(self._available_commands, key=lambda item: item.name.lower()):
            if command.name in existing_names:
                continue
            hint_suffix = ""
            input_hint = self._agent_input_hint(command)
            if input_hint:
                hint_suffix = f" (input: {input_hint})"
            commands.append(
                SlashCommand(
                    command=command.name,
                    help=f"{command.description}{hint_suffix}",
                    func=self._noop_slash_handler,
                    aliases=[],
                )
            )
        return commands

    async def _check_slash_trigger(self, text: str) -> None:
        if text.startswith("/") and len(text) <= 2:
            await self._show_slash_complete()
            return
        if self._slash_complete is not None and not text.startswith("/"):
            await self._hide_slash_complete()

    async def _show_slash_complete(self) -> None:
        if self._slash_complete is None:
            self._slash_complete = SlashComplete(id="slash-complete")
            self._slash_complete.slash_commands = self._slash_popup_commands()
            main = self.query_one("#chat-overlay-main", Container)
            chat_input = self.query_one("#chat-overlay-input", Input)
            await main.mount(self._slash_complete)
            chat_input.focus()
            return
        self._refresh_slash_complete_commands()

    async def _hide_slash_complete(self) -> None:
        if self._slash_complete is None:
            return
        await self._slash_complete.remove()
        self._slash_complete = None

    def _refresh_slash_complete_commands(self) -> None:
        if self._slash_complete is None:
            return
        self._slash_complete.slash_commands = self._slash_popup_commands()

    async def _execute_clear(self, *, notification: str | None = "Conversation cleared") -> None:
        self._clearing = True
        self._conversation_history.clear()
        self._pending_compact_snapshot = None
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
        await self._execute_clear(notification=None)
        self._requested_task_id = None
        self._requested_task_context = None
        self._focused_task_context = None
        await self._refresh_chat_targets()
        self._active_target_index = 0
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
        self._pending_compact_snapshot = snapshot
        self._conversation_history.clear()
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
        self._show_output()
        commands = sorted(self._slash_popup_commands(), key=lambda cmd: cmd.command)
        verbosity = self._interaction_verbosity()

        if verbosity == "tldr":
            quick = {
                "help": "Show commands",
                "clear": "Reset conversation",
                "new": "Start fresh session",
                "compact": "Compact context",
                "browse": "List chat sessions",
                "attach": "Attach to a session",
                "restart": "Restart AUTO target",
                "stop": "Stop AUTO target",
                "skills": "List local skills",
                "mode": "List/set mode",
            }
            lines = ["**Quick Commands:**", ""]
            for name, description in quick.items():
                lines.append(f"- `/{name}` - {description}")
            lines.append("")
            lines.append(
                "Switch to short/technical verbosity in Settings for full command details."
            )
            await self.output.post_note("\n".join(lines))
            return

        help_text = "**Available Commands:**\n"
        for command in commands:
            aliases = ""
            if command.aliases:
                alias_text = ", ".join(f"/{alias}" for alias in command.aliases)
                aliases = f" ({alias_text})"
            help_text += f"- `/{command.command}`{aliases} - {command.help}\n"
        if verbosity == "technical":
            help_text += (
                "\n**Usage Notes:**\n"
                "- `Tab` cycles active chat session (Orchestrator/AUTO/REVIEW).\n"
                "- `/browse` lists sessions; `/attach <id|kind|label>` switches directly.\n"
                "- `/restart [extra context]` starts the next AUTO iteration "
                "for the active AUTO target.\n"
                "- `/stop` requests stop for the active AUTO session.\n"
                "- `/new session` starts a fresh local chat session.\n"
                "- `/clear all sessions` resets local chat sessions and target focus.\n"
                "- `/skills` lists trusted local skill metadata; `/skills refresh` rescans.\n"
                "- `/mode` with no args lists modes; `/mode <id>` switches mode.\n"
                "- `/compact` prefers native agent compaction; when unavailable it uses "
                "Kagan's redacted snapshot + fresh-session fallback.\n"
            )
        await self.output.post_note(help_text)

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
        await self.output.post_note(
            f"Switched mode to `{mode_id}` ({mode_name}).",
            classes="success",
        )

    async def _execute_targets(self) -> None:
        await self._refresh_chat_targets()
        self._show_output()
        lines = [
            "**Chat Sessions (Tab to cycle):**",
            "",
            "Use `/attach <task-id|kind|label>` to switch directly.",
            "",
        ]
        active_key = self._active_target().key
        for target in self._chat_targets:
            marker = " (active)" if target.key == active_key else ""
            task_hint = f" [task: `{target.task_id}`]" if target.task_id else ""
            lines.append(f"- `{target.kind.value}`: {target.label}{task_hint}{marker}")
        await self.output.post_note("\n".join(lines))

    async def _execute_skills(self, args: str) -> None:
        normalized = self._normalize_command_args(args)
        if normalized not in {"", "list", "refresh"}:
            self.notify("Usage: /skills [list|refresh]", severity="warning")
            return

        self._show_output()
        if not self._auto_skill_discovery_enabled():
            await self.output.post_note(
                "Skill discovery is disabled. Enable "
                "`general.auto_skill_discovery` in Settings to scan trusted local skill roots.",
                classes="info",
            )
            return

        discovered = self._discover_local_skills(force_refresh=normalized == "refresh")
        if not discovered:
            await self.output.post_note(
                "No local skills discovered in trusted roots "
                "(`.agents/.pi/.claude/.codex/.vtcode`).",
                classes="info",
            )
            return

        lines = [
            "**Discovered Local Skills:**",
            "",
            "Metadata-only catalog from trusted local roots. Skill instruction bodies are not "
            "auto-loaded.",
            "",
        ]
        for skill in discovered[: self._SKILL_DISCOVERY_DISPLAY_LIMIT]:
            try:
                relative_path = skill.location.relative_to(skill.source_root)
                location = f"{skill.source_root}/{relative_path}"
            except ValueError:
                location = str(skill.location)
            description = skill.description or "No description"
            lines.append(f"- `{skill.name}`: {description} (`{location}`)")
        if len(discovered) > self._SKILL_DISCOVERY_DISPLAY_LIMIT:
            omitted = len(discovered) - self._SKILL_DISCOVERY_DISPLAY_LIMIT
            lines.append("")
            lines.append(f"... and {omitted} more skill(s).")
        await self.output.post_note("\n".join(lines))

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
            elif hasattr(screen, "prepare_for_planner_return"):
                await screen.prepare_for_planner_return()
        except Exception as exc:
            self.notify(f"Failed to create tasks: {exc}", severity="error")

    @on(PlanApprovalWidget.Dismissed)
    def _on_plan_dismissed(self) -> None:
        self.notify("Plan dismissed", severity="information")

    def _update_status(self, status: str, hint: str) -> None:
        with contextlib.suppress(NoMatches):
            self.status_bar.update_status(status, hint)

    def _focus_chat_input(self) -> None:
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            if chat_input.disabled or not self.has_class("visible"):
                return
            chat_input.focus()

    def _set_chat_input_disabled(self, disabled: bool) -> None:
        with contextlib.suppress(NoMatches):
            chat_input = self.query_one("#chat-overlay-input", Input)
            chat_input.disabled = disabled
        if not disabled:
            self._focus_chat_input()
            self.call_after_refresh(self._focus_chat_input)

    async def on_unmount(self) -> None:
        await self._hide_slash_complete()
        self._reset_auto_stream_state()
        if self._agent is not None:
            self._agent.set_message_target(None)
            with contextlib.suppress(Exception):
                await self._agent.stop()
        self._agent = None
        self._agent_stream_router = None


__all__ = ["ChatOverlay"]
