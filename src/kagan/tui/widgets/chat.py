import contextlib
import shlex
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.events import Key
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Input, OptionList, Select, Static
from textual.widgets.option_list import Option

from kagan.cli.chat import (
    SLASH_COMMAND_REGISTRY,
    build_slash_presentation_lines,
    format_unknown_slash_command,
    fuzzy_match,
    list_registered_agent_backends,
    normalize_chat_input,
    parse_slash_invocation,
    resolve_slash_input,
)
from kagan.core.enums import SessionKind
from kagan.tui.keybindings import CHAT_BINDINGS
from kagan.tui.screens.file_picker import FilePickerModal
from kagan.tui.screens.session_picker import (
    SessionPickerGroup,
    SessionPickerModal,
    SessionPickerOption,
)
from kagan.tui.widgets.chat_input import ChatInput
from kagan.tui.widgets.chat_session_menu import ChatSessionMenu
from kagan.tui.widgets.chat_transcript import ChatTranscript
from kagan.tui.widgets.permission import PermissionPrompt
from kagan.tui.widgets.status_bar import StatusBar
from kagan.tui.widgets.streaming import ConfidenceLevel, StreamingOutput

_SLASH_ALIASES: Final[dict[str, str]] = {
    "q": "exit",
    "quit": "exit",
    "?": "help",
    "s": "sessions",
    "a": "agents",
    "f": "flow",
}
_TUI_SLASH_COMMANDS: Final[frozenset[str]] = frozenset(
    {
        "agents",
        "clear",
        "delete",
        "exit",
        "flow",
        "help",
        "new",
        "sessions",
        "status",
    }
)


# Overrides Textual private methods to suppress NoMatches during Select's own
# early-mount rendering before SelectCurrent's children are attached.
# This is a Textual-internal initialization sequence issue, not a caller issue.
# Pinned to textual>=7.0.0,<8.0.0.
class _SessionSelect(Select[str]):
    def _setup_options_renderables(self) -> None:
        with contextlib.suppress(NoMatches):
            super()._setup_options_renderables()

    def _init_selected_option(self, hint: Any = Select.BLANK) -> None:
        with contextlib.suppress(NoMatches):
            super()._init_selected_option(hint)


@dataclass(slots=True)
class _SessionState:
    entries: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    draft: str = ""
    prompt_history: list[str] = field(default_factory=list)
    history_index: int | None = None
    decision_surface: tuple[str, dict[str, Any]] | None = None
    last_sent_text: str = ""


class ChatPanel(Vertical):
    BINDINGS = CHAT_BINDINGS
    _deferred_timer: Timer | None = None

    DEFAULT_CSS = """
    ChatPanel {
        layout: vertical;
    }
    """

    @dataclass
    class SubmitRequested(Message):
        text: str

    @dataclass
    class MessageAdded(Message):
        author: str
        text: str

    @dataclass
    class SessionChanged(Message):
        key: str

    @dataclass
    class SessionPickerRequested(Message):
        initial_query: str = ""

    @dataclass
    class CloseRequested(Message):
        pass

    @dataclass
    class NewSessionRequested(Message):
        pass

    @dataclass
    class AgentPickerRequested(Message):
        pass

    @dataclass
    class FilePickerRequested(Message):
        initial_query: str = ""

    @dataclass
    class FilePickerSelected(Message):
        path: str

    @dataclass
    class InterruptRequested(Message):
        pass

    @dataclass
    class InterruptCompleted(Message):
        pass

    @dataclass
    class EditResendRequested(Message):
        text: str

    @dataclass
    class Ready(Message):
        pass

    _EMPTY_TEXT = "No messages yet"
    _LOGO = """\
█▄▀  ▄▀▄  █▀▀  ▄▀▄  █▄  █
█▀▄  █▀█  █▄█  █▀█  █ ▀▄█"""
    _EXAMPLES: tuple[str, ...] = (
        '"Break this task into small milestones"',
        '"/flow Build a release checklist"',
        '"Suggest a safe implementation plan"',
        '"Show risks before coding"',
    )
    _DOCKED_EMPTY_HEADING = "What are you working on?"
    _EXPANDED_EMPTY_HEADING = "What's next?"
    _MAX_SESSION_STATE_COUNT = 30
    _MAX_SESSION_ENTRY_COUNT = 300

    def __init__(
        self,
        *,
        id: str | None = "chat-panel",
        classes: str | None = None,
    ) -> None:
        merged_classes = "chat-overlay" if not classes else f"{classes} chat-overlay"
        super().__init__(id=id, classes=merged_classes)
        self._agent_hint: str | None = None
        self._slash_matches: list[str] = []
        self._mention_matches: list[SessionPickerOption] = []
        self._selected_session_key = "orchestrator"
        self._session_options: list[tuple[str, str]] = [("Orchestrator", "orchestrator")]
        self._session_state: dict[str, _SessionState] = {"orchestrator": _SessionState()}
        self._suspend_session_change_event = False
        self._runtime_status = "ready"
        self._chat_input_disable_depth = 0
        self._pending_after_interrupt: str | None = None
        self._history_programmatic_update = False
        self._overlay_split_key = "Ctrl+I"
        self._overlay_fullscreen_key = "Ctrl+Shift+T"
        self._overlay_close_key = "Esc"
        self._status_hint_override: str | None = None
        self._state_only_updates = 0
        # Cache of chat-session ids belonging to the active project, refreshed
        # asynchronously via :meth:`_refresh_project_session_keys`. ``None``
        # means "not yet loaded / no filter" — the picker shows everything.
        self._project_session_keys_cache: dict[str, set[str]] = {}

    @contextlib.contextmanager
    def state_only_updates(self):
        self._state_only_updates += 1
        try:
            yield
        finally:
            self._state_only_updates = max(0, self._state_only_updates - 1)

    def stream_output(self) -> StreamingOutput:
        return self.query_one("#chat-overlay-output", StreamingOutput)

    def _transcript(self) -> ChatTranscript | None:
        try:
            return self.query_one("#chat-overlay-content", ChatTranscript)
        except NoMatches:
            return None

    def _chat_input(self) -> ChatInput | None:
        try:
            return self.query_one("#chat-overlay-command-line", ChatInput)
        except NoMatches:
            return None

    def _session_menu(self) -> ChatSessionMenu | None:
        try:
            return self.query_one("#chat-overlay-session-switcher", ChatSessionMenu)
        except NoMatches:
            return None

    def compose(self) -> ComposeResult:
        yield Static("Orchestrator", id="chat-title")
        with Vertical(id="chat-overlay-main"):
            with ChatTranscript(id="chat-overlay-content"):
                with Vertical(id="chat-overlay-empty-state", classes="chat-overlay-empty-state"):
                    with Vertical(classes="chat-overlay-empty-content"):
                        with Vertical(classes="chat-overlay-empty-card"):
                            yield Static(
                                self._LOGO,
                                classes="chat-header chat-overlay-logo",
                                id="chat-overlay-logo",
                            )
                            yield Static(
                                self._DOCKED_EMPTY_HEADING,
                                id="chat-overlay-empty-heading",
                            )
                            yield Static(
                                (
                                    "Describe what to build, or run /flow for guided "
                                    "Plan -> Execute -> Orchestrate."
                                ),
                                id="chat-overlay-empty-description",
                            )
                            yield Static(
                                (
                                    "Want a quick TLDR walkthrough?\n"
                                    "Need structure? Use /flow <goal> "
                                    "for an explicit 3-phase guide."
                                ),
                                id="chat-overlay-empty-walkthrough",
                            )
                            with Vertical(id="chat-overlay-empty-examples"):
                                yield Static(
                                    "Examples:", classes="chat-overlay-empty-section-title"
                                )
                                for example in self._EXAMPLES:
                                    yield Static(
                                        f"  • {example}", classes="chat-overlay-empty-example"
                                    )
                            yield Static(
                                "Tip: use this screen's chat shortcut to open AI chat.",
                                id="chat-overlay-first-boot-nudge",
                            )
                yield StreamingOutput(id="chat-overlay-output", classes="chat-output")
                yield Vertical(id="chat-inline-surface")
                yield Static(
                    self._EMPTY_TEXT,
                    classes="chat-empty chat-output chat-output-buffer",
                    id="chat-messages",
                    markup=False,
                )

            with Vertical(id="chat-overlay-bottom"):
                yield StatusBar(id="chat-overlay-status", classes="chat-status")
                with ChatInput(
                    classes="chat-input-row chat-command-line",
                    id="chat-overlay-command-line",
                ):
                    with Horizontal(classes="chat-input-with-badge", id="chat-input-with-badge"):
                        with Horizontal(classes="chat-input", id="chat-overlay-input-shell"):
                            chat_input = Input(
                                placeholder="What's next? Try /flow",
                                classes="chat-input-area",
                                id="chat-overlay-input",
                            )
                            chat_input.tooltip = (
                                "AI chat input. Type your request or use /flow for guided planning."
                            )
                            yield chat_input
                        badge = Static(
                            "Orchestrator",
                            id="chat-overlay-session-badge",
                            classes="session-badge session-kind-orchestrator",
                        )
                        badge.tooltip = "Current session kind (Orchestrator/Agent)"
                        yield badge
                with ChatSessionMenu(id="chat-overlay-session-switcher"):
                    with Horizontal(id="chat-overlay-session-current-wrap"):
                        mode_badge = Static(
                            "Docked",
                            id="chat-overlay-mode-badge",
                            classes="mode-docked",
                        )
                        mode_badge.tooltip = (
                            "Chat panel mode: Docked or Expanded (Ctrl+I to toggle)"
                        )
                        yield mode_badge
                        session_indicator = Static(
                            "●",
                            id="chat-overlay-session-indicator",
                            classes="session-kind-orchestrator",
                        )
                        session_indicator.tooltip = "Session status indicator"
                        yield session_indicator
                        session_label = Static("Orchestrator", id="chat-overlay-session-current")
                        session_label.tooltip = "Current active session"
                        yield session_label
                    with Horizontal(id="chat-overlay-session-toggle"):
                        toggle_label = Static("Session", id="chat-overlay-session-toggle-label")
                        toggle_label.tooltip = "Switch between active sessions"
                        yield toggle_label
                        session_select = _SessionSelect(
                            options=self._session_options,
                            value=self._selected_session_key,
                            id="chat-overlay-session-select",
                            allow_blank=False,
                            compact=True,
                        )
                        session_select.tooltip = "Select a different session to work with"
                        yield session_select

            with Vertical(classes="slash-complete", id="slash-complete"):
                yield OptionList(id="slash-options")
            with Vertical(classes="task-mention-complete", id="task-mention-complete"):
                yield OptionList(id="mention-options")

    def on_mount(self) -> None:
        self.set_class(True, "docked")
        self.set_class(True, "default")
        self.set_class(False, "expanded")
        self.set_class(False, "fullscreen")

        # Most setup queries widgets yielded unconditionally in compose().
        # A handful of test fixtures mount ChatPanel via partial-compose paths
        # (e.g. doctor modal harness) where individual children may be absent;
        # guard each query so a missing widget doesn't abort the rest of mount.
        for query_id, widget_type in (
            ("#slash-complete", Vertical),
            ("#task-mention-complete", Vertical),
            ("#chat-inline-surface", Vertical),
            ("#chat-messages", Static),
            ("#chat-title", Static),
        ):
            with contextlib.suppress(NoMatches):
                self.query_one(query_id, widget_type).display = False
        with contextlib.suppress(NoMatches):
            input_widget = self._input_widget()
            input_widget.disabled = True
            input_widget.can_focus = False
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-session-select", Select).disabled = True
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-empty-heading", Static).update(self._DOCKED_EMPTY_HEADING)
        self._sync_input_enabled_state()
        self._render_current_session()
        self._refresh_status()
        self.post_message(ChatPanel.Ready())

    def set_visible(self, visible: bool) -> None:
        self.set_class(visible, "visible")
        selector = self._session_selector()
        if selector is not None:
            selector.disabled = not visible
        self._sync_input_enabled_state()
        if not visible:
            self._flush_deferred()
            self._current_state().draft = self._input_widget().value
            self._hide_overlays()
        self._refresh_status()

    def set_fullscreen(self, fullscreen: bool) -> None:
        self.set_class(fullscreen, "fullscreen")
        self.set_class(fullscreen, "expanded")
        self.set_class(not fullscreen, "docked")
        self.set_class(not fullscreen, "default")
        badge = self.query_one("#chat-overlay-mode-badge", Static)
        if fullscreen:
            badge.update("Expanded")
            badge.set_class(True, "mode-expanded")
            badge.set_class(False, "mode-docked")
        else:
            badge.update("Docked")
            badge.set_class(False, "mode-expanded")
            badge.set_class(True, "mode-docked")
        heading = self.query_one("#chat-overlay-empty-heading", Static)
        if fullscreen:
            heading.update(self._EXPANDED_EMPTY_HEADING)
        else:
            heading.update(self._DOCKED_EMPTY_HEADING)
        self._refresh_status()

    def set_mode_title(self, title: str) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-title", Static).update(title)
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-session-badge", Static).update(title)
        self._refresh_status()

    def set_sessions(self, sessions: list[tuple[str, str]], active_key: str | None = None) -> None:
        normalized = [(label.strip(), key.strip()) for label, key in sessions if label and key]
        self._session_options = normalized or [("Orchestrator", "orchestrator")]
        # Invalidate + refresh the per-project session-key cache. ``set_sessions``
        # is called whenever the orchestrator store changes (new/delete/switch),
        # which is the same trigger ``SessionChanged`` fires under.
        self._project_session_keys_cache.clear()
        core = getattr(self.app, "core", None)
        active_project_id = getattr(core, "active_project_id", None) if core else None
        if isinstance(active_project_id, str) and active_project_id:
            self._kick_project_session_keys_refresh(active_project_id)
        for _label, key in self._session_options:
            self._ensure_session_state(key)
        self._prune_session_states()

        next_key = active_key or self._selected_session_key
        if not any(key == next_key for _, key in self._session_options):
            next_key = self._session_options[0][1]

        self._suspend_session_change_event = True
        selector = self._session_selector()
        if selector is None:
            self._selected_session_key = next_key
            self._ensure_session_state(next_key)
            self.set_class(len(self._session_options) > 1, "chat-overlay-multi-session")
            self._release_session_change_suspension()
            return
        set_options = getattr(selector, "set_options", None)
        if callable(set_options):
            set_options(self._session_options)
        selector.value = next_key
        self.set_class(len(self._session_options) > 1, "chat-overlay-multi-session")
        self._switch_session(next_key, emit=False)
        self.call_after_refresh(self._release_session_change_suspension)

    def _release_session_change_suspension(self) -> None:
        self._suspend_session_change_event = False

    def set_session_kind(self, kind: str) -> None:
        with contextlib.suppress(NoMatches):
            indicator = self.query_one("#chat-overlay-session-indicator", Static)
            for css_kind in SessionKind:
                indicator.set_class(css_kind == kind, f"session-kind-{css_kind}")
        with contextlib.suppress(NoMatches):
            badge = self.query_one("#chat-overlay-session-badge", Static)
            for css_kind in SessionKind:
                badge.set_class(css_kind == kind, f"session-kind-{css_kind}")

    def set_overlay_shortcuts(
        self,
        *,
        split: str,
        fullscreen: str,
        close: str | None = None,
    ) -> None:
        self._overlay_split_key = split.strip() or self._overlay_split_key
        self._overlay_fullscreen_key = fullscreen.strip() or self._overlay_fullscreen_key
        if close is not None:
            self._overlay_close_key = close.strip() or self._overlay_close_key
        self._refresh_status()

    def set_status_hint_override(self, hint: str | None) -> None:
        normalized = hint.strip() if isinstance(hint, str) else ""
        self._status_hint_override = normalized or None
        self._refresh_status()

    def set_first_boot(self, enabled: bool = True) -> None:
        self.set_class(enabled, "first-boot")

    def add_user_message(self, text: str) -> None:
        self._append_text_entry("user", text, author="You")

    def add_assistant_message(self, text: str) -> None:
        self._append_text_entry("assistant", text, author="Agent", merge=True)

    def add_system_message(self, text: str) -> None:
        self._append_text_entry("note", text, author="System")

    def add_thought_message(self, text: str) -> None:
        self._append_text_entry("thought", text, author="Agent", merge=True)

    def append_assistant_fragment(self, text: str) -> None:
        self._append_stream_fragment("assistant", text)

    def append_thought_fragment(self, text: str) -> None:
        self._append_stream_fragment("thought", text)

    def upsert_tool_call(
        self,
        tool_id: str,
        title: str,
        *,
        status: str = "running",
        args: str | None = None,
        result: str | None = None,
        kind: str | None = None,
    ) -> None:
        state = self._current_state()
        for index, (kind, existing) in enumerate(state.entries):
            if kind == "tool" and existing.get("tool_id") == tool_id:
                state.entries[index] = (
                    "tool",
                    {
                        "tool_id": tool_id,
                        "title": title or str(existing.get("title") or tool_id),
                        "status": status,
                        "args": args if args is not None else existing.get("args"),
                        "result": result if result is not None else existing.get("result"),
                        "kind": kind or existing.get("kind"),
                    },
                )
                break
        else:
            state.entries.append(
                (
                    "tool",
                    {
                        "tool_id": tool_id,
                        "title": title,
                        "status": status,
                        "args": args,
                        "result": result,
                        "kind": kind,
                    },
                )
            )
        self._trim_session_entries(state)
        if self.is_mounted and self._state_only_updates == 0:
            stream = self._stream_output()
            if stream is None:
                return
            stream.upsert_tool_call(
                tool_id,
                title or tool_id,
                status=status,
                args=args,
                result=result,
                kind=kind,
            )
            self._schedule_deferred_update()

    def update_tool_call(self, tool_id: str, status: str, *, result: str | None = None) -> None:
        state = self._current_state()
        for index, (kind, existing) in enumerate(state.entries):
            if kind != "tool" or existing.get("tool_id") != tool_id:
                continue
            payload = dict(existing)
            payload["status"] = status
            if result is not None:
                payload["result"] = result
            state.entries[index] = ("tool", payload)
            if self.is_mounted and self._state_only_updates == 0:
                stream = self._stream_output()
                if stream is None:
                    return
                stream.update_tool_status(tool_id, status, result=result)
                self._schedule_deferred_update()
            return

    def request_permission(self, text: str, *, timeout_seconds: int = 30) -> None:
        state = self._current_state()
        state.decision_surface = (
            "permission",
            {"text": text, "timeout_seconds": timeout_seconds},
        )
        if self.is_mounted:
            self._render_decision_surface()

    def clear_messages(self) -> None:
        state = self._current_state()
        state.entries.clear()
        state.decision_surface = None
        self._runtime_status = "ready"
        self._cancel_deferred_timer()
        if self.is_mounted:
            self._render_current_session()

    def message_count(self) -> int:
        return sum(
            1
            for kind, _payload in self._current_state().entries
            if kind in {"assistant", "user", "note", "thought"}
        )

    def preferred_agent_backend(self) -> str | None:
        return self._agent_hint

    def set_runtime_status(self, status: str) -> None:
        self._runtime_status = status.strip().lower() or "ready"
        if self.is_mounted:
            status_bar = self._status_bar()
            if status_bar is not None:
                status_bar.update_status(self._runtime_status)

    def set_agent_backend(self, backend: str) -> None:
        if self.is_mounted:
            status_bar = self._status_bar()
            if status_bar is not None:
                status_bar.agent_backend = backend

    def set_preferred_agent_backend(self, backend: str | None) -> None:
        if backend is None:
            self._agent_hint = None
            return
        normalized = backend.strip()
        self._agent_hint = normalized or None

    def increment_turn_count(self) -> None:
        if self.is_mounted:
            status_bar = self._status_bar()
            if status_bar is not None:
                status_bar.turn_count += 1

    def handle_interrupt(self) -> bool:
        """Fallback Ctrl+C handler for when the chat input does not have focus.

        Called by ``KaganApp.action_help_quit`` so that the Textual system
        Ctrl+C binding clears the chat input instead of showing a quit toast.
        When the input *does* have focus, ``on_key`` handles Ctrl+C directly.
        """
        try:
            input_widget = self._input_widget()
            if input_widget.value:
                self.action_clear_input()
                return True
        except NoMatches:
            pass
        return False

    def hydrate_current_session_history(self, history: list[tuple[str, str]]) -> None:
        state = self._current_state()
        state.entries.clear()
        state.decision_surface = None
        self._cancel_deferred_timer()
        for role, content in history:
            if role == "assistant":
                state.entries.append(("assistant", {"text": content}))
            else:
                state.entries.append(("user", {"text": content}))
        self._trim_session_entries(state)
        if self.is_mounted:
            self._render_current_session()

    def export_rendered_messages(self) -> list[str]:
        return self._rendered_messages()

    def set_stream_action(
        self,
        action: str,
        *,
        confidence: ConfidenceLevel = "certain",
    ) -> None:
        if not self.is_mounted:
            return
        stream = self._stream_output()
        if stream is None:
            return
        stream.set_current_action(action, confidence=confidence)

    @on(Input.Changed, "#chat-overlay-input")
    def _on_input_changed(self, event: Input.Changed) -> None:
        state = self._current_state()
        state.draft = event.value
        if self._history_programmatic_update:
            self._history_programmatic_update = False
        elif state.history_index is not None:
            state.history_index = None
        self._sync_completion_overlays(event.value)

    @on(OptionList.OptionSelected, "#slash-options")
    def _on_slash_option_selected(self, _: OptionList.OptionSelected) -> None:
        self.action_accept_completion()

    @on(OptionList.OptionSelected, "#mention-options")
    def _on_mention_option_selected(self, _: OptionList.OptionSelected) -> None:
        self.action_accept_completion()

    @on(Select.Changed, "#chat-overlay-session-select")
    def _on_session_changed(self, event: Select.Changed) -> None:
        if self._suspend_session_change_event:
            return
        value = event.value
        if value is Select.BLANK or not isinstance(value, str):
            return
        selector = self.query_one("#chat-overlay-session-select", Select)
        current_value = selector.value
        if current_value is Select.BLANK or not isinstance(current_value, str):
            return
        if value != current_value:
            return
        self._switch_session(value, emit=True)

    @on(Input.Submitted, "#chat-overlay-input")
    async def _on_input_submitted(self) -> None:
        await self._submit_current_input()

    @on(PermissionPrompt.DecisionMade)
    def _on_permission_decision(self, event: PermissionPrompt.DecisionMade) -> None:
        state = self._current_state()
        state.decision_surface = None
        self.add_system_message(f"Permission {event.decision}")
        self._render_decision_surface()

    def on_key(self, event: Key) -> None:
        """Intercept arrow keys for slash/mention completion overlay navigation."""
        overlay_visible = bool(self._slash_matches or self._mention_matches)
        if overlay_visible:
            option_list_id = "#slash-options" if self._slash_matches else "#mention-options"
            option_list = self.query_one(option_list_id, OptionList)

            nav_map: dict[str, str] = {
                "up": "action_cursor_up",
                "down": "action_cursor_down",
                "pageup": "action_page_up",
                "pagedown": "action_page_down",
                "home": "action_first",
                "end": "action_last",
            }

            if event.key in nav_map:
                event.prevent_default()
                event.stop()
                with contextlib.suppress(AttributeError):
                    getattr(option_list, nav_map[event.key])()
                return

            if event.key == "enter":
                # If the input already contains a complete slash command, submit it
                # instead of merely accepting the overlay selection.
                current_text = self._input_widget().value.strip()
                if current_text.startswith("/"):
                    cmd_name = (
                        current_text.lstrip("/").split()[0] if current_text.lstrip("/") else ""
                    )
                    specs = [
                        spec
                        for spec in SLASH_COMMAND_REGISTRY.specs()
                        if spec.name in _TUI_SLASH_COMMANDS
                    ]
                    exact_match = any(spec.name == cmd_name for spec in specs)
                    if exact_match:
                        self._hide_overlays()
                        self.call_later(self.action_send_message)
                        return
                event.prevent_default()
                event.stop()
                self.action_accept_completion()
                return

            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._hide_overlays()
                return

        if event.key == "escape" and not self._input_has_focus():
            event.prevent_default()
            event.stop()
            self._input_widget().focus()
            return

        if not self._input_has_focus():
            return

        if event.key == "ctrl+c":
            event.prevent_default()
            event.stop()
            # Ctrl+C clears input — Esc stops agent + edits last message
            if self._input_widget().value:
                self.action_clear_input()
            return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.call_later(self.action_send_message)
            return

        if overlay_visible:
            return

        if event.key == "up":
            if self._cycle_prompt_history(direction="up"):
                event.prevent_default()
                event.stop()
            return

        if event.key == "down":
            if self._cycle_prompt_history(direction="down"):
                event.prevent_default()
                event.stop()
            return

    async def action_send_message(self) -> None:
        await self._submit_current_input()

    def action_focus_output_latest(self) -> None:
        stream = self._stream_output()
        if stream is None:
            return
        stream.action_jump_to_latest()

    def action_insert_newline(self) -> None:
        return

    def action_clear_input(self) -> None:
        input_widget = self._input_widget()
        if input_widget.disabled:
            return
        if not input_widget.value:
            return
        self._history_programmatic_update = True
        input_widget.value = ""
        state = self._current_state()
        state.draft = ""
        state.history_index = None
        self._hide_overlays()
        input_widget.focus()

    def action_accept_completion(self) -> None:
        if self._mention_matches:
            self._apply_mention_completion()
            return
        if not self._slash_matches:
            return
        option_list = self.query_one("#slash-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or highlighted < 0 or highlighted >= len(self._slash_matches):
            selected = self._slash_matches[0]
        else:
            selected = self._slash_matches[highlighted]
        input_widget = self._input_widget()
        input_widget.value = f"/{selected} "
        input_widget.focus()
        self._current_state().draft = input_widget.value
        self._hide_slash_complete()

    def action_dismiss(self) -> None:
        if self._mention_matches or self._slash_matches:
            self._hide_overlays()
            return
        if self._runtime_status in {"thinking", "initializing", "waiting"}:
            input_widget = self._input_widget()
            pending = normalize_chat_input(input_widget.value)
            if pending:
                self._pending_after_interrupt = pending
                input_widget.value = ""
                self._current_state().draft = ""
            else:
                self._pending_after_interrupt = None
            self.post_message(ChatPanel.InterruptRequested())
            return
        self._request_close()

    def _handle_interrupt_completed(self) -> None:
        state = self._current_state()
        input_widget = self._input_widget()
        if self._pending_after_interrupt is not None:
            queued = self._pending_after_interrupt
            self._pending_after_interrupt = None
            input_widget.value = queued
            state.draft = queued
            self.call_later(self._submit_current_input)
        else:
            last = state.last_sent_text
            if last:
                self._history_programmatic_update = True
                input_widget.value = last
                state.draft = last
        input_widget.focus()
        self._refresh_status()

    def on_chat_panel_interrupt_completed(self, _: "ChatPanel.InterruptCompleted") -> None:
        self._handle_interrupt_completed()

    def on_chat_panel_edit_resend_requested(self, event: "ChatPanel.EditResendRequested") -> None:
        input_widget = self._input_widget()
        self._history_programmatic_update = True
        input_widget.value = event.text
        self._current_state().draft = event.text
        input_widget.focus()

    def action_open_session_picker(self, initial_query: str | None = None) -> None:
        self._request_session_picker(initial_query or "")

    def create_session_picker_modal(self, *, initial_query: str = "") -> SessionPickerModal:
        return SessionPickerModal(
            groups=self._build_session_groups(),
            active_key=self._selected_session_key,
            initial_query=initial_query,
        )

    def action_open_file_picker(self, initial_query: str | None = None) -> None:
        self._request_file_picker(initial_query or "")

    def create_file_picker_modal(self, *, initial_query: str = "") -> FilePickerModal:
        return FilePickerModal(initial_query=initial_query)

    def handle_file_picker_selected(self, selected_path: str | None) -> None:
        if not selected_path:
            return
        self.insert_file_reference(selected_path)
        self.post_message(self.FilePickerSelected(path=selected_path))

    def _on_file_picker_selected(self, selected_path: str | None) -> None:
        self.handle_file_picker_selected(selected_path)

    def insert_file_reference(self, relative_path: str) -> None:
        token = relative_path.strip()
        if not token:
            return
        if any(ch.isspace() for ch in token) or token.startswith("-"):
            token = shlex.quote(token)
        input_widget = self._input_widget()
        input_widget.insert_text_at_cursor(f"{token} ")
        self._current_state().draft = input_widget.value
        input_widget.focus()
        self._sync_completion_overlays(input_widget.value)

    async def _submit_current_input(self) -> None:
        input_widget = self._input_widget()
        if input_widget.disabled:
            return
        text = normalize_chat_input(input_widget.value)
        if not text:
            return

        if (
            self._slash_matches
            and text.startswith("/")
            and " " not in text[1:]
            and SLASH_COMMAND_REGISTRY.get(text[1:].casefold()) is None
        ):
            self.action_accept_completion()
            return

        session_key, resolved_text = self._consume_session_prefix(text)
        if session_key is not None:
            self._switch_session(session_key, emit=True)
            text = resolved_text
            if not text:
                input_widget.value = ""
                self._current_state().draft = ""
                self._hide_overlays()
                return

        self._append_prompt_history(text)
        self._current_state().last_sent_text = text

        handled = await self._handle_slash_command(text)
        if not handled:
            self.post_message(self.SubmitRequested(text))
            self.add_user_message(text)

        input_widget.value = ""
        self._current_state().draft = ""
        input_widget.focus()
        self._hide_overlays()

    async def _handle_slash_command(self, text: str) -> bool:
        by_key = {key: label for label, key in self._session_options}
        session_label = by_key.get(self._selected_session_key, "Orchestrator")
        invocation = parse_slash_invocation(text)
        if invocation is not None and invocation.name:
            target = _SLASH_ALIASES.get(invocation.name, invocation.name)
            if target not in _TUI_SLASH_COMMANDS:
                self.add_system_message(f"Error: {format_unknown_slash_command(invocation.name)}")
                return True

        result = resolve_slash_input(
            text,
            session_label=session_label,
            session_key=self._selected_session_key,
            runtime_session_id=None,
            current_backend=self._agent_hint,
            available_backends=list_registered_agent_backends(),
        )
        if not result.handled:
            return False

        if result.clear_requested:
            self.clear_messages()

        if result.selected_agent is not None:
            self._agent_hint = result.selected_agent
            self.add_system_message(f"Switched to {result.selected_agent}")
        if result.sessions_requested:
            self._request_session_picker(result.sessions_query or "")

        if result.delete_session_query is not None:
            await self._delete_chat_session(result.delete_session_query)

        if result.new_session_requested:
            self.post_message(self.NewSessionRequested())

        if result.agent_picker_requested:
            self.post_message(self.AgentPickerRequested())

        if result.help_overlay_requested:
            self._show_help_overlay()

        if result.status_requested:
            self.add_system_message(
                f"Session: {self._selected_session_key} | Agent: {self._agent_hint or 'default'}"
            )

        if result.project_info_requested:
            core = getattr(self.app, "core", None)
            pid = getattr(core, "active_project_id", None) if core else None
            self.add_system_message(f"Active project: {pid or '(none)'}")

        if result.project_switch_requested is not None:
            self.add_system_message(
                "Project switching is available via CLI or REPL. "
                f"Requested: {result.project_switch_requested}"
            )

        for line in build_slash_presentation_lines(result):
            if line.tone == "error":
                self.add_system_message(f"Error: {line.text}")
            else:
                self.add_system_message(line.text)

        if result.close_requested:
            self._request_close()

        return True

    def _request_session_picker(self, initial_query: str) -> None:
        if not self.has_class("chat-overlay"):
            return
        self.post_message(self.SessionPickerRequested(initial_query=initial_query))

    def _request_file_picker(self, initial_query: str) -> None:
        if not self.has_class("chat-overlay"):
            return
        self.post_message(self.FilePickerRequested(initial_query=initial_query))

    def _show_help_overlay(self) -> None:
        """Focus input with '/' to trigger the existing slash completion overlay."""
        input_widget = self._input_widget()
        input_widget.value = "/"
        input_widget.focus()
        self._sync_slash_complete("/")

    async def _delete_chat_session(self, query: str) -> None:
        """Delete a chat session by number or id."""
        # Pure UI helpers (item formatting + selector) stay in the cli.chat
        # shim until the chat-package consolidation completes (phase 6); the
        # actual DB mutation now goes through ``core.chat_sessions`` directly.
        from kagan.cli.chat.sessions import (
            build_chat_session_list_items,
            list_chat_sessions,
            resolve_chat_session_selector,
        )

        core = getattr(self.app, "core", None)
        if core is None:
            self.add_system_message("No client available.")
            return

        sessions = await list_chat_sessions(core)
        if not sessions:
            self.add_system_message("No sessions to delete.")
            return

        items = build_chat_session_list_items(sessions)
        target = resolve_chat_session_selector(items, query)
        if target is None:
            self.add_system_message(f"Unknown session: {query}")
            return

        # Don't allow deleting current session
        if target.session_id == self._selected_session_key:
            self.add_system_message("Cannot delete the current session.")
            return

        deleted = await core.chat_sessions.delete(target.session_id)
        if deleted:
            self.add_system_message(f"Deleted: {target.label} [{target.session_id}]")
        else:
            self.add_system_message(f"Failed to delete session {target.session_id}.")

    def _request_close(self) -> None:
        if self.has_class("chat-overlay"):
            self.post_message(self.CloseRequested())
            return
        self.set_visible(False)

    def _append_text_entry(
        self,
        kind: str,
        text: str,
        *,
        author: str,
        merge: bool = False,
    ) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        state = self._current_state()
        if (
            not merge
            and state.entries
            and state.entries[-1][0] == kind
            and state.entries[-1][1].get("text") == cleaned
        ):
            return
        if merge and state.entries and state.entries[-1][0] == kind:
            previous = dict(state.entries[-1][1])
            previous["text"] = f"{previous.get('text', '')}{cleaned}"
            state.entries[-1] = (kind, previous)
        else:
            state.entries.append((kind, {"text": cleaned}))
        self._trim_session_entries(state)

        if self.is_mounted and self._state_only_updates == 0:
            stream = self._stream_output()
            if stream is None:
                return
            if kind == "user":
                stream.post_user_input(cleaned)
            elif kind == "assistant":
                stream.append_chunk(cleaned, kind="assistant", merge=merge)
            elif kind == "thought":
                stream.append_chunk(cleaned, kind="thought", merge=merge)
            else:
                stream.post_note(cleaned)

        if merge:
            self._schedule_deferred_update()
            return

        self.post_message(self.MessageAdded(author=author, text=cleaned))
        self._update_hidden_buffer()
        self._update_content_state()
        self._refresh_status()

    def _append_stream_fragment(
        self,
        kind: Literal["assistant", "thought"],
        text: str,
    ) -> None:
        if not text:
            return

        state = self._current_state()
        if state.entries and state.entries[-1][0] == kind:
            previous = dict(state.entries[-1][1])
            previous["text"] = f"{previous.get('text', '')}{text}"
            state.entries[-1] = (kind, previous)
        else:
            state.entries.append((kind, {"text": text}))
        self._trim_session_entries(state)

        if self.is_mounted and self._state_only_updates == 0:
            stream = self._stream_output()
            if stream is None:
                return
            stream.append_chunk(text, kind=kind, merge=True)

        self._schedule_deferred_update()

    def _ensure_session_state(self, key: str) -> _SessionState:
        state = self._session_state.get(key)
        if state is None:
            state = _SessionState()
            self._session_state[key] = state
        return state

    def _prune_session_states(self) -> None:
        keep_keys = [key for _label, key in self._session_options]
        if self._selected_session_key not in keep_keys:
            keep_keys.append(self._selected_session_key)
        keep = set(keep_keys[-self._MAX_SESSION_STATE_COUNT :])
        for key in list(self._session_state):
            if key not in keep:
                self._session_state.pop(key, None)

    def _trim_session_entries(self, state: _SessionState) -> None:
        if len(state.entries) <= self._MAX_SESSION_ENTRY_COUNT:
            return
        state.entries = state.entries[-self._MAX_SESSION_ENTRY_COUNT :]

    def _current_state(self) -> _SessionState:
        return self._ensure_session_state(self._selected_session_key)

    def _switch_session(self, key: str, *, emit: bool) -> None:
        previous_key = self._selected_session_key
        if self.is_mounted:
            self._flush_deferred()
            input_widget = self._input_widget_safe()
            if input_widget is not None:
                self._ensure_session_state(previous_key).draft = input_widget.value

        self._selected_session_key = key
        self._ensure_session_state(key)
        self._sync_session_label()
        self.set_session_kind(self._infer_session_kind(key))

        if self.is_mounted:
            input_widget = self._input_widget_safe()
            if input_widget is not None:
                input_widget.value = self._current_state().draft
                self._sync_completion_overlays(input_widget.value)
            self._render_current_session()

        if emit and previous_key != key:
            self.post_message(self.SessionChanged(key))

    def _render_current_session(self) -> None:
        state = self._current_state()
        transcript = self._transcript()
        if transcript is not None:
            transcript.render_session(state.entries, state.decision_surface)
        else:
            # Partial-compose harnesses (e.g. doctor modal) may not yield the
            # transcript subtree; fall through with a no-op so the rest of the
            # mount sequence proceeds.
            self._update_hidden_buffer()
        self._update_content_state()
        self._refresh_status()

    def _render_decision_surface(self) -> None:
        transcript = self._transcript()
        if transcript is None:
            return
        transcript.render_decision_surface(self._current_state().decision_surface)

    def _rendered_messages(self) -> list[str]:
        return ChatTranscript.rendered_messages(self._current_state().entries)

    def _update_hidden_buffer(self) -> None:
        transcript = self._transcript()
        if transcript is None:
            return
        transcript.update_hidden_buffer(self._current_state().entries)

    def _update_content_state(self) -> None:
        state = self._current_state()
        has_content = bool(state.entries or state.decision_surface)
        self.set_class(has_content, "has-content")

    def _cancel_deferred_timer(self) -> None:
        if self._deferred_timer is None:
            return
        self._deferred_timer.stop()
        self._deferred_timer = None

    def _schedule_deferred_update(self) -> None:
        if not self.is_mounted:
            return
        if not self.has_class("has-content") and self._current_state().entries:
            self.set_class(True, "has-content")
        if self._deferred_timer is not None:
            self._deferred_timer.reset()
            return
        self._deferred_timer = self.set_timer(0.5, self._flush_deferred)

    def _flush_deferred(self) -> None:
        self._cancel_deferred_timer()
        if not self.is_mounted:
            return
        self._update_hidden_buffer()
        self._update_content_state()
        self._refresh_status()

    def _input_widget(self) -> Input:
        chat_input = self._chat_input()
        if chat_input is None:
            return self.query_one("#chat-overlay-input", Input)
        return chat_input.input_widget()

    def _input_widget_safe(self) -> Input | None:
        # Returns None when called from a partial-mount test fixture that
        # doesn't yield the input widget (e.g. doctor modal harness). All
        # post-Ready call sites can use the bare _input_widget() directly.
        try:
            return self._input_widget()
        except NoMatches:
            return None

    def _session_selector(self) -> Select[str] | None:
        menu = self._session_menu()
        if menu is None:
            try:
                return self.query_one("#chat-overlay-session-select", Select)
            except NoMatches:
                return None
        return menu.session_selector()

    def _stream_output(self) -> StreamingOutput | None:
        transcript = self._transcript()
        if transcript is None:
            try:
                return self.query_one("#chat-overlay-output", StreamingOutput)
            except NoMatches:
                return None
        return transcript.stream_output()

    def _status_bar(self) -> StatusBar | None:
        try:
            return self.query_one("#chat-overlay-status", StatusBar)
        except NoMatches:
            return None

    def set_chat_input_disabled(self, disabled: bool) -> None:
        if disabled:
            self._chat_input_disable_depth += 1
        else:
            self._chat_input_disable_depth = max(0, self._chat_input_disable_depth - 1)
        self._sync_input_enabled_state()
        self._refresh_status()

    def _sync_input_enabled_state(self) -> None:
        # Reachable from on_mount before all children are guaranteed; degrade
        # quietly when the input widget is absent in a partial-compose harness.
        input_widget = self._input_widget_safe()
        if input_widget is None:
            return
        visible = self.has_class("visible")
        locked = self._chat_input_disable_depth > 0
        should_disable = (not visible) or locked
        input_widget.disabled = should_disable
        input_widget.can_focus = not should_disable

    def _sync_completion_overlays(self, raw_value: str) -> None:
        self._sync_slash_complete(raw_value)
        self._sync_mention_complete(raw_value)
        # TODO(tui): add _sync_hash_mention_complete for kagan#/GitHub # tokens.
        # The ChatPanel Input widget uses tightly-coupled @-mention and slash
        # routing in on_key / _sync_completion_overlays.  A # trigger needs its
        # own overlay slot and a clean seam before it can coexist here safely.

    def _sync_slash_complete(self, raw_value: str) -> None:
        query = raw_value.strip()
        if not query.startswith("/"):
            self._hide_slash_complete()
            return

        query = query[1:]
        if any(ch.isspace() for ch in query):
            self._hide_slash_complete()
            return

        # Determine if we're in an orchestrator session
        is_orchestrator = (
            self._infer_session_kind(self._selected_session_key) == SessionKind.ORCHESTRATOR
        )

        seen: set[str] = set()
        matches: list[tuple[str, str]] = []
        # 1. Fuzzy-match against command names (filter orchestrator-only if not in orchestrator)
        for spec in SLASH_COMMAND_REGISTRY.specs():
            if spec.name not in _TUI_SLASH_COMMANDS:
                continue
            # Skip orchestrator-only commands in non-orchestrator sessions
            if spec.orchestrator_only and not is_orchestrator:
                continue
            if (not query or fuzzy_match(query.casefold(), spec.name)) and spec.name not in seen:
                seen.add(spec.name)
                matches.append((spec.name, spec.description))
        # 2. Exact alias match
        alias_target = _SLASH_ALIASES.get(query.casefold())
        if alias_target and alias_target in _TUI_SLASH_COMMANDS and alias_target not in seen:
            cmd = SLASH_COMMAND_REGISTRY.get(alias_target)
            # Skip alias if the target command is orchestrator-only and not in orchestrator session
            if cmd is not None and not (cmd.spec.orchestrator_only and not is_orchestrator):
                seen.add(alias_target)
                matches.append((alias_target, f"(alias) {cmd.spec.description}"))
        self._slash_matches = [name for name, _description in matches]
        if not matches:
            self._hide_slash_complete()
            return

        option_list = self.query_one("#slash-options", OptionList)
        option_list.clear_options()
        for name, description in matches:
            option_list.add_option(Option(f"/{name}  ·  {description}", id=name))
        option_list.highlighted = 0
        self.query_one("#slash-complete", Vertical).display = True

    def _sync_mention_complete(self, raw_value: str) -> None:
        mention = self._mention_span(raw_value)
        if mention is None:
            self._hide_mention_complete()
            return

        _start, _end, query = mention
        matches = self._mention_options(query)
        self._mention_matches = matches
        if not matches:
            self._hide_mention_complete()
            return

        option_list = self.query_one("#mention-options", OptionList)
        option_list.clear_options()
        for option in matches:
            option_list.add_option(Option(f"@{option.key}  ·  {option.label}", id=option.key))
        option_list.highlighted = 0
        self.query_one("#task-mention-complete", Vertical).display = True

    def _mention_options(self, query: str) -> list[SessionPickerOption]:
        normalized = query.casefold()
        options: list[SessionPickerOption] = []
        for label, key in self._session_options:
            option = SessionPickerOption(
                key=key,
                icon=self._session_icon(self._infer_session_kind(key)),
                label=label,
                search_text=f"{label} {key}",
            )
            haystack = f"{option.label} {option.key} {option.search_text}".casefold()
            if not normalized or normalized in haystack:
                options.append(option)
        return options

    def _apply_mention_completion(self) -> None:
        if not self._mention_matches:
            return
        option_list = self.query_one("#mention-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or highlighted < 0 or highlighted >= len(self._mention_matches):
            selected = self._mention_matches[0]
        else:
            selected = self._mention_matches[highlighted]

        input_widget = self._input_widget()
        mention = self._mention_span(input_widget.value)
        if mention is None:
            self._hide_mention_complete()
            return
        start, end, _query = mention
        input_widget.value = (
            f"{input_widget.value[:start]}@{selected.key} {input_widget.value[end:]}"
        )
        self._current_state().draft = input_widget.value
        input_widget.focus()
        self._hide_mention_complete()

    def _hide_slash_complete(self) -> None:
        self._slash_matches = []
        self.query_one("#slash-complete", Vertical).display = False

    def _hide_mention_complete(self) -> None:
        self._mention_matches = []
        self.query_one("#task-mention-complete", Vertical).display = False

    def _hide_overlays(self) -> None:
        self._hide_slash_complete()
        self._hide_mention_complete()

    def _sync_session_label(self) -> None:
        by_key = {key: label for label, key in self._session_options}
        label = by_key.get(self._selected_session_key, "Orchestrator")
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-session-current", Static).update(label)
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self._status_hint_override:
            status_bar = self._status_bar()
            if status_bar is None:
                return
            status_bar.update_status(self._runtime_status)
            status_bar.update_hint(self._status_hint_override)
            return

        split_key = self._overlay_split_key
        fullscreen_key = self._overlay_fullscreen_key
        close_key = self._overlay_close_key
        is_active = self._runtime_status in {"thinking", "initializing", "waiting"}
        if is_active:
            input_widget = self._input_widget_safe()
            value = input_widget.value if input_widget is not None else ""
            has_pending = bool(normalize_chat_input(value))
            esc_hint = "Esc stop+send" if has_pending else "Esc stop & edit last"
        else:
            esc_hint = f"{close_key} close"
        if bool(self._slash_matches or self._mention_matches):
            right = (
                f"Enter send · Tab complete · Ctrl+J timeline · "
                f"{split_key} split · {fullscreen_key} full · Ctrl+P files · Ctrl+K sessions · "
                f"Ctrl+C clear · {esc_hint}"
            )
        else:
            right = (
                f"Enter send · Up/Down history · Ctrl+J timeline · "
                f"{split_key} split · {fullscreen_key} full · Ctrl+P files · Ctrl+K sessions · "
                f"Ctrl+C clear · {esc_hint}"
            )
        status_bar = self._status_bar()
        if status_bar is None:
            return
        status_bar.update_status(self._runtime_status)
        status_bar.update_hint(right)

    def _append_prompt_history(self, text: str) -> None:
        cleaned = normalize_chat_input(text)
        if not cleaned:
            return
        state = self._current_state()
        if not state.prompt_history or state.prompt_history[-1] != cleaned:
            state.prompt_history.append(cleaned)
            state.prompt_history = state.prompt_history[-100:]
        state.history_index = None

    def _cycle_prompt_history(self, *, direction: Literal["up", "down"]) -> bool:
        state = self._current_state()
        if not state.prompt_history:
            return False
        if state.history_index is None:
            next_index = len(state.prompt_history) - 1 if direction == "up" else 0
        else:
            step = -1 if direction == "up" else 1
            next_index = (state.history_index + step) % len(state.prompt_history)
        state.history_index = next_index
        value = state.prompt_history[next_index]
        self._history_programmatic_update = True
        input_widget = self._input_widget()
        input_widget.value = value
        input_widget.focus()
        state.draft = value
        return True

    def _input_has_focus(self) -> bool:
        return self._input_widget().has_focus

    def _consume_session_prefix(self, text: str) -> tuple[str | None, str]:
        stripped = text.lstrip()
        if not stripped.startswith("@"):
            return None, text
        first, separator, remainder = stripped.partition(" ")
        alias = first[1:].strip()
        if not alias:
            return None, text
        key = self._resolve_session_alias(alias)
        if key is None:
            return None, text
        if not separator:
            return key, ""
        return key, normalize_chat_input(remainder)

    def _resolve_session_alias(self, alias: str) -> str | None:
        normalized = alias.casefold().replace("-", "").replace("_", "")
        for label, key in self._session_options:
            label_key = label.casefold().replace(" ", "").replace("-", "")
            session_key = key.casefold().replace("-", "").replace("_", "")
            if normalized in {label_key, session_key}:
                return key
        return None

    def _build_session_groups(self) -> list[SessionPickerGroup]:
        orchestrator: list[SessionPickerOption] = []
        task_targets_by_ticket: dict[str, list[SessionPickerOption]] = {}
        other: list[SessionPickerOption] = []

        # Filter by active project when available
        core = getattr(self.app, "core", None)
        active_project_id = getattr(core, "active_project_id", None) if core else None
        filtered_options = self._session_options
        if active_project_id is not None:
            project_keys = self._project_session_keys(active_project_id)
            if project_keys is not None:
                # Keep all non-chat sessions (task sessions are DB-scoped),
                # plus chat sessions matching the active project
                filtered_options = [
                    (label, key)
                    for label, key in self._session_options
                    if key == "orchestrator"
                    or key in project_keys
                    or self._infer_session_kind(key) != SessionKind.ORCHESTRATOR
                ]

        # Resolve source for each session key via the orchestrator store
        orch_store = getattr(core, "orchestrator_sessions", None) if core else None

        for label, key in filtered_options:
            kind = self._infer_session_kind(key)
            source = orch_store.source_for_key(key) if orch_store else ""
            option = SessionPickerOption(
                key=key,
                icon=self._session_icon(kind),
                label=label,
                search_text=f"{label} {key} {kind}",
                source=source,
            )
            if kind == SessionKind.ORCHESTRATOR:
                orchestrator.append(option)
            elif kind in {SessionKind.DETACHED, SessionKind.REVIEW, SessionKind.ATTACHED}:
                ticket_label = self._ticket_group_label(option.label)
                task_targets_by_ticket.setdefault(ticket_label, []).append(option)
            else:
                other.append(option)

        groups: list[SessionPickerGroup] = []
        if orchestrator:
            groups.append(
                SessionPickerGroup(
                    group_id="group:orchestrator",
                    icon="◎",
                    label="Orchestrator",
                    subtitle=f"{len(orchestrator)} target(s)",
                    search_text="orchestrator assistant global",
                    options=tuple(orchestrator),
                )
            )
        for ticket_label in sorted(task_targets_by_ticket):
            options = task_targets_by_ticket[ticket_label]
            groups.append(
                SessionPickerGroup(
                    group_id=f"group:ticket:{ticket_label.casefold().replace(' ', '-')}",
                    icon="◉",
                    label=ticket_label,
                    subtitle=f"{len(options)} agent(s)",
                    search_text=f"ticket task managed review interactive worktree {ticket_label}",
                    options=tuple(options),
                )
            )
        if other:
            groups.append(
                SessionPickerGroup(
                    group_id="group:other",
                    icon="●",
                    label="Other",
                    subtitle=f"{len(other)} target(s)",
                    search_text="other sessions",
                    options=tuple(other),
                )
            )
        return groups

    def _project_session_keys(self, project_id: str) -> set[str] | None:
        """Return session keys for the given project from the local cache.

        Returns ``None`` while the cache is cold so callers fall back to
        showing every session — the cache is populated asynchronously by
        :meth:`_refresh_project_session_keys`, which is kicked off on
        :class:`SessionChanged` and on mount. This avoids the legacy
        ``_db_sync`` call from a sync code path.
        """
        cached = self._project_session_keys_cache.get(project_id)
        if cached is None:
            # Kick off a background refresh so the next render of the picker
            # gets the filtered set. Does nothing if a refresh is in flight.
            self._kick_project_session_keys_refresh(project_id)
            return None
        return cached

    def _kick_project_session_keys_refresh(self, project_id: str) -> None:
        if not self.is_mounted:
            return
        # Use ``run_worker`` so concurrent kicks coalesce by name; Textual will
        # not start a duplicate worker with the same group.
        self.run_worker(
            self._refresh_project_session_keys(project_id),
            name=f"chat-project-session-keys-{project_id}",
            group=f"chat-project-session-keys-{project_id}",
            exit_on_error=False,
        )

    async def _refresh_project_session_keys(self, project_id: str) -> None:
        """Populate :attr:`_project_session_keys_cache` for ``project_id``.

        Reads from ``client.chat_sessions.list`` — the public aggregate seam
        that replaces the legacy ``_db_sync(Setting)`` raw read.
        """
        core = getattr(self.app, "core", None)
        if core is None:
            return
        try:
            rows = await core.chat_sessions.list(project_id=project_id)
        except Exception:
            return
        keys: set[str] = set()
        for row in rows:
            session_id = getattr(row, "id", None)
            if isinstance(session_id, str) and session_id:
                keys.add(f"orchestrator:{session_id}")
        self._project_session_keys_cache[project_id] = keys

    @staticmethod
    def _ticket_group_label(option_label: str) -> str:
        ticket_label, _separator, _role = option_label.partition(" · ")
        normalized = ticket_label.strip()
        return normalized or "Ticket"

    @staticmethod
    def _infer_session_kind(key: str) -> str:
        normalized = key.casefold()
        if "orchestrator" in normalized:
            return SessionKind.ORCHESTRATOR
        if "review" in normalized:
            return SessionKind.REVIEW
        if "interactive" in normalized or "attached" in normalized:
            return SessionKind.ATTACHED
        if "managed" in normalized:
            return SessionKind.DETACHED
        return SessionKind.DETACHED

    @staticmethod
    def _session_icon(kind: str) -> str:
        if kind == SessionKind.ORCHESTRATOR:
            return "◎"
        if kind == SessionKind.REVIEW:
            return "◆"
        if kind == SessionKind.ATTACHED:
            return "◌"
        if kind == SessionKind.DETACHED:
            return "◉"
        return "●"

    @staticmethod
    def _mention_span(value: str) -> tuple[int, int, str] | None:
        end = len(value)
        start = value.rfind("@")
        if start < 0:
            return None
        if start > 0 and not value[start - 1].isspace():
            return None
        query = value[start + 1 : end]
        if any(ch.isspace() for ch in query):
            return None
        return start, end, query
