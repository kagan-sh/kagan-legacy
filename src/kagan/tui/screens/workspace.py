import asyncio
import contextlib
from typing import TYPE_CHECKING, cast

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from kagan.cli.chat import (
    ChatSessionListItem,
    resolve_default_agent_backend,
    warm_orchestrator_backend,
)
from kagan.core.enums import SessionKind, TaskStatus
from kagan.core.errors import KaganError
from kagan.tui._chat_helpers import TitleGenerationSession, kick_title_generation
from kagan.tui.keybindings import WORKSPACE_BINDINGS, get_key_for_action
from kagan.tui.screens._chat_runner import send_chat_message
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.widgets.chat import ChatPanel
from kagan.tui.widgets.header import KaganHeader

if TYPE_CHECKING:
    from kagan.core._session_items import SessionItem
    from kagan.tui.app import KaganApp


class _GroupHeader:
    __slots__ = ("group_key", "label")

    def __init__(self, label: str, group_key: str) -> None:
        self.label = label
        self.group_key = group_key


class WorkspaceScreen(Screen[None]):
    BINDINGS = WORKSPACE_BINDINGS

    def __init__(self) -> None:
        super().__init__(id="workspace-screen")
        self._chat_orchestrator_history: list[tuple[str, str]] = []
        self._chat_message_task: asyncio.Task[None] | None = None
        self._chat_session_switch_token = 0
        self._session_items: list[ChatSessionListItem] = []
        self._visible_session_items: list[ChatSessionListItem] = []
        self._footer_keys: dict[str, str] = {}
        self._unified_session_items: list[SessionItem] = []
        self._poll_task: asyncio.Task[None] | None = None
        self._row_map: list[ChatSessionListItem | _GroupHeader] = []

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        yield KaganHeader()
        with Horizontal(id="workspace-body"):
            with Vertical(id="workspace-sidebar"):
                with Vertical(id="workspace-sidebar-head"):
                    yield Static("Workspace", id="workspace-sidebar-title")
                    yield Static(
                        "Orchestrator conversations",
                        id="workspace-sidebar-subtitle",
                    )
                    yield Static(
                        "n new  / filter  Enter open",
                        id="workspace-sidebar-hint",
                    )
                    yield Static(
                        "Ctrl+W toggle mode",
                        id="workspace-sidebar-mode-hint",
                    )
                yield Input(
                    placeholder="Filter conversations",
                    id="workspace-search",
                )
                yield OptionList(id="workspace-session-list")
                yield Static(
                    "No conversations yet. Press n to start one.",
                    id="workspace-sidebar-empty",
                )
            with Vertical(id="workspace-main"):
                with Vertical(id="workspace-main-header"):
                    yield Static("Active conversation", id="workspace-main-eyebrow")
                    yield Static("No conversation selected", id="workspace-main-title")
                    yield Static(
                        "Select a conversation from the sidebar or press n to start one.",
                        id="workspace-main-subtitle",
                    )
                    yield Static(
                        "",
                        id="workspace-open-task",
                        classes="workspace-open-task",
                    )
                yield ChatPanel(id="workspace-chat", classes="workspace-chat")
        yield Static("", id="workspace-footer")

    async def on_mount(self) -> None:
        self._footer_keys = {
            "focus_search": get_key_for_action(WORKSPACE_BINDINGS, "focus_search", default="/"),
            "new_session": get_key_for_action(WORKSPACE_BINDINGS, "new_session", default="n"),
            "delete_session": get_key_for_action(WORKSPACE_BINDINGS, "delete_session", default="x"),
            "toggle_board": get_key_for_action(WORKSPACE_BINDINGS, "toggle_board", default="w"),
            "focus_chat": get_key_for_action(WORKSPACE_BINDINGS, "focus_chat", default="Ctrl+."),
            "switch_session": get_key_for_action(
                WORKSPACE_BINDINGS, "switch_session", default="Ctrl+K"
            ),
            "open_session": get_key_for_action(WORKSPACE_BINDINGS, "open_session", default="Enter"),
        }
        self._refresh_header()
        await self._refresh_header_context()
        self._update_footer()
        self.call_after_refresh(self._focus_sidebar)
        self.run_worker(
            self._warm_orchestrator_backend(),
            group="workspace-chat-warmup",
            exclusive=False,
            exit_on_error=False,
        )
        self._poll_task = asyncio.create_task(
            self._poll_unified_sessions(), name="workspace-session-poll"
        )

    async def on_chat_panel_ready(self, _: ChatPanel.Ready) -> None:
        panel = self.query_one(ChatPanel)
        panel.set_visible(True)
        panel.set_fullscreen(True)
        panel.set_mode_title("Workspace")
        panel.set_session_kind(SessionKind.ORCHESTRATOR)
        panel.set_status_hint_override(
            "Enter send · Shift+Enter newline · Ctrl+K sessions · Esc sidebar"
        )
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        await self._load_workspace_panel_state(panel)

    async def on_screen_resume(self) -> None:
        self.call_after_refresh(self._on_screen_resume_deferred)

    async def _on_screen_resume_deferred(self) -> None:
        await self.kagan_app.orchestrator_sessions.reload()
        panel = self.query_one(ChatPanel)
        await self._load_workspace_panel_state(panel)
        self._refresh_header()
        await self._refresh_header_context()
        self._focus_sidebar()

    async def on_unmount(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        if self._chat_message_task is not None:
            self._chat_message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._chat_message_task
            self._chat_message_task = None

        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError, NoMatches):
            panel = self.query_one(ChatPanel)
            await self.kagan_app.orchestrator_sessions.persist_active(
                history=self._chat_orchestrator_history,
                rendered_messages=panel.export_rendered_messages(),
                agent_backend=panel.preferred_agent_backend(),
            )

    def action_toggle_board(self) -> None:
        self.app.switch_screen("kanban-screen")

    def action_toggle_mode(self) -> None:
        self.app.switch_screen("kanban-screen")

    def action_back(self) -> None:
        self.action_toggle_board()

    def action_focus_search(self) -> None:
        self.query_one("#workspace-search", Input).focus()
        self._update_footer(self.query_one("#workspace-search", Input))

    def action_focus_chat(self) -> None:
        panel = self.query_one("#workspace-chat", ChatPanel)
        panel.query_one("#chat-overlay-input", Input).focus()
        self._update_footer(panel.query_one("#chat-overlay-input", Input))

    def _focus_sidebar(self) -> None:
        self.query_one("#workspace-session-list", OptionList).focus()
        self._update_footer(self.query_one("#workspace-session-list", OptionList))

    def action_switch_session(self) -> None:
        self.query_one(ChatPanel).action_open_session_picker()

    def action_open_settings(self) -> None:
        self.app.push_screen("settings-modal", callback=self._on_settings_dismissed)

    def action_open_session(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        if isinstance(row, _GroupHeader):
            if row.group_key == "__new_chat__":
                self._request_new_session_kind()
            return
        self._chat_session_switch_token += 1
        token = self._chat_session_switch_token
        self.run_worker(
            self._switch_orchestrator_session(
                self.query_one(ChatPanel),
                self._session_key_for_item(row),
                token=token,
                focus_chat=True,
            ),
            exit_on_error=False,
        )

    def action_new_session(self) -> None:
        self.run_worker(self._create_new_session(), exit_on_error=False)

    def _request_new_session_kind(self) -> None:
        def _on_kind(confirmed: bool) -> None:
            session_kind = "orchestrator" if confirmed else "general"
            self.run_worker(
                self._create_new_session(session_kind=session_kind),
                exit_on_error=False,
            )

        self.app.push_screen(
            ConfirmModal(
                title="New chat",
                message="Orchestrator session has Kagan tools. General chat is raw agent access.",
                confirm_label="Orchestrator",
                cancel_label="General",
            ),
            callback=_on_kind,
        )

    def action_delete_session(self) -> None:
        selected = self._selected_session_item()
        if selected is None:
            return

        def _on_confirm(confirmed: bool) -> None:
            if confirmed:
                self.run_worker(
                    self._delete_session(self._session_key_for_item(selected)),
                    exit_on_error=False,
                )

        self.app.push_screen(
            ConfirmModal(
                title="Delete Session",
                message=f"Delete '{selected.label}'?",
                confirm_label="Delete",
                cancel_label="Cancel",
            ),
            callback=_on_confirm,
        )

    @on(Input.Changed, "#workspace-search")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self._render_session_list(query=event.value)

    @on(events.DescendantFocus)
    def _on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self._update_footer(event.widget)

    async def on_key(self, event: events.Key) -> None:
        if event.key != "escape":
            return
        search = self.query_one("#workspace-search", Input)
        if self.focused is not search:
            return

        event.prevent_default()
        event.stop()
        if search.value:
            search.value = ""
            self._render_session_list(query="")
            self._update_footer(search)
            return

        self.query_one("#workspace-session-list", OptionList).focus()
        self._update_footer(self.query_one("#workspace-session-list", OptionList))

    @on(OptionList.OptionSelected, "#workspace-session-list")
    def _on_session_selected(self, _: OptionList.OptionSelected) -> None:
        self.action_open_session()

    async def on_chat_panel_submit_requested(self, message: ChatPanel.SubmitRequested) -> None:
        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()

        self._chat_message_task = asyncio.create_task(
            self._send_orchestrator_message(message.text),
            name="workspace-chat-orchestrator-send",
        )

    def on_chat_panel_session_changed(self, message: ChatPanel.SessionChanged) -> None:
        self._chat_orchestrator_history = self.kagan_app.orchestrator_sessions.history_for_key(
            message.key
        )
        self._chat_session_switch_token += 1
        token = self._chat_session_switch_token
        self.run_worker(
            self._switch_orchestrator_session(
                self.query_one(ChatPanel),
                message.key,
                token=token,
                focus_chat=True,
            ),
            exit_on_error=False,
        )

    def on_chat_panel_session_picker_requested(
        self, message: ChatPanel.SessionPickerRequested
    ) -> None:
        panel = self.query_one(ChatPanel)
        modal = panel.create_session_picker_modal(initial_query=message.initial_query)

        def _on_select(selected_key: str | None) -> None:
            if not selected_key:
                return
            self._chat_session_switch_token += 1
            token = self._chat_session_switch_token
            self.run_worker(
                self._switch_orchestrator_session(
                    panel,
                    selected_key,
                    token=token,
                    focus_chat=True,
                ),
                exit_on_error=False,
            )

        self.app.push_screen(modal, callback=_on_select)

    def on_chat_panel_file_picker_requested(self, message: ChatPanel.FilePickerRequested) -> None:
        panel = self.query_one(ChatPanel)
        modal = panel.create_file_picker_modal(initial_query=message.initial_query)
        self.app.push_screen(modal, callback=panel.handle_file_picker_selected)

    def on_chat_panel_agent_picker_requested(
        self, _message: ChatPanel.AgentPickerRequested
    ) -> None:
        panel = self.query_one(ChatPanel)

        def _on_agent_selected(selected: str | None) -> None:
            if not selected:
                return
            panel.set_preferred_agent_backend(selected)
            panel.add_system_message(f"Default agent set to {selected}")
            self._refresh_header_backend(selected)
            self.run_worker(
                self._persist_session_backend(selected),
                group="workspace-chat-persist",
                exclusive=False,
                exit_on_error=False,
            )
            self.run_worker(
                self._warm_orchestrator_backend(selected),
                group="workspace-chat-warmup",
                exclusive=False,
                exit_on_error=False,
            )

        self.app.push_screen("agent-picker-modal", callback=_on_agent_selected)

    def on_chat_panel_interrupt_requested(self, _: ChatPanel.InterruptRequested) -> None:
        panel = self.query_one("#workspace-chat", ChatPanel)
        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()
        panel.post_message(ChatPanel.InterruptCompleted())

    def on_chat_panel_new_session_requested(self, _: ChatPanel.NewSessionRequested) -> None:
        self.action_new_session()

    def on_chat_panel_close_requested(self, _: ChatPanel.CloseRequested) -> None:
        self.query_one("#workspace-session-list", OptionList).focus()
        self._update_footer(self.query_one("#workspace-session-list", OptionList))

    async def _send_orchestrator_message(self, text: str) -> None:
        panel = self.query_one(ChatPanel)
        should_title = self.kagan_app.orchestrator_sessions.should_generate_title()
        try:
            self._chat_orchestrator_history = await send_chat_message(
                core=self.kagan_app.core,
                panel=panel,
                text=text,
                history=self._chat_orchestrator_history,
            )
            await self.kagan_app.orchestrator_sessions.persist_active(
                history=self._chat_orchestrator_history,
                rendered_messages=panel.export_rendered_messages(),
                agent_backend=panel.preferred_agent_backend(),
            )
            self._render_session_list(prefer_key=self.kagan_app.orchestrator_sessions.active_key())
            if should_title and self._chat_orchestrator_history:
                asyncio.create_task(
                    self._refresh_generated_title(text),
                    name="workspace-chat-title-gen",
                )
        except asyncio.CancelledError:
            panel.set_runtime_status("ready")
            panel.set_stream_action("Waiting for prompt", confidence="certain")
            raise
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            panel.set_runtime_status("error")
            panel.set_stream_action("Orchestrator error", confidence="needs-validation")
            panel.add_system_message(f"Orchestrator error: {exc}")

    async def _refresh_generated_title(self, user_message: str) -> None:
        panel = self.query_one(ChatPanel)
        await kick_title_generation(
            TitleGenerationSession(
                orchestrator_sessions=self.kagan_app.orchestrator_sessions,
                panel=panel,
                user_message=user_message,
                history=self._chat_orchestrator_history,
                session_options=self.kagan_app.orchestrator_sessions.options(),
                is_mounted=lambda: self.is_mounted,
            ),
            self.kagan_app.core,
        )
        if self.is_mounted:
            self._render_session_list(prefer_key=self.kagan_app.orchestrator_sessions.active_key())

    async def _switch_orchestrator_session(
        self,
        panel: ChatPanel,
        key: str,
        *,
        token: int | None = None,
        focus_chat: bool = False,
    ) -> None:
        if token is not None and token != self._chat_session_switch_token:
            return
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=panel.preferred_agent_backend(),
        )
        if token is not None and token != self._chat_session_switch_token:
            return
        await self._load_workspace_panel_state(
            panel,
            requested_key=key,
            focus_chat=focus_chat,
        )
        if token is not None and token != self._chat_session_switch_token:
            return
        self.run_worker(
            self._warm_orchestrator_backend(panel.preferred_agent_backend()),
            group="workspace-chat-warmup",
            exclusive=False,
            exit_on_error=False,
        )

    async def _create_new_session(self, session_kind: str = "orchestrator") -> None:
        panel = self.query_one(ChatPanel)
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=panel.preferred_agent_backend(),
        )
        next_key = await self.kagan_app.orchestrator_sessions.create_new(
            agent_backend=panel.preferred_agent_backend(),
            session_type=session_kind,
        )
        await self._load_workspace_panel_state(panel, requested_key=next_key, focus_chat=True)
        panel.add_system_message("New session started.")

    async def _delete_session(self, key: str) -> None:
        panel = self.query_one(ChatPanel)
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=panel.preferred_agent_backend(),
        )
        next_key = await self.kagan_app.orchestrator_sessions.delete(key)
        if next_key is None:
            return
        await self._load_workspace_panel_state(panel, requested_key=next_key)
        panel.add_system_message("Session deleted.")

    async def _load_workspace_panel_state(
        self,
        panel: ChatPanel,
        *,
        requested_key: str | None = None,
        focus_chat: bool = False,
    ) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        if requested_key is not None:
            self._chat_orchestrator_history = await self.kagan_app.orchestrator_sessions.switch(
                requested_key
            )
        else:
            self._chat_orchestrator_history = self.kagan_app.orchestrator_sessions.active_history()

        active_key = self.kagan_app.orchestrator_sessions.active_key()
        panel.set_sessions(self.kagan_app.orchestrator_sessions.options(), active_key)
        panel.hydrate_current_session_history(self._chat_orchestrator_history)
        session_backend = self.kagan_app.orchestrator_sessions.agent_backend_for_key(active_key)
        panel.set_preferred_agent_backend(session_backend)
        self._refresh_header_backend(session_backend or "")
        self._render_session_list(prefer_key=active_key)
        self._refresh_main_header(active_key)
        # Update composer context with access mode and branch
        branch = self.query_one(KaganHeader).git_branch or ""
        panel.set_composer_context(access_mode="Full", branch=f"  {branch}" if branch else "")
        if focus_chat:
            self.call_after_refresh(self.action_focus_chat)

    async def _persist_session_backend(self, backend: str) -> None:
        panel = self.query_one(ChatPanel)
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=backend,
        )
        self._render_session_list(prefer_key=self.kagan_app.orchestrator_sessions.active_key())

    async def _warm_orchestrator_backend(self, preferred_backend: str | None = None) -> None:
        panel = self.query_one(ChatPanel)
        settings = await self.kagan_app.core.settings.get()
        backend = (
            preferred_backend
            or panel.preferred_agent_backend()
            or resolve_default_agent_backend(settings)
        )
        if not backend.strip():
            return
        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
            await warm_orchestrator_backend(self.kagan_app.core, agent_backend=backend)

    def _render_session_list(
        self,
        *,
        query: str | None = None,
        prefer_key: str | None = None,
    ) -> None:
        self._session_items = self.kagan_app.orchestrator_sessions.list_items()
        if query is not None:
            normalized_query = query
        else:
            normalized_query = self.query_one("#workspace-search", Input).value
        needle = normalized_query.strip().lower()

        option_list = self.query_one("#workspace-session-list", OptionList)
        subtitle = self.query_one("#workspace-sidebar-subtitle", Static)
        option_list.clear_options()
        self._row_map = []

        # "+ New chat" button at top
        option_list.add_option(Option("[+ New chat]", id="__new_chat__"))
        self._row_map.append(_GroupHeader("[+ New chat]", "__new_chat__"))

        # Group orchestrator sessions by project
        groups: dict[str, list[ChatSessionListItem]] = {}
        ungrouped: list[ChatSessionListItem] = []
        for item in self._session_items:
            pid = (item.project_id or "").strip()
            if pid:
                groups.setdefault(pid, []).append(item)
            else:
                ungrouped.append(item)

        active_key = prefer_key or self.kagan_app.orchestrator_sessions.active_key()

        # Render project groups
        project_name = self.kagan_app.project.name if self.kagan_app.project else "Sessions"
        project_id = self.kagan_app.project.id if self.kagan_app.project else ""

        if groups or ungrouped:
            # Project header
            option_list.add_option(Option(f"▸ {project_name}", id=f"__group__{project_id}"))
            self._row_map.append(_GroupHeader(project_name, f"__group__{project_id}"))

        # Orchestrator sessions under project
        all_items = list(ungrouped)
        for _pid, items in groups.items():
            all_items.extend(items)

        if needle:
            filtered = [
                item
                for item in all_items
                if needle in item.label.lower()
                or needle in item.session_id.lower()
                or needle in (item.agent_backend or "").lower()
            ]
        else:
            filtered = all_items

        self._visible_session_items = filtered

        for item in filtered:
            is_active = self._session_key_for_item(item) == active_key
            prefix = "  ●" if is_active else "  ◇"
            label = f"{prefix} {item.label}"
            ts = item.updated_relative or ""
            if ts:
                label += f"  [dim]{ts}[/]"
            opt_id = f"__session__{item.session_id}"
            option_list.add_option(Option(label, id=opt_id))
            self._row_map.append(item)

        # Task sessions from unified list
        task_items = [si for si in self._unified_session_items if si.type == "task"]
        if task_items:
            option_list.add_option(Option("▸ Task sessions", id="__group__tasks"))
            self._row_map.append(_GroupHeader("Task sessions", "__group__tasks"))
            for ti in task_items:
                label = ti.title or ti.id
                if needle and needle not in label.lower():
                    continue
                ts_short = ti.updated_at[:10] if ti.updated_at else ""
                glyph = "▶" if ti.role == "worker" else "◈"
                row_label = f"  {glyph} {label}"
                if ts_short:
                    row_label += f"  [dim]{ts_short}[/]"
                option_list.add_option(Option(row_label, id=f"__task__{ti.id}"))
                self._row_map.append(_GroupHeader(label, f"__task__{ti.id}"))

        # Manage visibility
        visible_count = len(all_items) + len(task_items)
        if needle:
            visible_count = len(filtered) + (
                sum(1 for ti in task_items if needle in (ti.title or ti.id).lower())
            )
        if visible_count > 0:
            option_list.display = True
            self.query_one("#workspace-sidebar-empty", Static).display = False
            if needle:
                subtitle.update(
                    f"{visible_count} of {len(self._session_items)} conversations + tasks"
                )
            else:
                noun = "item" if visible_count == 1 else "items"
                subtitle.update(f"{visible_count} {noun}")
            # Highlight active session
            active_index = 0
            for index, item in enumerate(filtered):
                if self._session_key_for_item(item) == active_key:
                    active_index = index + 2  # offset for new_chat + group header
                    break
            if active_index < option_list.option_count:
                option_list.highlighted = active_index
        else:
            option_list.display = False
            empty = self.query_one("#workspace-sidebar-empty", Static)
            empty.update(
                "No matching conversations. Clear search or press n to start one."
                if needle
                else "No conversations yet. Press n to start one."
            )
            empty.display = True
            subtitle.update("No matching conversations" if needle else "No conversations")

    async def _poll_unified_sessions(self) -> None:
        while True:
            await asyncio.sleep(3.0)
            if not self.is_mounted:
                return
            try:
                from kagan.tui.app import KaganApp

                app = self.app
                if not isinstance(app, KaganApp):
                    continue
                project_id = app.project.id if app.project else None
                items = await app.core.list_session_items(project_id=project_id)
                self._unified_session_items = items
                self.call_after_refresh(self._re_render_if_idle)
            except Exception:
                pass

    def _re_render_if_idle(self) -> None:
        if not self.is_mounted:
            return
        self._render_session_list()

    def _selected_session_item(self) -> ChatSessionListItem | None:
        option_list = self.query_one("#workspace-session-list", OptionList)
        highlighted = option_list.highlighted if option_list.highlighted is not None else 0
        if highlighted < 0 or highlighted >= len(self._row_map):
            return None
        row = self._row_map[highlighted]
        if isinstance(row, ChatSessionListItem):
            return row
        return None

    def _selected_row(self) -> ChatSessionListItem | _GroupHeader | None:
        option_list = self.query_one("#workspace-session-list", OptionList)
        highlighted = option_list.highlighted if option_list.highlighted is not None else 0
        if highlighted < 0 or highlighted >= len(self._row_map):
            return None
        return self._row_map[highlighted]

    def _session_key_for_item(self, item: ChatSessionListItem) -> str:
        return f"orchestrator:{item.session_id}"

    def _active_session_item(self, active_key: str | None = None) -> ChatSessionListItem | None:
        session_key = active_key or self.kagan_app.orchestrator_sessions.active_key()
        for item in self._session_items:
            if self._session_key_for_item(item) == session_key:
                return item
        return None

    def _refresh_header(self) -> None:
        header = self.query_one(KaganHeader)
        project = self.kagan_app.project
        header.update_project(project.name if project is not None else "No project")
        header.update_repo(self.kagan_app.selected_repo_name or "")
        header.update_mode("chat")
        header.update_sessions(0)

    async def _refresh_header_context(self) -> None:
        from kagan.core import git

        header = self.query_one(KaganHeader)
        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
            tasks = await self.kagan_app.core.tasks.list()
            header.update_count(len(tasks))
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

    def _refresh_header_backend(self, backend: str) -> None:
        self.query_one(KaganHeader).update_backend(backend)
        self._refresh_main_header()

    def _refresh_main_header(self, active_key: str | None = None) -> None:
        title = self.query_one("#workspace-main-title", Static)
        subtitle = self.query_one("#workspace-main-subtitle", Static)
        task_btn = self.query_one("#workspace-open-task", Static)
        item = self._active_session_item(active_key)
        if item is None:
            title.update("No conversation selected")
            subtitle.update("Select a conversation from the sidebar or press n to start one.")
            task_btn.display = False
            return

        title.update(item.label)
        parts: list[str] = []
        if item.agent_backend:
            parts.append(item.agent_backend)
        if item.updated_relative:
            parts.append(f"updated {item.updated_relative}")
        parts.append("Ctrl+. to type")
        parts.append("Esc to step back")
        subtitle.update(" · ".join(parts))
        task_btn.display = False

    def _update_footer(self, focused: Widget | None = None) -> None:
        keys = {
            "focus_search": get_key_for_action(WORKSPACE_BINDINGS, "focus_search", default="/"),
            "new_session": get_key_for_action(WORKSPACE_BINDINGS, "new_session", default="n"),
            "toggle_board": get_key_for_action(WORKSPACE_BINDINGS, "toggle_board", default="w"),
            "focus_chat": get_key_for_action(WORKSPACE_BINDINGS, "focus_chat", default="Ctrl+."),
            "switch_session": get_key_for_action(
                WORKSPACE_BINDINGS, "switch_session", default="Ctrl+K"
            ),
            "open_session": get_key_for_action(WORKSPACE_BINDINGS, "open_session", default="Enter"),
        }
        new_key = keys["new_session"]
        search_key = keys["focus_search"]
        board_key = keys["toggle_board"]
        switch_key = keys["switch_session"]
        open_key = keys["open_session"]

        widget = focused or self.focused
        search = self.query_one("#workspace-search", Input)
        chat = self.query_one("#workspace-chat", ChatPanel)

        if widget is search:
            footer = (
                f"Type to filter  {board_key} board  Esc clear"
                if search.value
                else f"Type to filter  {open_key} open  Esc list"
            )
        elif widget is not None and chat in widget.ancestors:
            footer = (
                f"{open_key} send  Shift+Enter newline  "
                f"{switch_key} sessions  Esc sidebar  Ctrl+W mode"
            )
        else:
            footer = (
                f"j/k nav  {search_key} search  {new_key} new  "
                f"Ctrl+W view  {switch_key} palette  Esc back"
            )

        self.query_one("#workspace-footer", Static).update(footer)

    def _on_settings_dismissed(self, _result: None) -> None:
        from kagan.tui.app import KaganApp

        app = self.app
        if isinstance(app, KaganApp):
            app.run_worker(app._apply_saved_theme(), exclusive=False)
