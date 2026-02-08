from __future__ import annotations

from typing import cast

import pytest
from tests.helpers.wait import type_text, wait_for_planner_ready, wait_for_screen, wait_for_widget

from kagan.ui.screens.kanban import KanbanScreen
from kagan.ui.screens.planner import PlannerInput, PlannerScreen
from kagan.ui.widgets.slash_complete import SlashComplete


@pytest.mark.asyncio
async def test_planner_slash_complete_opens_without_reactive_error(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        kanban.action_open_planner()
        await wait_for_screen(pilot, PlannerScreen, timeout=10.0)
        await wait_for_planner_ready(pilot, timeout=10.0)

        planner = cast("PlannerScreen", pilot.app.screen)
        planner.query_one(PlannerInput).focus()
        await type_text(pilot, "/")
        await wait_for_widget(pilot, "#slash-complete", timeout=5.0)
        planner.query_one("#slash-complete", SlashComplete)
