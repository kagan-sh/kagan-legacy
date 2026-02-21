from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, OptionList, Rule, Static

from kagan.core.config import KaganConfig
from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType
from kagan.tui.ui.modals.settings import PersonaField, SettingsModal
from kagan.tui.ui.modals.task_details_modal import TaskDetailsModal

if TYPE_CHECKING:
    from textual.screen import ModalScreen


def _task_view_stub() -> SimpleNamespace:
    return SimpleNamespace(
        id="task-123",
        short_id="task-123",
        title="Refine modal UX",
        description="Refine modal layouts",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.BACKLOG,
        task_type=TaskType.PAIR,
        acceptance_criteria=[],
        base_branch=None,
        created_at="2026-02-21T13:28:00",
        updated_at="2026-02-21T13:30:00",
        project_id="project-1",
        agent_backend="claude",
        terminal_backend="tmux",
    )


class _TaskDetailsModalForTest(TaskDetailsModal):
    def __init__(self, *, task: SimpleNamespace, list_workspaces: AsyncMock) -> None:
        super().__init__(task=task)
        self._ctx_test = SimpleNamespace(
            api=SimpleNamespace(list_workspaces=list_workspaces),
            active_repo_id=None,
        )

    @property
    def ctx(self) -> SimpleNamespace:
        return self._ctx_test


class _TaskDetailsModalLayoutOnly(TaskDetailsModal):
    """Modal variant for composition assertions without async data loaders."""

    def on_mount(self) -> None:
        return


class _ModalHostApp(App[None]):
    def __init__(self, modal: ModalScreen[object]) -> None:
        super().__init__()
        self._modal = modal

    def compose(self) -> ComposeResult:
        yield Static("")

    def on_mount(self) -> None:
        self.push_screen(self._modal)


@pytest.mark.asyncio
async def test_task_details_sections_use_spacing_not_extra_rules() -> None:
    modal = _TaskDetailsModalLayoutOnly(task=_task_view_stub())
    app = _ModalHostApp(modal)

    async with app.run_test(size=(120, 40)) as pilot:
        del pilot
        mounted = app.screen
        assert isinstance(mounted, TaskDetailsModal)

        workspace_section = mounted.query_one("#workspace-repos-section", Vertical)
        github_section = mounted.query_one("#github-section", Vertical)

        assert list(workspace_section.query(Rule)) == []
        assert list(github_section.query(Rule)) == []

        connect_button = mounted.query_one("#connect-github-btn", Button)
        assert connect_button.id == "connect-github-btn"


@pytest.mark.asyncio
async def test_task_details_action_hints_use_single_full_width_label() -> None:
    modal = _TaskDetailsModalLayoutOnly(task=_task_view_stub())
    app = _ModalHostApp(modal)

    async with app.run_test(size=(120, 40)) as pilot:
        del pilot
        mounted = app.screen
        assert isinstance(mounted, TaskDetailsModal)

        view_row = mounted.query_one("#view-buttons")
        view_children = [child for child in view_row.children if isinstance(child, Static)]
        assert len(view_children) == 1
        assert "modal-action-hint" in view_children[0].classes

        edit_row = mounted.query_one("#edit-buttons")
        edit_children = [child for child in edit_row.children if isinstance(child, Static)]
        assert len(edit_children) == 1
        assert "modal-action-hint" in edit_children[0].classes
        assert "Ctrl+S save  |  Esc cancel" in str(edit_children[0].render())


@pytest.mark.asyncio
async def test_task_details_workspace_empty_state_is_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_workspaces = AsyncMock(return_value=[])
    modal = _TaskDetailsModalForTest(task=_task_view_stub(), list_workspaces=list_workspaces)

    container = Vertical(id="workspace-repos-section")
    loading = Static("Loading workspace repositories...", id="workspace-repos-loading")

    def _safe_query_one(
        _parent: object,
        selector: str,
        _widget_class: type[object],
        default: object | None = None,
    ) -> object | None:
        if selector == "#workspace-repos-section":
            return container
        if selector == "#workspace-repos-loading":
            return loading
        return default

    monkeypatch.setattr("kagan.tui.ui.modals.task_details_modal.safe_query_one", _safe_query_one)

    await modal._load_workspace_repos()

    assert "No repositories connected." in str(loading.render())
    assert "workspace-empty-state" in loading.classes


@pytest.mark.asyncio
async def test_settings_modal_groups_controls_into_sections() -> None:
    modal = SettingsModal(KaganConfig(), api=SimpleNamespace())
    app = _ModalHostApp(modal)

    async with app.run_test(size=(120, 40)) as pilot:
        del pilot
        mounted = app.screen
        assert isinstance(mounted, SettingsModal)

        container = mounted.query_one("#settings-container", Container)
        assert container.id == "settings-container"
        nav = mounted.query_one("#settings-nav", OptionList)
        nav_option_ids = {option.id for option in nav.options}
        assert nav_option_ids >= {
            "section-auto-review",
            "section-orchestrator",
            "section-merge-policy",
            "section-general",
            "section-model-defaults",
            "section-ui-preferences",
        }

        sections_host = mounted.query_one("#settings-sections", VerticalScroll)
        section_ids = {
            child.id
            for child in sections_host.children
            if isinstance(child, Vertical) and "settings-section" in child.classes
        }
        assert section_ids >= {
            "section-auto-review",
            "section-orchestrator",
            "section-merge-policy",
            "section-general",
            "section-model-defaults",
            "section-ui-preferences",
        }

        general_section = mounted.query_one("#section-general", Vertical)
        general_compact_rows = [
            child
            for child in general_section.children
            if isinstance(child, Horizontal) and "settings-input-row" in child.classes
        ]
        assert len(general_compact_rows) == 2

        model_section = mounted.query_one("#section-model-defaults", Vertical)
        model_compact_rows = [
            child
            for child in model_section.children
            if isinstance(child, Horizontal) and "settings-input-row" in child.classes
        ]
        assert len(model_compact_rows) == 3

        assert mounted.query_one("#settings-search", Input).placeholder == "Search settings..."
        bool_toggles = [widget for widget in mounted.query("*") if isinstance(widget, Checkbox)]
        assert len(bool_toggles) >= 8
        assert all(toggle.compact for toggle in bool_toggles)


@pytest.mark.asyncio
async def test_settings_modal_search_focuses_matching_section_and_filters_items() -> None:
    modal = SettingsModal(KaganConfig(), api=SimpleNamespace())
    app = _ModalHostApp(modal)

    async with app.run_test(size=(120, 40)) as pilot:
        mounted = app.screen
        assert isinstance(mounted, SettingsModal)

        for key in "copilot":
            await pilot.press(key)

        model_section = mounted.query_one("#section-model-defaults", Vertical)
        assert model_section.display is True

        copilot_group = mounted.query_one("#default-model-copilot-input", Input).parent
        claude_group = mounted.query_one("#default-model-claude-input", Input).parent
        assert copilot_group is not None
        assert claude_group is not None
        assert copilot_group.display is True
        assert claude_group.display is False

        search_status = mounted.query_one("#settings-search-status", Static)
        assert search_status.display is True
        assert "match" in str(search_status.render()).lower()


@pytest.mark.asyncio
async def test_settings_modal_action_hint_is_single_compact_label() -> None:
    modal = SettingsModal(KaganConfig(), api=SimpleNamespace())
    app = _ModalHostApp(modal)

    async with app.run_test(size=(120, 40)) as pilot:
        del pilot
        mounted = app.screen
        assert isinstance(mounted, SettingsModal)

        action_hint = mounted.query_one("#settings-action-hint", Static)
        assert "modal-action-hint" in action_hint.classes
        assert "Ctrl+S" in str(action_hint.render())
        assert "Esc" in str(action_hint.render())
        assert "modal-action-hint-end" not in action_hint.classes


def test_persona_field_preview_shows_multiple_lines() -> None:
    field = PersonaField(
        "Implementer line one\nImplementer line two\nImplementer line three\nImplementer line four",
        field_id="worker-persona-field",
        default="",
    )
    field._refresh_preview()

    rendered = str(field.render())
    assert "Implementer line one" in rendered
    assert "Implementer line two" in rendered
    assert "(+1 more lines)" in rendered
    assert "line(s)" in rendered
