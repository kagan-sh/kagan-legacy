from typing import Any, cast

import pytest
from tests.helpers.async_utils import wait_for
from tests.helpers.driver import KaganDriver
from textual.css.query import NoMatches
from textual.widgets import OptionList


def _has_options(app, widget_id: str) -> bool:
    """Check if an OptionList widget exists and has options, without raising."""
    try:
        return app.screen.query_one(f"#{widget_id}", OptionList).option_count > 0
    except NoMatches:
        return False


pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def test_session_resume_modal_opens_and_resumes_project(
    tmp_path,
) -> None:
    from kagan.cli.chat.sessions import save_chat_session
    from kagan.tui import KaganApp
    from kagan.tui.screens.session_resume_modal import SessionResumeModal

    driver = await KaganDriver.boot(tmp_path)
    project_id = await driver.create_project("Resume Project")
    await driver.settings_update({"open_last_project_on_startup": "true"})
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
        assert app.screen.id == "kanban-screen"

        # Push the SessionResumeModal directly (previously opened via welcome button)
        app.push_screen(SessionResumeModal())
        await wait_for(lambda: app.screen.id == "session-resume-modal", pump_delay=0.05)

        await wait_for(
            lambda: _has_options(app, "session-resume-options"),
            pump_delay=0.05,
        )
        option_list = app.screen.query_one("#session-resume-options", OptionList)
        assert option_list.option_count == 1

        await pilot.press("enter")
        await wait_for(lambda: app.screen.id == "kanban-screen", pump_delay=0.05)
        assert app.project is not None
        assert app.project.id == project_id
        assert app.orchestrator_sessions.current_session_id() == "resume01"

    await driver.teardown()


async def test_resume_modal_hides_sessions_without_project_binding(tmp_path) -> None:
    from kagan.cli.chat.sessions import save_chat_session
    from kagan.tui import KaganApp
    from kagan.tui.screens.session_resume_modal import SessionResumeModal

    driver = await KaganDriver.boot(tmp_path)
    project_id = await driver.create_project("Resume Project")
    assert driver._ctx is not None
    await save_chat_session(
        cast("Any", driver._ctx),
        {
            "id": "resume02",
            "label": "TUI session",
            "source": "tui-orchestrator",
            "agent_backend": "codex",
            "orchestrator_history": [["user", "continue"], ["assistant", "ready"]],
            "messages_rendered": ["You: continue", "Agent: ready"],
            "project_id": project_id,
        },
    )
    await save_chat_session(
        cast("Any", driver._ctx),
        {
            "id": "legacy01",
            "label": "Old session",
            "source": "tui-orchestrator",
            "agent_backend": "claude-code",
            "orchestrator_history": [["user", "old"], ["assistant", "state"]],
            "messages_rendered": ["You: old", "Agent: state"],
        },
    )

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(SessionResumeModal())
        await wait_for(lambda: app.screen.id == "session-resume-modal", pump_delay=0.05)

        await wait_for(
            lambda: _has_options(app, "session-resume-options"),
            pump_delay=0.05,
        )
        option_list = app.screen.query_one("#session-resume-options", OptionList)
        assert option_list.option_count == 1

    await driver.teardown()
