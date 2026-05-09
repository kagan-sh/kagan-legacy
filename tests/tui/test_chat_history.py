"""Tests for persistent chat input history in ChatPanel / ChatWidget.

History file: platformdirs.user_data_dir("kagan") / "history" / "<project_id>.jsonl"
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path: Path) -> KaganDriver:
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("History Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})
    await driver.create_task("History task")
    yield driver  # type: ignore[misc]
    await driver.teardown()


async def test_up_arrow_cycles_to_most_recent_entry(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressing Up in the chat input shows the most recent history entry."""
    import os

    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import orchestrator_overlay as orch

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(orch, "send_chat_message", fake_send_chat_message)

    project_id = board._ctx.active_project_id
    # Seed the history file in the KAGAN_DATA_DIR that the conftest redirects to
    data_root = os.environ.get("KAGAN_DATA_DIR", "")
    history_dir = Path(data_root) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / f"{project_id}.jsonl"
    history_file.write_text(
        json.dumps({"text": "first"}) + "\n" + json.dumps({"text": "second"}) + "\n",
        encoding="utf-8",
    )

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        from kagan.tui.widgets.chat import ChatPanel

        monkeypatch.setattr(
            ChatPanel,
            "_handle_overlay_cycle_agent",
            lambda self, event: False,
        )

        panel = app.screen.query_one(ChatPanel)
        panel.set_project_id(project_id)
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        await pilot.press("up")
        await pilot.pause()
        assert input_widget.value == "second"


async def test_down_arrow_returns_to_working_draft(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressing Up then Down restores the partially-typed working draft."""
    import os

    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import orchestrator_overlay as orch

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(orch, "send_chat_message", fake_send_chat_message)

    project_id = board._ctx.active_project_id
    data_root = os.environ.get("KAGAN_DATA_DIR", "")
    history_dir = Path(data_root) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / f"{project_id}.jsonl"
    history_file.write_text(
        json.dumps({"text": "alpha"}) + "\n",
        encoding="utf-8",
    )

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        from kagan.tui.widgets.chat import ChatPanel

        monkeypatch.setattr(
            ChatPanel,
            "_handle_overlay_cycle_agent",
            lambda self, event: False,
        )

        panel = app.screen.query_one(ChatPanel)
        panel.set_project_id(project_id)
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        # Type a partial draft
        input_widget.value = "draft"
        await pilot.pause()

        # Navigate to history
        await pilot.press("up")
        await pilot.pause()
        assert input_widget.value == "alpha"

        # Navigate back to working draft
        await pilot.press("down")
        await pilot.pause()
        assert input_widget.value == "draft"


async def test_submit_persists_to_history_file(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submitting a message appends it to the JSONL history file."""
    import os

    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import orchestrator_overlay as orch

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(orch, "send_chat_message", fake_send_chat_message)

    project_id = board._ctx.active_project_id
    data_root = os.environ.get("KAGAN_DATA_DIR", "")
    history_dir = Path(data_root) / "history"

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        from kagan.tui.widgets.chat import ChatPanel

        panel = app.screen.query_one(ChatPanel)
        panel.set_project_id(project_id)
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "hello"
        await pilot.press("enter")
        await pilot.pause()

    # After the app exits, check the history file
    history_file = history_dir / f"{project_id}.jsonl"
    assert history_file.exists(), "History file should be created"
    lines = [
        json.loads(line)
        for line in history_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    texts = [entry["text"] for entry in lines]
    assert "hello" in texts


async def test_history_disabled_when_opt_out_key_false(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When persist_input_history=False no JSONL file is written."""
    import os

    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import orchestrator_overlay as orch

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(orch, "send_chat_message", fake_send_chat_message)

    project_id = board._ctx.active_project_id
    data_root = os.environ.get("KAGAN_DATA_DIR", "")
    history_dir = Path(data_root) / "history"

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        from kagan.tui.widgets.chat import ChatPanel

        panel = app.screen.query_one(ChatPanel)
        # Set persist=False to opt out of file persistence
        panel.set_project_id(project_id, persist=False)
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "no persist"
        await pilot.press("enter")
        await pilot.pause()

    history_file = history_dir / f"{project_id}.jsonl"
    assert not history_file.exists(), "No history file should be written when persist=False"
