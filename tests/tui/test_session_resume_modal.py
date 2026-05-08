from typing import Any, cast

import pytest
from tests.helpers.async_utils import wait_for
from tests.helpers.driver import KaganDriver
from textual.css.query import NoMatches
from textual.widgets import OptionList


async def save_chat_session(client: Any, session: dict[str, Any]) -> None:
    """Local test helper — upsert a session dict via the aggregate."""
    sid = str(session.get("id") or "").strip()
    if not sid:
        return
    history: list[tuple[str, str]] = []
    for pair in session.get("orchestrator_history") or []:
        if isinstance(pair, list | tuple) and len(pair) == 2:
            role = str(pair[0]).strip()
            content = str(pair[1]).strip()
            if role and content:
                history.append((role, content))
    raw_backend = session.get("agent_backend")
    backend: str | None = (
        raw_backend if isinstance(raw_backend, str) and raw_backend.strip() else None
    )
    raw_project = session.get("project_id")
    project: str | None = (
        raw_project if isinstance(raw_project, str) and raw_project.strip() else None
    )
    await client.chat_sessions.upsert_with_history(
        sid,
        label=str(session.get("label") or f"Session {sid[:8]}").strip(),
        source=str(session.get("source") or "repl") or "repl",
        agent_backend=backend,
        project_id=project,
        history=history,
    )


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
        await app.orchestrator_sessions.ensure_loaded()
        assert app.orchestrator_sessions.current_session_id() == "resume01"

    await driver.teardown()


async def test_resume_modal_hides_sessions_without_project_binding(tmp_path) -> None:
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
