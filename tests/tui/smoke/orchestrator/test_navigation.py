from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from textual.widgets import Input, OptionList, Select, Static

from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.tui.ui.modals.session_picker import SessionPickerModal
from kagan.tui.ui.modals.tmux_gateway import PairInstructionsModal
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.screens.task_output import TaskOutputScreen
from kagan.tui.ui.widgets.card import TaskCard
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay, TaskContext
from kagan.tui.ui.widgets.plan_approval import PlanApprovalWidget
from kagan.tui.ui.widgets.streaming_output import StreamingOutput
from tests.helpers.mock_responses import make_plan_submit_tool_call
from tests.helpers.wait import wait_for_screen, wait_for_widget, wait_until

from .conftest import (
    UI_TIMEOUT_BOOT,
    UI_TIMEOUT_LONG,
    UI_TIMEOUT_SHORT,
    _active_session_picker,
    _focus_task_card,
    _open_task_output_via_enter,
    _press_enter_until,
    _wait_for_kanban_overlay,
)

pytestmark = pytest.mark.usefixtures("global_mock_tmux")


@pytest.mark.asyncio
async def test_orchestrator_overlay_renders_plan_approval_from_tool_calls(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Here's a plan.")
    mock_agent_factory.set_default_tool_calls(
        make_plan_submit_tool_call(
            tool_call_id="tc-orchestrator-plan-001",
            tasks=[
                {
                    "title": "Create orchestrator smoke coverage",
                    "type": "AUTO",
                    "description": "Add tests for docked/fullscreen overlay behavior.",
                    "acceptance_criteria": [
                        "Overlay opens fullscreen on board entry",
                        "Ctrl+P/Ctrl+O toggle orchestrator modes",
                    ],
                    "priority": "high",
                }
            ],
        )
    )

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        from kagan.tui.ui.widgets.status_bar import StatusBar

        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        await wait_until(
            lambda: status_bar.status == "ready",
            timeout=UI_TIMEOUT_LONG,
            description="orchestrator status to become ready",
        )
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "Plan this work"
        await pilot.pause()
        await pilot.press("enter")

        await wait_for_widget(pilot, "PlanApprovalWidget", timeout=20.0)
        overlay.query_one(PlanApprovalWidget)


@pytest.mark.asyncio
async def test_orchestrator_overlay_tab_opens_session_picker_for_single_target_scope(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "Auto task for chat target switch",
            "Created by test",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        session_select: Select[str] = overlay.query_one("#chat-overlay-session-select", Select)
        chat_input.focus()
        await pilot.pause()
        await pilot.press("tab")
        await wait_until(
            lambda: _active_session_picker(app) is not None,
            timeout=UI_TIMEOUT_LONG,
            description="Tab to open session picker for single-target scope",
        )
        session_picker = _active_session_picker(app)
        assert session_picker is not None
        picker_groups = session_picker.query_one("#session-picker-groups", OptionList)
        picker_options = session_picker.query_one("#session-picker-options", OptionList)
        await wait_until(
            lambda: len(picker_groups.options) >= 2,
            timeout=UI_TIMEOUT_LONG,
            description="session picker to include orchestrator group and active task group",
        )
        assert any(option.id == "group:orchestrator" for option in picker_groups.options)
        has_task_group = any(
            str(option.id).startswith("group:") and option.id != "group:orchestrator"
            for option in picker_groups.options
        )
        assert has_task_group
        assert any(str(option.id).startswith("orchestrator:") for option in picker_options.options)
        await pilot.press("escape")
        await wait_until(
            lambda: _active_session_picker(app) is None,
            timeout=UI_TIMEOUT_LONG,
            description="session picker to close",
        )
        assert chat_input.placeholder.startswith("Describe your task")
        assert not bool(session_select.display)
        assert overlay._active_target().key.startswith("orchestrator:")


@pytest.mark.asyncio
async def test_orchestrator_overlay_tab_cycles_scoped_targets_linearly(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog attention queue target",
            "Tab should stay on REVIEW when AUTO is not IN_PROGRESS",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        overlay._requested_task_context = TaskContext(
            task_id=auto_task.id,
            short_id=auto_task.id[:8],
            title=auto_task.title,
            task_type=TaskType.AUTO,
            status=TaskStatus.BACKLOG,
        )
        overlay.set_target_scope(auto_task.id)
        await overlay._refresh_chat_targets(force=True)
        await wait_until(
            lambda: overlay._active_target().key == f"auto:{auto_task.id}",
            timeout=UI_TIMEOUT_LONG,
            description="scoped overlay to activate AUTO target",
        )
        overlay.query_one("#chat-overlay-input", Input).focus()
        await pilot.pause()
        await pilot.press("tab")
        await wait_until(
            lambda: overlay._active_target().key == f"review:{auto_task.id}",
            timeout=UI_TIMEOUT_LONG,
            description="Tab to jump from worker to reviewer",
        )
        await pilot.press("tab")
        await wait_until(
            lambda: overlay._active_target().key == f"auto:{auto_task.id}",
            timeout=UI_TIMEOUT_LONG,
            description="Tab to cycle back from reviewer to worker",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_switch_clears_input_and_reenables_after_switch(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "Switch clears draft input",
            "Session switch should clear input and not restore old drafts",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        overlay._requested_task_context = TaskContext(
            task_id=auto_task.id,
            short_id=auto_task.id[:8],
            title=auto_task.title,
            task_type=TaskType.AUTO,
            status=TaskStatus.IN_PROGRESS,
        )
        overlay.set_target_scope(auto_task.id)
        await overlay._refresh_chat_targets(force=True)
        await wait_until(
            lambda: overlay._active_target().key == f"auto:{auto_task.id}",
            timeout=UI_TIMEOUT_LONG,
            description="scoped overlay to activate AUTO target",
        )

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.value = "hello worker"
        switch_gate = asyncio.Event()
        original_restore = overlay._restore_output_for_target

        async def _delayed_restore(target):
            await switch_gate.wait()
            await original_restore(target)

        with patch.object(overlay, "_restore_output_for_target", side_effect=_delayed_restore):
            switch_task = asyncio.create_task(
                overlay._switch_active_target_by_key(f"review:{auto_task.id}", notify=False)
            )
            await wait_until(
                lambda: chat_input.disabled is True,
                timeout=UI_TIMEOUT_LONG,
                description="chat input to disable while switching targets",
            )
            switch_gate.set()
            await switch_task

        await wait_until(
            lambda: chat_input.disabled is False,
            timeout=UI_TIMEOUT_LONG,
            description="chat input to re-enable after switching targets",
        )
        assert chat_input.value == ""

        chat_input.value = "hello reviewer"
        await overlay._switch_active_target_by_key(f"auto:{auto_task.id}", notify=False)
        assert chat_input.value == ""


@pytest.mark.asyncio
async def test_orchestrator_overlay_ctrl_k_quick_pick_switches_scope(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO quick-pick scope switch",
            "Ctrl+K should switch to the selected task session",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        await output.post_note("orchestrator marker")
        assert "orchestrator marker" in output.get_text_content()
        chat_input.focus()
        await pilot.pause()
        await pilot.press("ctrl+k")
        await wait_until(
            lambda: _active_session_picker(app) is not None,
            timeout=UI_TIMEOUT_LONG,
            description="Ctrl+K to open session quick-pick",
        )

        session_picker = _active_session_picker(app)
        assert session_picker is not None
        picker_groups = session_picker.query_one("#session-picker-groups", OptionList)
        await wait_until(
            lambda: any(option.id == "group:orchestrator" for option in picker_groups.options),
            timeout=UI_TIMEOUT_LONG,
            description="quick-pick to include orchestrator root group",
        )
        picker_filter = session_picker.query_one("#session-picker-filter", Input)
        picker_filter.value = auto_task.id[:8]
        picker_options = session_picker.query_one("#session-picker-options", OptionList)
        auto_session_key = f"auto:{auto_task.id}"
        await wait_until(
            lambda: any(option.id == auto_session_key for option in picker_options.options),
            timeout=UI_TIMEOUT_LONG,
            description="AUTO target option to appear in quick-pick",
        )
        for index, option in enumerate(picker_options.options):
            if option.id == auto_session_key:
                picker_options.highlighted = index
                break
        await pilot.press("enter")
        await wait_until(
            lambda: _active_session_picker(app) is None,
            timeout=UI_TIMEOUT_LONG,
            description="session quick-pick to dismiss after selection",
        )
        await wait_until(
            lambda: overlay._active_target().key == auto_session_key,
            timeout=UI_TIMEOUT_LONG,
            description="quick-pick selection to switch active chat target",
        )
        assert "orchestrator marker" not in output.get_text_content()
        assert overlay._target_scope_task_id == auto_task.id


@pytest.mark.asyncio
async def test_orchestrator_overlay_session_picker_tab_cycles_filter_groups_and_agents(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        await pilot.pause()
        await pilot.press("ctrl+k")
        await wait_until(
            lambda: _active_session_picker(app) is not None,
            timeout=UI_TIMEOUT_LONG,
            description="Ctrl+K to open session quick-pick",
        )
        session_picker = _active_session_picker(app)
        assert session_picker is not None
        footer_hint = session_picker.query_one("#session-picker-footer-hint", Static)
        assert "Esc clears filter first, Esc again closes" in str(footer_hint.render())
        match_count = session_picker.query_one("#session-picker-match-count", Static)
        assert "session" in str(match_count.render())

        await wait_until(
            lambda: getattr(getattr(app, "focused", None), "id", "") == "session-picker-filter",
            timeout=UI_TIMEOUT_LONG,
            description="picker filter to receive initial focus",
        )
        await pilot.press("tab")
        await wait_until(
            lambda: getattr(getattr(app, "focused", None), "id", "") == "session-picker-groups",
            timeout=UI_TIMEOUT_LONG,
            description="Tab to move focus from filter to session groups",
        )
        await pilot.press("tab")
        await wait_until(
            lambda: getattr(getattr(app, "focused", None), "id", "") == "session-picker-options",
            timeout=UI_TIMEOUT_LONG,
            description="Tab to move focus from groups to agent options",
        )
        await pilot.press("tab")
        await wait_until(
            lambda: getattr(getattr(app, "focused", None), "id", "") == "session-picker-filter",
            timeout=UI_TIMEOUT_LONG,
            description="Tab to cycle focus back to filter",
        )
        await pilot.press("escape")
        await wait_until(
            lambda: _active_session_picker(app) is None,
            timeout=UI_TIMEOUT_LONG,
            description="session picker to close",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_session_picker_shows_recent_group_and_updates_match_count(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "Recent sessions source task",
            "Populate recent session group in picker",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        overlay._requested_task_context = TaskContext(
            task_id=auto_task.id,
            short_id=auto_task.id[:8],
            title=auto_task.title,
            task_type=TaskType.AUTO,
            status=TaskStatus.IN_PROGRESS,
        )
        overlay.set_target_scope(auto_task.id)
        await overlay._refresh_chat_targets(force=True)
        await overlay._switch_active_target_by_key(f"review:{auto_task.id}", notify=False)
        await overlay._switch_active_target_by_key(f"auto:{auto_task.id}", notify=False)

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        await pilot.pause()
        await pilot.press("ctrl+k")
        await wait_until(
            lambda: _active_session_picker(app) is not None,
            timeout=UI_TIMEOUT_LONG,
            description="Ctrl+K to open quick-pick with recent sessions",
        )
        session_picker = _active_session_picker(app)
        assert session_picker is not None
        groups = session_picker.query_one("#session-picker-groups", OptionList)
        await wait_until(
            lambda: len(groups.options) >= 2,
            timeout=UI_TIMEOUT_LONG,
            description="quick-pick to populate groups including recents",
        )
        assert str(groups.options[0].id) == "group:recent"
        filter_input = session_picker.query_one("#session-picker-filter", Input)
        filter_input.value = auto_task.id[:8]
        match_count = session_picker.query_one("#session-picker-match-count", Static)
        await wait_until(
            lambda: "session" in str(match_count.render()).lower(),
            timeout=UI_TIMEOUT_LONG,
            description="match count to update after filtering",
        )
        await pilot.press("escape")
        await wait_until(
            lambda: (
                _active_session_picker(app) is not None
                and _active_session_picker(app).query_one("#session-picker-filter", Input).value
                == ""
            ),
            timeout=UI_TIMEOUT_LONG,
            description="first Escape to clear filter before closing",
        )
        await pilot.press("escape")
        await wait_until(
            lambda: _active_session_picker(app) is None,
            timeout=UI_TIMEOUT_LONG,
            description="second Escape to close quick-pick",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_debounces_chat_session_notifications(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "Debounced chat notifications",
            "Rapid session switching should emit one trailing toast",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        overlay._requested_task_context = TaskContext(
            task_id=auto_task.id,
            short_id=auto_task.id[:8],
            title=auto_task.title,
            task_type=TaskType.AUTO,
            status=TaskStatus.IN_PROGRESS,
        )
        overlay.set_target_scope(auto_task.id)
        await overlay._refresh_chat_targets(force=True)

        with patch.object(overlay, "notify") as notify_mock:
            await overlay._switch_active_target_by_key(f"review:{auto_task.id}", notify=True)
            await overlay._switch_active_target_by_key(f"auto:{auto_task.id}", notify=True)
            await overlay._switch_active_target_by_key(f"review:{auto_task.id}", notify=True)
            await pilot.pause(0.35)
            assert notify_mock.call_count == 1
            message = notify_mock.call_args.args[0]
            assert "Chat session:" in message


@pytest.mark.asyncio
async def test_orchestrator_overlay_session_picker_empty_filter_does_not_auto_close(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        await pilot.pause()
        await pilot.press("ctrl+k")
        await wait_until(
            lambda: _active_session_picker(app) is not None,
            timeout=UI_TIMEOUT_LONG,
            description="Ctrl+K to open session quick-pick",
        )
        session_picker = _active_session_picker(app)
        assert session_picker is not None

        picker_filter = session_picker.query_one("#session-picker-filter", Input)
        picker_filter.value = "zzzz-no-such-session"
        picker_groups = session_picker.query_one("#session-picker-groups", OptionList)
        picker_options = session_picker.query_one("#session-picker-options", OptionList)
        await wait_until(
            lambda: (
                len(picker_groups.options) == 1
                and str(picker_groups.options[0].id) == SessionPickerModal.EMPTY_GROUP_OPTION_ID
            ),
            timeout=UI_TIMEOUT_LONG,
            description="session picker to show empty-state group placeholder",
        )
        await wait_until(
            lambda: (
                len(picker_options.options) == 1
                and str(picker_options.options[0].id) == SessionPickerModal.EMPTY_SESSION_OPTION_ID
            ),
            timeout=UI_TIMEOUT_LONG,
            description="session picker to show empty-state session placeholder",
        )
        await pilot.press("enter")
        await wait_until(
            lambda: _active_session_picker(app) is not None,
            timeout=UI_TIMEOUT_SHORT,
            description="Enter on empty-state picker to keep modal open",
        )
        await pilot.press("escape")
        await wait_until(
            lambda: (
                _active_session_picker(app) is not None
                and _active_session_picker(app).query_one("#session-picker-filter", Input).value
                == ""
            ),
            timeout=UI_TIMEOUT_LONG,
            description="first Escape to clear filter without closing picker",
        )
        await pilot.press("escape")
        await wait_until(
            lambda: _active_session_picker(app) is None,
            timeout=UI_TIMEOUT_LONG,
            description="second Escape to close picker",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_session_selector_stays_orchestrator_only(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "Auto task for session dropdown",
            "Created by test",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()
        await overlay._refresh_chat_targets()

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        session_current = overlay.query_one("#chat-overlay-session-current")
        session_indicator = overlay.query_one("#chat-overlay-session-indicator")
        session_select: Select[str] = overlay.query_one("#chat-overlay-session-select", Select)
        assert not bool(session_select.display)
        assert len(session_select._options) == 1
        assert str(session_select._options[0][1]).startswith("orchestrator:")
        assert chat_input.placeholder.startswith("Describe your task")
        session_label = str(session_current.render())
        assert "Orchestrator" in session_label
        assert "Orchestration" not in session_label
        assert session_indicator.has_class("session-kind-orchestrator")


@pytest.mark.asyncio
async def test_orchestrator_overlay_ignores_hidden_session_selector_change_events(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "Hidden selector event regression",
            "Ensure hidden select change does not force target switch",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        overlay._requested_task_context = TaskContext(
            task_id=auto_task.id,
            short_id=auto_task.id[:8],
            title=auto_task.title,
            task_type=TaskType.AUTO,
            status=TaskStatus.IN_PROGRESS,
        )
        overlay.set_target_scope(auto_task.id)
        await overlay._refresh_chat_targets(force=True)
        review_key = f"review:{auto_task.id}"
        auto_key = f"auto:{auto_task.id}"
        await overlay._switch_active_target_by_key(review_key, notify=False)
        await wait_until(
            lambda: overlay._active_target().key == review_key,
            timeout=UI_TIMEOUT_LONG,
            description="scoped overlay to switch to reviewer target",
        )

        session_select: Select[str] = overlay.query_one("#chat-overlay-session-select", Select)
        assert not bool(session_select.display)
        session_select.value = auto_key
        await pilot.pause()
        await wait_until(
            lambda: overlay._active_target().key == review_key,
            timeout=UI_TIMEOUT_LONG,
            description="hidden selector change to be ignored",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_routes_review_task_to_session_flow(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        review_task = await kanban.ctx.api.create_task(
            "Review target from Enter",
            "Ensure Enter routes REVIEW tasks through session flow",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.REVIEW.value)
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before Enter opens focused review context",
        )

        review_card = kanban.query_one(f"#card-{review_task.id}", TaskCard)
        review_card.focus()
        await pilot.pause()
        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            await pilot.press("o")
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="Enter to route REVIEW task through session flow",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == review_task.id
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_review_shortcut_routes_to_review_stream_not_overlay(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        review_task = await kanban.ctx.api.create_task(
            "Review shortcut target",
            "Ensure r routes REVIEW task to review stream",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.REVIEW.value)
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before pressing review shortcut",
        )

        review_card = kanban.query_one(f"#card-{review_task.id}", TaskCard)
        review_card.focus()
        await pilot.pause()
        with patch.object(kanban._review, "action_open_review", autospec=True) as open_review_mock:
            await pilot.press("r")
            await wait_until(
                lambda: open_review_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="'r' to route REVIEW task to review stream",
            )
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_routes_pair_task_to_session_flow(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR backlog enter target",
            "Ensure Enter routes PAIR tasks through session flow",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before opening pair backlog context",
        )

        pair_card = kanban.query_one(f"#card-{pair_task.id}", TaskCard)
        pair_card.focus()
        await pilot.pause()
        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            await pilot.press("o")
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="Enter to route PAIR task through session flow",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == pair_task.id
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_pair_task_opens_instructions_modal(
    e2e_app_with_tasks,
    mock_agent_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kagan.core.agents.installer.check_agent_installed",
        lambda _agent: True,
    )

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR instructions enter target",
            "Ensure Enter opens PAIR instructions modal before launching backend",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before opening pair instructions context",
        )

        pair_card = kanban.query_one(f"#card-{pair_task.id}", TaskCard)
        pair_card.focus()
        await pilot.pause()

        with patch.object(
            kanban.ctx.api,
            "session_exists",
            new=AsyncMock(return_value=True),
        ):
            await pilot.press("o")
            await wait_until(
                lambda: any(
                    isinstance(screen, PairInstructionsModal) for screen in app.screen_stack
                ),
                timeout=UI_TIMEOUT_LONG,
                description="Enter to open PAIR instructions modal",
            )
            await pilot.press("escape")


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_uses_last_focused_pair_task_when_focus_clears(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR enter fallback target",
            "Ensure Enter still opens the last focused PAIR task when focus clears",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before validating Enter fallback behavior",
        )

        pair_card = kanban.query_one(f"#card-{pair_task.id}", TaskCard)
        pair_card.focus()
        await wait_until(
            lambda: kanban.last_focused_task_id == pair_task.id,
            timeout=UI_TIMEOUT_SHORT,
            description="PAIR card focus to update remembered task id",
        )

        kanban.app.set_focus(None)
        await pilot.pause()

        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            kanban.action_open_session()
            await pilot.pause()
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="Enter to use remembered PAIR task when focus is temporarily cleared",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == pair_task.id


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_ignores_repeated_open_session_while_loading(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR enter loading guard",
            "Ensure repeated Enter does not queue concurrent open-session workers",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before validating repeated Enter guard",
        )

        pair_card = kanban.query_one(f"#card-{pair_task.id}", TaskCard)
        pair_card.focus()
        await pilot.pause()

        open_started = asyncio.Event()
        allow_complete = asyncio.Event()

        async def _block_open_session(task: object) -> None:
            del task
            open_started.set()
            await allow_complete.wait()

        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            open_session_mock.side_effect = _block_open_session

            await pilot.press("o")
            await wait_until(
                lambda: open_started.is_set(),
                timeout=UI_TIMEOUT_LONG,
                description="first Enter to start open-session flow",
            )

            await pilot.press("o")
            await pilot.pause()
            assert open_session_mock.await_count == 1

            allow_complete.set()
            await wait_until(
                lambda: all(
                    worker.group != "open-session" or worker.is_finished
                    for worker in kanban.workers
                ),
                timeout=UI_TIMEOUT_LONG,
                description="open-session worker to finish cleanly after guarded Enter",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_routes_backlog_auto_task_to_session_flow(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog enter starts task",
            "Ensure Enter routes backlog AUTO tasks through session flow",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before pressing Enter on AUTO backlog task",
        )

        await _focus_task_card(pilot, kanban, auto_task.id)

        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            await pilot.press("o")
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="Enter to route AUTO backlog task through session flow",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == auto_task.id
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_orchestrator_overlay_backlog_auto_confirmed_start_passes_start_requested_flag(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog confirm start",
            "Ensure confirmed backlog start carries start_requested state to output opening",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()

        with (
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban._session,
                "confirm_start_auto_task",
                AsyncMock(return_value=True),
            ),
            patch.object(
                kanban._session,
                "open_auto_output_for_task",
                AsyncMock(return_value=True),
            ) as open_output_mock,
        ):
            await _press_enter_until(
                pilot,
                lambda: open_output_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="backlog AUTO Enter to open output after confirmed start",
            )
            called_task = open_output_mock.await_args.args[0]
            assert called_task.id == auto_task.id
            assert open_output_mock.await_args.kwargs["auto_start_requested"] is True


@pytest.mark.asyncio
async def test_orchestrator_overlay_backlog_auto_confirmed_start_force_opens_output(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog force open output",
            "Ensure confirmed start force-opens output even before runtime readiness settles",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        await _focus_task_card(pilot, kanban, auto_task.id)

        with (
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban._session,
                "confirm_start_auto_task",
                AsyncMock(return_value=True),
            ),
            patch.object(
                kanban._session,
                "start_agent_flow",
                AsyncMock(return_value=True),
            ),
            patch.object(
                kanban._session,
                "open_auto_output_for_task",
                AsyncMock(return_value=True),
            ) as open_output_mock,
        ):
            await _press_enter_until(
                pilot,
                lambda: open_output_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="confirmed backlog AUTO start to force-open task output",
            )
            assert open_output_mock.await_args.kwargs["force_open"] is True


@pytest.mark.asyncio
async def test_orchestrator_overlay_backlog_auto_start_failure_still_opens_task_output(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    """Verify Task Output opens even when the auto-start job submission fails.

    When the user confirms starting a BACKLOG AUTO task, the Task Output screen
    should open immediately. The agent start is triggered asynchronously after
    mount via _auto_start_if_needed(). Even if that start request fails, the
    Task Output screen must remain open so the user can manually retry.
    """
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog start failure opens output",
            "Ensure confirmed start still opens Task Output when start request fails",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        await _focus_task_card(pilot, kanban, auto_task.id)
        readiness = SimpleNamespace(
            can_open_output=False,
            execution_id=None,
            is_running=False,
            message="No active AUTO run.",
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban._session,
                "confirm_start_auto_task",
                AsyncMock(return_value=True),
            ),
            patch.object(
                kanban.ctx.api,
                "submit_job",
                AsyncMock(side_effect=RuntimeError("Start request failed")),
            ),
        ):
            task_output = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            # Give the auto-start worker time to attempt and fail
            await pilot.pause()
            await asyncio.sleep(0.2)
            await pilot.pause()
            # Task Output should still be the active screen despite start failure
            assert isinstance(pilot.app.screen, TaskOutputScreen)
            assert pilot.app.screen is task_output


@pytest.mark.asyncio
async def test_orchestrator_overlay_backlog_auto_confirmed_start_submits_without_workspace_gate(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog submit start without workspace gate",
            "Ensure confirmed start submits job even when workspace path is absent",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        await _focus_task_card(pilot, kanban, auto_task.id)
        readiness = SimpleNamespace(
            can_open_output=False,
            execution_id=None,
            is_running=False,
            message="No active AUTO run.",
        )
        with (
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban._session,
                "confirm_start_auto_task",
                AsyncMock(return_value=True),
            ),
            patch.object(
                kanban.ctx.api,
                "submit_job",
                AsyncMock(return_value=SimpleNamespace(job_id="job-start-001")),
            ) as submit_job_mock,
            patch.object(
                kanban.ctx.api,
                "wait_job",
                AsyncMock(return_value=None),
            ),
            patch.object(
                kanban._session,
                "provision_workspace_for_active_repo",
                AsyncMock(),
            ) as provision_mock,
        ):
            await _open_task_output_via_enter(
                pilot,
                kanban,
                auto_task.id,
                ensure_workspace=False,
            )
            assert submit_job_mock.await_count >= 1
            assert provision_mock.await_count == 0


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_opens_auto_chat_session(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO enter opens chat session",
            "Ensure Enter opens orchestrator chat in AUTO session",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        if board_overlay.has_class("visible"):
            await pilot.press("escape")
            await wait_until(
                lambda: not board_overlay.has_class("visible"),
                timeout=UI_TIMEOUT_SHORT,
                description="overlay to close before Enter opens AUTO chat session",
            )

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-open-001",
            is_running=True,
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            output_screen = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            await wait_until(
                lambda: embedded_overlay.has_class("visible")
                and not embedded_overlay.has_class("fullscreen"),
                timeout=UI_TIMEOUT_LONG,
                description="AUTO Enter to open session overlay in Task Output screen",
            )
            await wait_until(
                lambda: embedded_overlay.has_class("has-content"),
                timeout=UI_TIMEOUT_LONG,
                description="Task Output overlay to switch to stream content mode on open",
            )
            await wait_until(
                lambda: "connecting to agent output stream in a task..."
                in output.get_text_content().lower(),
                timeout=UI_TIMEOUT_LONG,
                description="Task Output overlay to show deterministic stream connection note",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_opens_task_output_when_auto_idle(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO enter opens idle task output",
            "Ensure Enter opens split task output even before a live run starts",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=False,
            execution_id=None,
            is_running=False,
            message="No active AUTO run.",
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            output_screen = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            await wait_until(
                lambda: embedded_overlay.has_class("visible")
                and not embedded_overlay.has_class("fullscreen"),
                timeout=UI_TIMEOUT_LONG,
                description="AUTO Enter to open split task output even when idle",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_task_output_ctrl_p_ctrl_o_match_board_overlay_behavior(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO output Ctrl+P/Ctrl+O behavior",
            "Ensure Task Output overlay controls match board overlay semantics",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-cycle-001",
            is_running=True,
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            output_screen = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)

            assert not output_screen.has_class("task-output-terminal-fullscreen")
            assert embedded_overlay.has_class("visible")
            assert not embedded_overlay.has_class("fullscreen")
            expected_docked_height = output_screen._estimated_docked_overlay_height()
            assert expected_docked_height > 0
            assert int(embedded_overlay.styles.height.value) == expected_docked_height

            await pilot.press("tab")
            await wait_until(
                lambda: embedded_overlay.has_class("visible")
                and not embedded_overlay.has_class("fullscreen"),
                timeout=UI_TIMEOUT_SHORT,
                description="Task Output overlay to remain docked and visible after Tab",
            )

            await pilot.press("ctrl+p")
            await wait_until(
                lambda: output_screen.has_class("task-output-terminal-fullscreen")
                and embedded_overlay.has_class("fullscreen"),
                timeout=UI_TIMEOUT_SHORT,
                description="Ctrl+P to switch split task output to fullscreen terminal",
            )

            await pilot.press("ctrl+o")
            await wait_until(
                lambda: embedded_overlay.has_class("visible")
                and not embedded_overlay.has_class("fullscreen")
                and not output_screen.has_class("task-output-terminal-fullscreen"),
                timeout=UI_TIMEOUT_SHORT,
                description="Ctrl+O to switch Task Output overlay from fullscreen to docked",
            )

            await pilot.press("ctrl+o")
            await wait_until(
                lambda: not embedded_overlay.has_class("visible")
                and not embedded_overlay.has_class("fullscreen"),
                timeout=UI_TIMEOUT_SHORT,
                description="Ctrl+O to hide docked Task Output overlay",
            )

            await pilot.press("ctrl+p")
            await wait_until(
                lambda: (
                    embedded_overlay.has_class("visible")
                    and embedded_overlay.has_class("fullscreen")
                ),
                timeout=UI_TIMEOUT_SHORT,
                description="Ctrl+P to reopen hidden Task Output overlay in fullscreen",
            )
            await pilot.press("ctrl+p")
            await wait_until(
                lambda: not embedded_overlay.has_class("visible"),
                timeout=UI_TIMEOUT_SHORT,
                description=(
                    "Ctrl+P on fullscreen Task Output overlay to hide without leaving screen"
                ),
            )
            await wait_for_screen(pilot, TaskOutputScreen, timeout=UI_TIMEOUT_LONG)


@pytest.mark.asyncio
async def test_orchestrator_overlay_task_output_escape_returns_to_board(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO task output Esc returns board",
            "Ensure Escape closes Task Output and returns to board screen",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-escape-001",
            is_running=True,
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            await pilot.press("escape")
            await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_LONG)
