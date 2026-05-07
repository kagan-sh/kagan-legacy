"""Behavioral tests for RunningAgentsBar.

Per testing.md: behavioral specs, targeted waits only.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Agents Bar Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})
    yield driver
    await driver.teardown()


async def test_empty_state_hidden_when_no_agents(board: KaganDriver) -> None:
    """When no agents are running, the bar is hidden (no has-agents class)."""
    from textual.app import App, ComposeResult

    from kagan.tui.widgets.running_agents_bar import RunningAgentsBar

    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield RunningAgentsBar(poll_interval=0)

    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.query_one(RunningAgentsBar)
        # Bar is hidden when no agents — has-agents class absent
        assert not bar.has_class("has-agents")


async def test_agent_rows_populated_from_rows_reactive(board: KaganDriver) -> None:
    """Setting _rows reactive causes rows to appear and has-agents class is set."""
    from datetime import datetime

    from textual.app import App, ComposeResult
    from textual.widgets import Static

    from kagan.core._sessions_query import ActiveAgentRow
    from kagan.tui.widgets.running_agents_bar import RunningAgentsBar

    fake_row = ActiveAgentRow(
        task_id="task-aaa",
        task_title="Build login",
        task_status="in_progress",
        session_id="sess-bbb-1234",
        agent_role="worker",
        agent_backend="claude",
        session_status="running",
        started_at=datetime.now(tz=UTC),
        last_event_at=None,
        input_tokens=1000,
        output_tokens=500,
    )

    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield RunningAgentsBar(poll_interval=0)

    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.query_one(RunningAgentsBar)
        bar._rows = [fake_row]
        await pilot.pause()

        assert bar.has_class("has-agents")
        labels = list(bar.query(Static))
        texts = [str(lb.content) for lb in labels]
        assert any("Build login" in t for t in texts)
        assert any("worker" in t.lower() or "▶" in t for t in texts)


async def test_enter_on_row_fires_agent_selected_message(board: KaganDriver) -> None:
    """Pressing Enter on an agent row fires the on_select callback with session_id."""
    from datetime import datetime

    from textual.app import App, ComposeResult
    from textual.widgets import ListView

    from kagan.core._sessions_query import ActiveAgentRow
    from kagan.tui.widgets.running_agents_bar import RunningAgentsBar

    selected: list[tuple[str, str | None, str]] = []

    def _on_select(session_id: str, role: str | None, task_id: str) -> None:
        selected.append((session_id, role, task_id))

    fake_row = ActiveAgentRow(
        task_id="task-xyz",
        task_title="Fix auth",
        task_status="in_progress",
        session_id="sess-12345678-abcd",
        agent_role="worker",
        agent_backend="claude",
        session_status="running",
        started_at=datetime.now(tz=UTC),
        last_event_at=None,
        input_tokens=None,
        output_tokens=None,
    )

    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield RunningAgentsBar(on_select=_on_select, poll_interval=0)

    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.query_one(RunningAgentsBar)
        bar._rows = [fake_row]
        await pilot.pause()

        lv = bar.query_one(ListView)
        lv.focus()
        await pilot.press("enter")
        await pilot.pause()

        assert len(selected) == 1
        session_id, role, task_id = selected[0]
        assert session_id == "sess-12345678-abcd"
        assert role == "worker"
        assert task_id == "task-xyz"
