"""Behavioral tests: Chat sessions via DB tables.

Uses KaganDriver only -- no direct imports from kagan.cli.chat.sessions
or kagan.core._* private modules.
"""

import pytest

from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.core, pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create(
    board: KaganDriver,
    *,
    source: str = "test",
    label: str | None = None,
    project_id: str | None = None,
):
    return await board.chat_create_session(source=source, label=label, project_id=project_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_create_session_persists_across_client_boots(tmp_path) -> None:
    """A session created in one KaganCore instance is visible after a fresh boot."""
    driver1 = await KaganDriver.boot(tmp_path)
    await driver1.create_project("Boot Test")
    session = await driver1.chat_create_session(source="repl", label="Persistence Check")
    session_id = session["id"]
    await driver1.teardown()

    driver2 = await KaganDriver.boot(tmp_path)
    try:
        fetched = await driver2.chat_get_session(session_id)
        assert fetched is not None
        assert fetched["id"] == session_id
        assert fetched["label"] == "Persistence Check"
    finally:
        await driver2.teardown()


async def test_messages_append_under_session_in_order(board: KaganDriver) -> None:
    """append_chat_message inserts messages; get_chat_session returns them ordered by id."""
    session = await board.chat_create_session(source="repl", label="Order Test")
    sid = session["id"]

    await board.chat_append_message(sid, "user", "Hello")
    await board.chat_append_message(sid, "assistant", "Hi there")
    await board.chat_append_message(sid, "user", "How are you?")

    fetched = await board.chat_get_session(sid)
    assert fetched is not None
    history = fetched["orchestrator_history"]
    assert len(history) == 3
    assert history[0] == ["user", "Hello"]
    assert history[1] == ["assistant", "Hi there"]
    assert history[2] == ["user", "How are you?"]


async def test_session_list_filters_by_project_when_specified(board: KaganDriver) -> None:
    """list_chat_sessions with project_id returns only sessions for that project."""
    project_id = board._driver._ctx.active_project_id  # type: ignore[union-attr]

    await board.chat_create_session(source="repl", label="With Project", project_id=project_id)
    await board.chat_create_session(source="repl", label="Without Project", project_id=None)

    with_project = await board.chat_list_sessions(project_id=project_id)
    without_project = await board.chat_list_sessions(project_id=None)

    with_project_labels = [s["label"] for s in with_project]
    all_labels = [s["label"] for s in without_project]

    assert "With Project" in with_project_labels
    assert "Without Project" not in with_project_labels
    assert "With Project" in all_labels
    assert "Without Project" in all_labels


async def test_session_list_returns_all_when_no_filter(board: KaganDriver) -> None:
    """list_chat_sessions without filters returns all sessions ordered newest-first."""
    await board.chat_create_session(source="repl", label="First")
    await board.chat_create_session(source="repl", label="Second")
    await board.chat_create_session(source="repl", label="Third")

    all_sessions = await board.chat_list_sessions()
    labels = [s["label"] for s in all_sessions]

    assert "First" in labels
    assert "Second" in labels
    assert "Third" in labels


async def test_terminated_partial_message_is_visible_in_history(board: KaganDriver) -> None:
    """A message with terminated_at_user_request=True is still returned in orchestrator_history."""
    session = await board.chat_create_session(source="repl", label="Terminated Test")
    sid = session["id"]

    await board.chat_append_message(sid, "user", "Start something")
    await board.chat_append_message(sid, "assistant", "Partial respon", terminated=True)

    fetched = await board.chat_get_session(sid)
    assert fetched is not None
    history = fetched["orchestrator_history"]
    # Both messages should appear
    assert len(history) == 2
    assert history[1] == ["assistant", "Partial respon"]


async def test_delete_session_removes_messages_via_cascade(board: KaganDriver) -> None:
    """delete_chat_session removes the session and its messages cascade-deleted."""
    session = await board.chat_create_session(source="repl", label="Delete Me")
    sid = session["id"]

    await board.chat_append_message(sid, "user", "Please delete me")
    await board.chat_append_message(sid, "assistant", "Okay")

    deleted = await board.chat_delete_session(sid)
    assert deleted is True

    fetched = await board.chat_get_session(sid)
    assert fetched is None

    # Verify second delete returns False
    deleted_again = await board.chat_delete_session(sid)
    assert deleted_again is False
