from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.widgets import Static

from kagan.core.domain.enums import TaskStatus
from kagan.tui.keybindings import (
    HELP_BINDINGS,
    KANBAN_BINDINGS,
    ONBOARDING_BINDINGS,
    WELCOME_BINDINGS,
    get_key_for_action,
)
from kagan.tui.ui.modals.help import HelpModal
from kagan.tui.ui.screens.kanban.board_controller import (
    KanbanBoardController,
    build_search_filter_hint,
)
from kagan.tui.ui.screens.kanban.commands import KANBAN_ACTIONS, KanbanActionId
from kagan.tui.ui.screens.kanban.hints import build_kanban_hints
from kagan.tui.ui.screens.kanban.screen import KanbanScreen
from kagan.tui.ui.screens.welcome import WelcomeScreen


def _help_key_rows(query: str = "") -> set[tuple[str, str]]:
    rows: set[tuple[str, str]] = set()
    content = HelpModal()._compose_keybindings(query)
    for child in content._pending_children:
        if not isinstance(child, Horizontal) or "help-key-row" not in child.classes:
            continue
        key = ""
        desc = ""
        for cell in child._pending_children:
            if not isinstance(cell, Static):
                continue
            if "help-key" in cell.classes:
                key = str(getattr(cell, "_Static__content", ""))
            elif "help-desc" in cell.classes:
                desc = str(getattr(cell, "_Static__content", ""))
        rows.add((key, desc))
    return rows


class _HintStub:
    def __init__(self) -> None:
        self.value = ""
        self.classes: set[str] = set()

    def update(self, value: str) -> None:
        self.value = value

    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_class(self, name: str) -> None:
        self.classes.discard(name)


class _ReviewHintScreenStub:
    def __init__(self) -> None:
        self._tasks = [
            SimpleNamespace(status=TaskStatus.REVIEW),
            SimpleNamespace(status=TaskStatus.REVIEW),
        ]
        self.hint = _HintStub()

    def query_one(self, selector: str, _type: object = None) -> _HintStub:
        if selector != "#review-queue-hint":
            raise NoMatches(selector)
        return self.hint


class _WelcomeAppStub:
    def __init__(
        self,
        *,
        open_result: bool,
        modal_result: dict | None = None,
        confirm_result: bool = True,
    ) -> None:
        self.open_project_session = AsyncMock(return_value=open_result)
        self.exit_called = False
        self.modal_result = modal_result
        self.confirm_result = confirm_result
        self.worker_runs = 0

    def exit(self) -> None:
        self.exit_called = True

    def push_screen(self, _screen: object, callback) -> None:
        callback(self.modal_result)

    async def push_screen_wait(self, _screen: object) -> object:
        return self.confirm_result

    def run_worker(self, awaitable, **kwargs: object) -> None:
        del kwargs
        self.worker_runs += 1
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()


class _WelcomeScreenForTest(WelcomeScreen):
    def __init__(self, *, ctx: object, app: object) -> None:
        super().__init__()
        self._ctx_test = ctx
        self._app_test = app
        self.notifications: list[tuple[str, str]] = []

    @property
    def ctx(self) -> object:
        return self._ctx_test

    @property
    def kagan_app(self) -> object:
        return self._app_test

    @property
    def app(self) -> object:
        return self._app_test

    def notify(self, message: str, *, severity: str = "information", **kwargs: object) -> None:
        del kwargs
        self.notifications.append((message, severity))


def test_enter_maps_to_details_and_o_maps_to_open_session() -> None:
    assert get_key_for_action(KANBAN_BINDINGS, "view_details") == "Enter"
    assert get_key_for_action(KANBAN_BINDINGS, "open_session") == "o"
    assert get_key_for_action(KANBAN_BINDINGS, "move_backward") == "Shift+Left"
    assert get_key_for_action(KANBAN_BINDINGS, "move_forward") == "Shift+Right"
    assert get_key_for_action(KANBAN_BINDINGS, "switch_global_agent") == "Ctrl+A / Shift+A"


def test_enter_key_dispatches_view_details_on_board(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = KanbanScreen()
    dispatched: list[KanbanActionId] = []

    def _no_overlay(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise NoMatches("#chat-overlay")

    def _dispatch(action: KanbanActionId) -> bool:
        dispatched.append(action)
        return True

    focused_card = SimpleNamespace(task_model=SimpleNamespace(id="task-1"))

    event = SimpleNamespace(key="enter", stopped=False)

    def _stop() -> None:
        event.stopped = True

    event.stop = _stop
    monkeypatch.setattr(screen, "query_one", _no_overlay)
    monkeypatch.setattr(screen, "_dispatch_kanban_action", _dispatch)
    monkeypatch.setattr(screen, "get_focused_card", lambda: focused_card)

    screen.on_key(event)

    assert dispatched == [KanbanActionId.VIEW_DETAILS]
    assert event.stopped is True


def test_search_no_results_hint_includes_explicit_guidance() -> None:
    message = build_search_filter_hint(
        query="missing phrase",
        filtered_count=0,
        clear_key="Esc",
        hide_key="/",
    )
    assert 'No tasks match "missing phrase".' in message
    assert "Try fewer words or a broader term." in message
    assert "Esc clear, / hide." in message


def test_search_hint_has_priority_over_review_queue_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = _ReviewHintScreenStub()
    controller = KanbanBoardController(screen=screen)  # type: ignore[arg-type]
    monkeypatch.setattr(controller, "_search_hint_message", lambda: "Search active")

    controller.update_review_queue_hint()

    assert screen.hint.value == "Search active"
    assert "visible" in screen.hint.classes


class _EmptyBoardScreenStub:
    def __init__(self) -> None:
        self._tasks: list[SimpleNamespace] = []
        self.search_visible = False
        self.hint = _HintStub()
        self.kagan_app = SimpleNamespace(
            config=SimpleNamespace(ui=SimpleNamespace(show_beginner_hints=True))
        )

    def query_one(self, selector: str, _type: object = None) -> _HintStub:
        if selector != "#review-queue-hint":
            raise NoMatches(selector)
        return self.hint


def test_empty_board_hint_shows_plain_language_quick_start() -> None:
    screen = _EmptyBoardScreenStub()
    controller = KanbanBoardController(screen=screen)  # type: ignore[arg-type]

    controller.update_review_queue_hint()

    assert "Quick start:" in screen.hint.value
    assert "new task" in screen.hint.value
    assert "search" in screen.hint.value
    assert "assistant" in screen.hint.value
    assert "docked" in screen.hint.value
    assert "actions" in screen.hint.value
    assert "help" in screen.hint.value
    assert "visible" in screen.hint.classes


def test_global_kanban_hint_row_contains_novice_friendly_shortcuts() -> None:
    hints = build_kanban_hints(None, None)
    assert hints.global_hints == [
        ("n", "new"),
        ("/", "search"),
        ("Enter", "details"),
        ("Ctrl+P", "assistant"),
        (".", "actions"),
        ("?", "help"),
    ]


def test_help_modal_uses_ai_assistant_labels_and_updated_board_keys() -> None:
    rows = _help_key_rows()
    assert ("Enter", "View task details") in rows
    assert ("o", "Open task workspace/output") in rows
    assert ("Shift+Left / Shift+H", "Move task left") in rows
    assert ("Shift+Right / Shift+L", "Move task right") in rows
    assert ("Ctrl+P", "Toggle fullscreen AI Assistant") in rows
    assert ("Ctrl+O", "Toggle docked AI Assistant") in rows
    assert ("Tab", "Cycle active scoped sessions (opens picker when single target)") in rows
    assert ("Ctrl+K", "Open session quick-pick") in rows
    assert all("orchestrator" not in desc.lower() for _, desc in rows)


def test_help_bindings_include_search_shortcut() -> None:
    assert get_key_for_action(HELP_BINDINGS, "focus_search") == "Ctrl+F"


def test_help_modal_search_filters_keybindings_case_insensitively() -> None:
    rows = _help_key_rows("DeLeTe")
    assert ("x", "Delete task") in rows
    assert all(
        ("delete" in key.casefold()) or ("delete" in description.casefold())
        for key, description in rows
    )


def test_help_modal_escape_clears_search_before_close() -> None:
    modal = HelpModal()
    dismissed: list[None] = []

    def _fake_dismiss(result: None = None) -> None:
        dismissed.append(result)

    setattr(modal, "dismiss", _fake_dismiss)  # type: ignore[method-assign]

    modal._search_query = "delete"
    modal.action_close()

    assert modal._search_query == ""
    assert dismissed == []

    modal.action_close()
    assert dismissed == [None]


def test_kanban_command_descriptions_use_ai_assistant_language() -> None:
    command_help = {action.command: action.help for action in KANBAN_ACTIONS}
    assert command_help["board ai assistant"] == "Toggle docked AI Assistant overlay (Ctrl+O)"
    assert (
        command_help["board ai assistant docked"] == "Toggle docked AI Assistant overlay (Ctrl+O)"
    )
    assert (
        command_help["board ai assistant fullscreen"]
        == "Toggle fullscreen AI Assistant overlay (Ctrl+P)"
    )


def test_welcome_navigation_bindings_expose_arrow_and_tab_defaults() -> None:
    assert get_key_for_action(WELCOME_BINDINGS, "move_selection_up") == "Up / k"
    assert get_key_for_action(WELCOME_BINDINGS, "move_selection_down") == "Down / j"
    assert get_key_for_action(WELCOME_BINDINGS, "focus_next") == "Tab"
    assert get_key_for_action(WELCOME_BINDINGS, "focus_previous") == "Shift+Tab"


def test_welcome_empty_state_message_guides_first_run_actions() -> None:
    message = WelcomeScreen._default_empty_state_message()
    assert "No recent projects yet." in message
    assert "Press n" in message
    assert "open a folder" in message


def test_welcome_new_project_cancel_shows_confirmation_message() -> None:
    app_stub = _WelcomeAppStub(open_result=True, modal_result=None)
    screen = _WelcomeScreenForTest(
        ctx=SimpleNamespace(active_project_id=None, active_repo_id=None),
        app=app_stub,
    )

    screen.action_new_project()

    assert ("Project setup canceled", "information") in screen.notifications
    assert app_stub.worker_runs == 0


def test_welcome_new_project_create_shows_confirmation_message() -> None:
    app_stub = _WelcomeAppStub(open_result=True, modal_result={"project_id": "project-1"})
    screen = _WelcomeScreenForTest(
        ctx=SimpleNamespace(active_project_id=None, active_repo_id=None),
        app=app_stub,
    )

    screen.action_new_project()

    assert ("Project created. Opening board...", "success") in screen.notifications
    assert app_stub.worker_runs == 1


def test_help_modal_documents_welcome_arrow_and_tab_navigation() -> None:
    rows = _help_key_rows()
    assert ("Up / Down or j / k", "Move project selection") in rows
    assert ("Tab / Shift+Tab", "Move focus to next/previous control") in rows
    assert ("Ctrl+P / Ctrl+O", "After opening a board: fullscreen/docked AI Assistant") in rows


def test_onboarding_bindings_include_tab_submit_and_escape_defaults() -> None:
    assert get_key_for_action(ONBOARDING_BINDINGS, "focus_next") == "Tab"
    assert get_key_for_action(ONBOARDING_BINDINGS, "focus_previous") == "Shift+Tab"
    assert get_key_for_action(ONBOARDING_BINDINGS, "continue_setup") == "Enter"
    assert get_key_for_action(ONBOARDING_BINDINGS, "quit") == "Esc"


def test_help_modal_documents_onboarding_navigation_and_submit() -> None:
    rows = _help_key_rows()
    assert ("Tab / Shift+Tab", "Move focus between setup controls") in rows
    assert ("Enter / Ctrl+S", "Save setup and continue") in rows
    assert ("Esc", "Quit") in rows


@pytest.mark.asyncio
async def test_welcome_escape_returns_to_board_context_when_opened_from_board() -> None:
    app_stub = _WelcomeAppStub(open_result=True)
    screen = _WelcomeScreenForTest(
        ctx=SimpleNamespace(active_project_id="project-1", active_repo_id="repo-1"),
        app=app_stub,
    )

    await screen.action_quit()

    app_stub.open_project_session.assert_awaited_once_with(
        "project-1",
        preferred_repo_id="repo-1",
        allow_picker=False,
        screen_mode="switch",
    )
    assert app_stub.exit_called is False


@pytest.mark.asyncio
async def test_welcome_escape_does_not_quit_when_board_return_fails() -> None:
    app_stub = _WelcomeAppStub(open_result=False)
    screen = _WelcomeScreenForTest(
        ctx=SimpleNamespace(active_project_id="project-1", active_repo_id="repo-1"),
        app=app_stub,
    )

    await screen.action_quit()

    app_stub.open_project_session.assert_awaited_once()
    assert app_stub.exit_called is False
    assert screen.notifications == [("Unable to return to board right now", "warning")]


@pytest.mark.asyncio
async def test_welcome_escape_quits_when_no_board_context_exists() -> None:
    app_stub = _WelcomeAppStub(open_result=False, confirm_result=True)
    screen = _WelcomeScreenForTest(
        ctx=SimpleNamespace(active_project_id=None, active_repo_id=None),
        app=app_stub,
    )

    await screen.action_quit()

    app_stub.open_project_session.assert_not_called()
    assert app_stub.exit_called is True


@pytest.mark.asyncio
async def test_welcome_escape_cancel_does_not_quit() -> None:
    app_stub = _WelcomeAppStub(open_result=False, confirm_result=False)
    screen = _WelcomeScreenForTest(
        ctx=SimpleNamespace(active_project_id=None, active_repo_id=None),
        app=app_stub,
    )

    await screen.action_quit()

    app_stub.open_project_session.assert_not_called()
    assert app_stub.exit_called is False
