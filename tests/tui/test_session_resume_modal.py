from typing import Any, cast

import pytest
from tests.helpers.driver import KaganDriver
from textual.widgets import Button, OptionList

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def test_welcome_resume_session_button_opens_modal_and_resumes_project(
    tmp_path,
) -> None:
    from kagan.chat.sessions import save_chat_session
    from kagan.tui import KaganApp

    driver = await KaganDriver.boot(tmp_path)
    project_id = await driver.create_project("Resume Project")
    assert driver._ctx is not None
    await save_chat_session(
        cast("Any", driver._ctx),
        {
            "id": "resume01",
            "label": "TUI session",
            "source": "tui-orchestrator",
            "agent_backend": "codex",
            "orchestrator_history": [["user", "continue"], ["assistant", "ready"]],
            "messages_rendered": ["You: continue", "Agent: ready"],
            "project_id": project_id,
        },
    )

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "welcome-screen"
        button = app.screen.query_one("#welcome-resume-session", Button)
        assert "Resume recent session" in str(button.label)

        await pilot.click("#welcome-resume-session")
        await pilot.pause()

        assert app.screen.id == "session-resume-modal"
        option_list = app.screen.query_one("#session-resume-options", OptionList)
        assert option_list.option_count == 1

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert app.screen.id == "kanban-screen"
        assert app.project is not None
        assert app.project.id == project_id
        assert app.orchestrator_sessions.current_session_id() == "resume01"

    await driver.teardown()
