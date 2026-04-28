from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from textual import on
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, OptionList, Static
from textual.widgets.option_list import Option

from kagan.cli.chat.sessions import build_chat_session_list_items, list_chat_sessions
from kagan.core.errors import KaganError

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.tui.app import KaganApp


@dataclass(frozen=True, slots=True)
class RecentSessionSelection:
    session_id: str
    project_id: str


class SessionResumeModal(ModalScreen[RecentSessionSelection | None]):
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self) -> None:
        super().__init__(id="session-resume-modal")
        self._sessions: list[RecentSessionSelection] = []

    @property
    def kagan_app(self) -> KaganApp:
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="session-resume-container"):
            yield Static("Resume Recent Session", classes="modal-title")
            yield Static(
                "Only sessions tied to a project are shown. "
                "Resuming reopens that project and chat history.",
                classes="modal-subtitle",
            )
            with Vertical(id="session-resume-body"):
                yield Static("Loading sessions…", id="session-resume-status")
                yield OptionList(id="session-resume-options")
            with Horizontal(id="session-resume-actions"):
                yield Button(
                    "Resume", id="session-resume-confirm", variant="primary", disabled=True
                )
                yield Button("Cancel", id="session-resume-cancel")
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        self.call_after_refresh(self._reload_sessions)

    async def _reload_sessions(self) -> None:
        option_list = self.query_one("#session-resume-options", OptionList)
        option_list.clear_options()
        self._sessions = []

        try:
            projects = await self.kagan_app.core.projects.list()
            project_names = {project.id: project.name for project in projects}
            sessions = await list_chat_sessions(self.kagan_app.core)
        except (KaganError, OSError, RuntimeError, ValueError):
            self.query_one("#session-resume-status", Static).update(
                "Recent sessions are unavailable right now."
            )
            option_list.display = False
            return

        recent_items = build_chat_session_list_items(sessions)
        for item in recent_items:
            project_id = item.project_id
            if not project_id:
                continue
            project_name = project_names.get(project_id)
            if project_name is None:
                continue
            self._sessions.append(
                RecentSessionSelection(session_id=item.session_id, project_id=project_id)
            )
            label = self._format_session_label(
                project_name, item.label, item.updated_relative, item.agent_backend, item.source
            )
            option_list.add_option(Option(label, id=item.session_id))

        if self._sessions:
            option_list.display = True
            option_list.highlighted = 0
            self.query_one("#session-resume-status", Static).update(
                "Pick a session to reopen its project and restored chat history."
            )
            self.query_one("#session-resume-confirm", Button).disabled = False
            option_list.focus()
            return

        option_list.display = False
        self.query_one("#session-resume-status", Static).update(
            "No resumable sessions yet. Only project-bound TUI sessions are shown here."
        )

    @staticmethod
    def _format_session_label(
        project_name: str,
        session_label: str,
        updated_relative: str,
        agent_backend: str | None,
        source: str = "",
    ) -> str:
        backend = f" · {agent_backend}" if agent_backend else ""
        updated = f" · {updated_relative}" if updated_relative else ""
        source_badge = (
            f" [$secondary][{source}][/]" if source else ""
        )
        return f"{project_name} · {session_label}{backend}{updated}{source_badge}"

    def _selected_session(self) -> RecentSessionSelection | None:
        option_list = self.query_one("#session-resume-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or highlighted < 0 or highlighted >= len(self._sessions):
            return None
        return self._sessions[highlighted]

    @on(OptionList.OptionSelected, "#session-resume-options")
    def _on_session_selected(self, _: OptionList.OptionSelected) -> None:
        self._resume_selected()

    @on(Button.Pressed, "#session-resume-confirm")
    def _on_resume_pressed(self) -> None:
        self._resume_selected()

    @on(Button.Pressed, "#session-resume-cancel")
    def _on_cancel_pressed(self) -> None:
        self.dismiss(None)

    def _resume_selected(self) -> None:
        selection = self._selected_session()
        if selection is None:
            return
        self.dismiss(selection)
