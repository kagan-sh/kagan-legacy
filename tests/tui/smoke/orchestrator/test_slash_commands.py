from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from textual.widgets import Input, OptionList, Select

from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.keybinding_hint import KanbanHintBar
from kagan.tui.ui.widgets.slash_complete import SlashComplete
from kagan.tui.ui.widgets.streaming_output import StreamingOutput
from tests.helpers.wait import wait_until

from .conftest import (
    UI_TIMEOUT_LONG,
    UI_TIMEOUT_SHORT,
    _active_session_picker,
    _has_slash_complete,
    _open_task_output_via_enter,
    _wait_for_kanban_overlay,
)

pytestmark = pytest.mark.usefixtures("global_mock_tmux")


@pytest.mark.asyncio
async def test_orchestrator_overlay_shows_slash_popup_and_escape_dismisses_only_popup(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "/"

        await wait_until(
            lambda: _has_slash_complete(overlay),
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete popup to appear",
        )

        await pilot.press("escape")
        await wait_until(
            lambda: not _has_slash_complete(overlay),
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete popup to close on escape",
        )
        assert overlay.has_class("visible")
        assert chat_input.value == ""
        assert not bool(hint_bar.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_slash_popup_enter_runs_highlighted_command(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "/"

        await wait_until(
            lambda: _has_slash_complete(overlay),
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete popup to appear for enter selection",
        )

        slash_complete = overlay.query_one(SlashComplete)
        option_list = slash_complete.query_one("#slash-options", OptionList)
        help_index = next(
            (
                index
                for index, option in enumerate(option_list.options)
                if getattr(option, "id", None) == "help"
            ),
            None,
        )
        assert help_index is not None
        option_list.highlighted = help_index

        await pilot.press("enter")
        await wait_until(
            lambda: not _has_slash_complete(overlay),
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete popup to close on enter selection",
        )

        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        await wait_until(
            lambda: "Available Commands" in output.get_text_content(),
            timeout=UI_TIMEOUT_LONG,
            description="slash popup enter selection to execute /help",
        )
        assert overlay.has_class("visible")
        assert not bool(hint_bar.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_slash_popup_filters_while_typing(
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
        chat_input.value = "/"

        await wait_until(
            lambda: _has_slash_complete(overlay),
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete popup to appear for filtering",
        )

        slash_complete = overlay.query_one(SlashComplete)
        option_list = slash_complete.query_one("#slash-options", OptionList)

        def _option_ids() -> set[str]:
            return {
                str(option_id)
                for option in option_list.options
                if (option_id := getattr(option, "id", None)) is not None
            }

        def _expected_ids(query: str) -> set[str]:
            lowered = query.casefold()
            return {
                command.command
                for command in slash_complete.slash_commands
                if command.command.casefold().startswith(lowered)
                or any(alias.casefold().startswith(lowered) for alias in command.aliases)
            }

        chat_input.value = "/h"
        expected_h = _expected_ids("h")
        assert expected_h
        await wait_until(
            lambda: _option_ids() == expected_h,
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete to filter for /h",
        )
        filtered_count_h = len(option_list.options)

        chat_input.value = "/he"
        expected_he = _expected_ids("he")
        assert expected_he
        await wait_until(
            lambda: _option_ids() == expected_he,
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete to filter for /he",
        )
        assert len(option_list.options) <= filtered_count_h


@pytest.mark.asyncio
async def test_orchestrator_overlay_slash_popup_overlays_footer_and_supports_paging(
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
        chat_input.value = "/"

        await wait_until(
            lambda: _has_slash_complete(overlay),
            timeout=UI_TIMEOUT_SHORT,
            description="slash complete popup to appear for overlay/footer assertions",
        )

        slash_complete = overlay.query_one(SlashComplete)
        option_list = slash_complete.query_one("#slash-options", OptionList)
        status_bar = overlay.query_one("#chat-overlay-status")
        chat_input = overlay.query_one("#chat-overlay-input", Input)

        await wait_until(
            lambda: option_list.region.height > 0 and slash_complete.region.height > 0,
            timeout=UI_TIMEOUT_SHORT,
            description="slash popup layout to settle",
        )

        # Popup should sit over or directly abut footer/status area instead of pushing layout.
        assert slash_complete.region.y <= status_bar.region.y
        assert status_bar.region.y <= slash_complete.region.y + slash_complete.region.height
        # Popup should stay within the overlay bounds even when footer layout changes.
        assert slash_complete.region.y >= overlay.region.y
        assert (
            slash_complete.region.y + slash_complete.region.height
            <= overlay.region.y + overlay.region.height
        )

        # Default popup height reserves six visible rows.
        assert option_list.region.height == 6
        assert option_list.highlighted == 0

        await pilot.press("end")
        assert option_list.highlighted >= 0
        await pilot.press("pageup")
        assert option_list.highlighted >= 0
        await pilot.press("pagedown")
        assert option_list.highlighted >= 0
        await pilot.press("home")
        assert option_list.highlighted == 0


@pytest.mark.asyncio
async def test_orchestrator_overlay_help_slash_command_posts_command_reference(
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
        chat_input.value = "/help"
        await pilot.pause()
        await pilot.press("enter")

        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        await wait_until(
            lambda: (
                "Available Commands" in output.get_text_content()
                and "/clear" in output.get_text_content()
                and "/mode" in output.get_text_content()
            ),
            timeout=UI_TIMEOUT_LONG,
            description="/help output to render available command list",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_slash_session_commands(
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
            "AUTO target for session popup",
            "Validate /sessions selector behavior",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        session_select: Select[str] = overlay.query_one("#chat-overlay-session-select", Select)

        chat_input.focus()
        chat_input.value = "/sessions"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: _active_session_picker(app) is not None,
            timeout=UI_TIMEOUT_LONG,
            description="/sessions to open session quick-pick",
        )
        assert not bool(session_select.expanded)
        await pilot.press("escape")
        await wait_until(
            lambda: _active_session_picker(app) is None,
            timeout=UI_TIMEOUT_LONG,
            description="session quick-pick to close",
        )
        assert str(session_select.value).startswith("orchestrator:")
        assert chat_input.placeholder.startswith("Describe your task")

        previous_scope_count = len(overlay._orchestrator_session_scope_ids)
        chat_input.focus()
        chat_input.value = "/new session"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: not overlay.has_class("has-content"),
            timeout=UI_TIMEOUT_LONG,
            description="/new session to clear overlay transcript",
        )
        assert len(overlay._orchestrator_session_scope_ids) == previous_scope_count + 1

        chat_input.focus()
        chat_input.value = "/clear all sessions"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: chat_input.placeholder.startswith("Describe your task"),
            timeout=UI_TIMEOUT_LONG,
            description="/clear all sessions to reset active chat target",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_export_slash_command_across_target_kinds(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    copied: list[tuple[str, str]] = []

    def _capture_copy(_app, text: str, label: str = "Content") -> bool:
        copied.append((text, label))
        return True

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)

        with patch(
            "kagan.tui.ui.widgets.chat_overlay.copy_with_notification",
            side_effect=_capture_copy,
        ):
            await output.clear()
            await output.post_note("orchestrator export marker")
            chat_input.focus()
            chat_input.value = "/export"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: len(copied) >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="/export to copy orchestrator transcript",
            )
            assert "orchestrator export marker" in copied[-1][0]
            assert "Type: orchestrator" in copied[-1][0]
            assert copied[-1][1] == "ORCHESTRATOR session transcript"

            auto_task = await kanban.ctx.api.create_task(
                "AUTO target for /export",
                "Validate /export for AUTO and REVIEW scoped sessions",
                project_id=project_id,
                task_type=TaskType.AUTO,
            )
            await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
            await kanban._board.refresh_board()

            if overlay.has_class("visible"):
                await pilot.press("escape")
                await wait_until(
                    lambda: not overlay.has_class("visible"),
                    timeout=UI_TIMEOUT_SHORT,
                    description="overlay to close before opening scoped Task Output session",
                )

            output_screen = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            embedded_overlay.set_target_scope(auto_task.id)
            embedded_overlay.show_for_task(auto_task, fullscreen=False)
            await wait_until(
                lambda: embedded_overlay._active_target().kind.value == "auto",
                timeout=UI_TIMEOUT_SHORT,
                description="Task Output overlay to bind AUTO target for /export",
            )

            embedded_input = embedded_overlay.query_one("#chat-overlay-input", Input)
            embedded_output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)

            await embedded_output.clear()
            await embedded_output.post_note("auto export marker")
            embedded_input.focus()
            embedded_input.value = "/export"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: len(copied) >= 2,
                timeout=UI_TIMEOUT_LONG,
                description="/export to copy AUTO transcript",
            )
            assert "auto export marker" in copied[-1][0]
            assert "Type: auto" in copied[-1][0]
            assert f"Task: {auto_task.id}" in copied[-1][0]
            assert copied[-1][1] == "AUTO session transcript"

            embedded_session_select: Select[str] = embedded_overlay.query_one(
                "#chat-overlay-session-select", Select
            )
            review_session_key = f"review:{auto_task.id}"
            embedded_input.focus()
            embedded_input.value = "/sessions"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: _active_session_picker(app) is not None,
                timeout=UI_TIMEOUT_LONG,
                description="/sessions to open scoped session quick-pick",
            )
            session_picker = _active_session_picker(app)
            assert session_picker is not None
            picker_filter = session_picker.query_one("#session-picker-filter", Input)
            picker_filter.value = "review"
            picker_options = session_picker.query_one("#session-picker-options", OptionList)
            await wait_until(
                lambda: any(option.id == review_session_key for option in picker_options.options),
                timeout=UI_TIMEOUT_LONG,
                description="review session option to appear in quick-pick",
            )
            for index, option in enumerate(picker_options.options):
                if option.id == review_session_key:
                    picker_options.highlighted = index
                    break
            await pilot.press("enter")
            await wait_until(
                lambda: embedded_overlay._active_target().kind.value == "review",
                timeout=UI_TIMEOUT_LONG,
                description="quick-pick selection to switch active scoped session",
            )
            assert not bool(embedded_session_select.expanded)

            await embedded_output.clear()
            await embedded_output.post_note("review export marker")
            embedded_input.focus()
            embedded_input.value = "/export"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: len(copied) >= 3,
                timeout=UI_TIMEOUT_LONG,
                description="/export to copy REVIEW transcript",
            )
            assert "review export marker" in copied[-1][0]
            assert "Type: review" in copied[-1][0]
            assert f"Task: {auto_task.id}" in copied[-1][0]
            assert copied[-1][1] == "REVIEW session transcript"


@pytest.mark.asyncio
async def test_orchestrator_overlay_restart_and_stop_accept_review_target_for_auto_task(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, _overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO runtime commands from review target",
            "Allow /restart and /stop while focused on REVIEW target of AUTO task",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        output_screen = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
        embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
        embedded_overlay.set_target_scope(auto_task.id)
        embedded_overlay.show_for_task(auto_task, fullscreen=False)
        await wait_until(
            lambda: embedded_overlay._active_target().kind.value == "auto",
            timeout=UI_TIMEOUT_LONG,
            description="Task Output overlay to bind AUTO target before review switch",
        )
        await embedded_overlay._switch_active_target_by_key(f"review:{auto_task.id}", notify=False)
        await wait_until(
            lambda: embedded_overlay._active_target().kind.value == "review",
            timeout=UI_TIMEOUT_LONG,
            description="Task Output overlay to switch to REVIEW target",
        )

        embedded_input = embedded_overlay.query_one("#chat-overlay-input", Input)
        output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
        with (
            patch.object(
                kanban.ctx.api,
                "submit_job",
                side_effect=[
                    SimpleNamespace(job_id="job-restart"),
                    SimpleNamespace(job_id="job-stop"),
                ],
            ) as submit_job_mock,
            patch.object(
                kanban.ctx.api,
                "wait_job",
                return_value=None,
            ) as wait_job_mock,
        ):
            embedded_input.focus()
            embedded_input.value = "/restart"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: "AUTO restart requested; waiting for scheduler."
                in output.get_text_content(),
                timeout=UI_TIMEOUT_LONG,
                description="/restart to execute from REVIEW target bound to AUTO task",
            )

            embedded_input.focus()
            embedded_input.value = "/stop"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: "AUTO stop requested; waiting for scheduler." in output.get_text_content(),
                timeout=UI_TIMEOUT_LONG,
                description="/stop to execute from REVIEW target bound to AUTO task",
            )

        assert submit_job_mock.await_count == 2
        assert submit_job_mock.await_args_list[0].args == (auto_task.id, "start_agent")
        assert submit_job_mock.await_args_list[1].args == (auto_task.id, "stop_agent")
        assert wait_job_mock.await_count == 2


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_runtime_commands_reject_non_auto_review_target(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, _overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR task for restart guard",
            "Ensure AUTO runtime commands reject non-AUTO review context",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban.ctx.api.move_task(pair_task.id, TaskStatus.REVIEW.value)
        await kanban._board.refresh_board()

        output_screen = await _open_task_output_via_enter(pilot, kanban, pair_task.id)
        embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
        embedded_overlay.set_target_scope(pair_task.id)
        embedded_overlay.show_for_task(pair_task, fullscreen=False)
        await wait_until(
            lambda: embedded_overlay._active_target().kind.value == "review",
            timeout=UI_TIMEOUT_LONG,
            description="Task Output overlay to bind REVIEW target for PAIR task",
        )

        embedded_input = embedded_overlay.query_one("#chat-overlay-input", Input)
        with patch.object(embedded_overlay, "notify") as notify_mock:
            embedded_input.focus()
            embedded_input.value = "/restart"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: notify_mock.call_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="/restart to reject non-AUTO review target",
            )
            restart_message = notify_mock.call_args.args[0]
            assert "/restart is available only for AUTO runtime tasks" in restart_message

            embedded_input.focus()
            embedded_input.value = "/stop"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: notify_mock.call_count >= 2,
                timeout=UI_TIMEOUT_LONG,
                description="/stop to reject non-AUTO review target",
            )
            stop_message = notify_mock.call_args.args[0]
            assert "/stop is available only for AUTO runtime tasks" in stop_message


@pytest.mark.asyncio
async def test_orchestrator_overlay_new_session_rotates_scope_when_empty(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        await wait_until(
            lambda: len(mock_agent_factory.get_all_agents()) >= 1,
            timeout=UI_TIMEOUT_LONG,
            description="initial orchestrator agent to initialize",
        )
        first_agent = mock_agent_factory.get_last_agent()
        assert first_agent is not None
        first_scope = first_agent.external_session_scope
        assert first_scope is not None
        assert first_scope.startswith("orchestrator-")
        assert not overlay.has_class("has-content")

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "/new session"
        await pilot.pause()
        await pilot.press("enter")

        await wait_until(
            lambda: len(mock_agent_factory.get_all_agents()) >= 2,
            timeout=UI_TIMEOUT_LONG,
            description="/new session to create a new orchestrator agent",
        )
        second_agent = mock_agent_factory.get_last_agent()
        assert second_agent is not None
        second_scope = second_agent.external_session_scope
        assert second_scope is not None
        assert second_scope.startswith("orchestrator-")
        assert second_scope != first_scope
        assert overlay._active_target().key.endswith(second_scope)


@pytest.mark.asyncio
async def test_orchestrator_overlay_close_session_removes_active_orchestrator_session(
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
        chat_input.value = "/new session"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: len(overlay._orchestrator_session_scope_ids) >= 2,
            timeout=UI_TIMEOUT_LONG,
            description="new orchestrator session to be added before close",
        )
        removed_scope = overlay._active_orchestrator_session_scope_id
        chat_input.focus()
        chat_input.value = "/close session"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: len(overlay._orchestrator_session_scope_ids) == 1,
            timeout=UI_TIMEOUT_LONG,
            description="active orchestrator session to be removed by /close session",
        )
        assert removed_scope not in overlay._orchestrator_session_scope_ids
        assert overlay._active_target().key.startswith("orchestrator:")
