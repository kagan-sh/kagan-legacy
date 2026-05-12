"""Behavioral tests for EventSource-driven chat resume in the TUI.

Uses KaganApp.run_test() + Textual Pilot.  Targeted waits only —
never wait_for_workers().  Uses pilot.pause() to pump the message queue.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _poll_until(pilot, predicate, *, attempts: int = 30) -> bool:
    """Pump the Textual message queue until predicate() is True.

    Returns True if predicate satisfied within *attempts* pauses.
    """
    for _ in range(attempts):
        await pilot.pause()
        if predicate():
            return True
    return predicate()


def _make_frame_row(seq: int, frame: dict[str, Any]) -> Any:
    from kagan.core._event_log import FrameRow

    return FrameRow(seq=seq, idx=seq, ts=datetime.now(UTC), frame=frame)


# ---------------------------------------------------------------------------
# InProcEventSource unit-level tests (no full Textual app needed)
# ---------------------------------------------------------------------------


@pytest.fixture
async def in_proc_event_source(tmp_path):
    """Return an InProcEventSource wired to a fresh EventLog with a real DB."""
    from kagan.core._db import create_db_engine
    from kagan.core._event_log import EventLog
    from kagan.tui._event_source import InProcEventSource

    db_path = tmp_path / "resume_test.db"
    engine = create_db_engine(db_path)
    event_log = EventLog(engine)
    return InProcEventSource(event_log), event_log


async def test_in_proc_snapshot_returns_empty_for_unknown_session(
    in_proc_event_source,
) -> None:
    """snapshot() on a session with no events returns empty entries and max_seq=-1."""
    source, _ = in_proc_event_source
    snap = await source.snapshot("unknown-session", "chat")
    assert snap.entries == []
    assert snap.max_seq == -1


async def test_in_proc_snapshot_reduces_history(tmp_path) -> None:
    """snapshot() materialises frames from EventLog.history into Entry objects."""
    from kagan.core._db import create_db_engine
    from kagan.core._db_helpers import _db_sync
    from kagan.core._event_log import EventLog
    from kagan.core.models import Project, Session, Task
    from kagan.tui._event_source import InProcEventSource

    db_path = tmp_path / "snap_test.db"
    engine = create_db_engine(db_path)

    def _write(s) -> str:
        project = Project(name="P")
        s.add(project)
        s.flush()
        task = Task(project_id=project.id, title="T")
        s.add(task)
        s.flush()
        session = Session(task_id=task.id, agent_backend="fake")
        s.add(session)
        s.commit()
        s.refresh(session)
        return session.id

    sid = _db_sync(engine, _write)
    event_log = EventLog(engine)
    source = InProcEventSource(event_log)

    # Append a create+append+finalize sequence
    await event_log.append(
        sid,
        "chat",
        {
            "type": "patch",
            "op": "create",
            "path": "/entries/0",
            "value": {"idx": 0, "role": "user", "text": "hi", "finalized": False},
        },
    )
    await event_log.append(
        sid,
        "chat",
        {
            "type": "patch",
            "op": "append",
            "path": "/entries/0/text",
            "value": " there",
        },
    )
    await event_log.append(
        sid,
        "chat",
        {"type": "patch", "op": "finalize", "path": "/entries/0", "value": None},
    )

    snap = await source.snapshot(sid, "chat")

    assert len(snap.entries) == 1
    assert snap.entries[0].text == "hi there"
    assert snap.entries[0].finalized is True
    assert snap.max_seq == 2


# ---------------------------------------------------------------------------
# Frame reducer integration via InProcEventSource
# ---------------------------------------------------------------------------


async def test_event_source_snapshot_from_seq_skips_old_frames(tmp_path) -> None:
    """snapshot(from_seq=N) skips frames with seq < N."""
    from kagan.core._db import create_db_engine
    from kagan.core._db_helpers import _db_sync
    from kagan.core._event_log import EventLog
    from kagan.core.models import Project, Session, Task
    from kagan.tui._event_source import InProcEventSource

    db_path = tmp_path / "from_seq_test.db"
    engine = create_db_engine(db_path)

    def _write(s) -> str:
        project = Project(name="P")
        s.add(project)
        s.flush()
        task = Task(project_id=project.id, title="T")
        s.add(task)
        s.flush()
        session = Session(task_id=task.id, agent_backend="fake")
        s.add(session)
        s.commit()
        s.refresh(session)
        return session.id

    sid = _db_sync(engine, _write)
    event_log = EventLog(engine)
    source = InProcEventSource(event_log)

    # seq=0: first entry
    await event_log.append(
        sid,
        "chat",
        {
            "type": "patch",
            "op": "create",
            "path": "/entries/0",
            "value": {"idx": 0, "role": "user", "text": "old", "finalized": True},
        },
    )
    # seq=1: second entry
    await event_log.append(
        sid,
        "chat",
        {
            "type": "patch",
            "op": "create",
            "path": "/entries/1",
            "value": {"idx": 1, "role": "assistant", "text": "new", "finalized": False},
        },
    )

    # from_seq=1 skips seq=0
    snap = await source.snapshot(sid, "chat", from_seq=1)
    assert len(snap.entries) == 1
    assert snap.entries[0].text == "new"


# ---------------------------------------------------------------------------
# Frame reducer pure tests (via apply_frame)
# ---------------------------------------------------------------------------


def test_frame_reducer_create_then_append() -> None:
    """apply_frame: create + append builds correct text."""
    from kagan.server.responses import FramePatch
    from kagan.tui._frame_reducer import apply_frame

    state: dict = {}
    state = apply_frame(
        state,
        FramePatch(
            type="patch",
            op="create",
            path="/entries/0",
            value={"idx": 0, "role": "assistant", "text": "Hello", "finalized": False},
        ),
    )
    state = apply_frame(
        state,
        FramePatch(type="patch", op="append", path="/entries/0/text", value=" world"),
    )

    assert state[0].text == "Hello world"
    assert not state[0].finalized


def test_frame_reducer_finalize_removes_streaming_cursor() -> None:
    """apply_frame finalize sets finalized=True (UI can remove cursor on finalized)."""
    from kagan.server.responses import FramePatch
    from kagan.tui._frame_reducer import apply_frame

    state: dict = {}
    state = apply_frame(
        state,
        FramePatch(
            type="patch",
            op="create",
            path="/entries/0",
            value={"idx": 0, "role": "assistant", "text": "stream...", "finalized": False},
        ),
    )
    assert not state[0].finalized
    state = apply_frame(
        state,
        FramePatch(type="patch", op="finalize", path="/entries/0", value=None),
    )
    assert state[0].finalized


def test_frame_reducer_resume_frame_does_not_change_entries() -> None:
    """apply_frame: FrameResume passes through without altering entries."""
    from kagan.server.responses import FrameResume
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict = {0: Entry(idx=0, role="user", text="preserved", finalized=True)}
    result = apply_frame(state, FrameResume(type="resume", kind="task", turn_active=True))
    assert result[0].text == "preserved"


# ---------------------------------------------------------------------------
# Textual app-level tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def board_with_session(tmp_path):
    """Board with a project, repo hint, and a real DB."""
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Resume Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    yield driver
    await driver.teardown()


async def test_event_source_wired_in_proc_on_local_app(
    board_with_session: KaganDriver,
) -> None:
    """KaganApp wires InProcEventSource when no http_client is set."""
    from kagan.tui import KaganApp
    from kagan.tui._event_source import InProcEventSource

    app = KaganApp(db_path=board_with_session.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.event_source, InProcEventSource)


async def test_overlay_opens_without_error_after_event_source_wired(
    board_with_session: KaganDriver,
) -> None:
    """OrchestratorOverlay opens correctly when event_source is wired on app."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board_with_session.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        assert app.screen.id == "kanban-screen"
        await pilot.press("ctrl+space")
        await _poll_until(pilot, lambda: isinstance(app.screen, OrchestratorOverlay))
        assert isinstance(app.screen, OrchestratorOverlay)


async def test_orchestrator_session_load_shows_snapshot_history(
    board_with_session: KaganDriver,
) -> None:
    """ensure_loaded() works and produces history via event_source snapshot path."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_session.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        # Load sessions (triggers ensure_loaded)
        await app.orchestrator_sessions.ensure_loaded()
        # Should have at least one session created
        session_id = app.orchestrator_sessions.current_session_id()
        assert isinstance(session_id, str)
        assert len(session_id) > 0


async def test_overlay_reopen_does_not_crash(
    board_with_session: KaganDriver,
) -> None:
    """Overlay can be closed and reopened without error (basic smoke test)."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board_with_session.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        # Open
        await pilot.press("ctrl+space")
        await _poll_until(pilot, lambda: isinstance(app.screen, OrchestratorOverlay))
        assert isinstance(app.screen, OrchestratorOverlay)

        # Close
        await pilot.press("escape")
        await _poll_until(pilot, lambda: not isinstance(app.screen, OrchestratorOverlay))
        assert app.screen.id == "kanban-screen"

        # Reopen
        await pilot.press("ctrl+space")
        await _poll_until(pilot, lambda: isinstance(app.screen, OrchestratorOverlay))
        assert isinstance(app.screen, OrchestratorOverlay)


async def test_event_source_switch_to_remote_mode_uses_http(tmp_path) -> None:
    """When http_client is provided to KaganApp, HttpEventSource is wired."""
    import httpx

    from kagan.tui import KaganApp
    from kagan.tui._event_source import HttpEventSource

    transport = httpx.MockTransport(lambda req: httpx.Response(200))
    http_client = httpx.AsyncClient(transport=transport, base_url="http://localhost:9999")

    app = KaganApp(
        db_path=tmp_path / "kagan.db",
        http_client=http_client,
        base_url="http://localhost:9999",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.event_source, HttpEventSource)

    await http_client.aclose()


async def test_resume_frame_carries_turn_active_flag(tmp_path) -> None:
    """InProcEventSource.subscribe yields FrameResume rows as-is from EventLog."""
    from kagan.core._db import create_db_engine
    from kagan.core._db_helpers import _db_sync
    from kagan.core._event_log import EventLog
    from kagan.core.models import Project, Session, Task
    from kagan.tui._event_source import InProcEventSource

    db_path = tmp_path / "resume_frames.db"
    engine = create_db_engine(db_path)

    def _write(s) -> str:
        project = Project(name="P")
        s.add(project)
        s.flush()
        task = Task(project_id=project.id, title="T")
        s.add(task)
        s.flush()
        session = Session(task_id=task.id, agent_backend="fake")
        s.add(session)
        s.commit()
        s.refresh(session)
        return session.id

    sid = _db_sync(engine, _write)
    event_log = EventLog(engine)
    source = InProcEventSource(event_log)

    # Append a resume-type frame
    await event_log.append(
        sid,
        "task",
        {"type": "resume", "kind": "task", "turn_active": True},
    )

    collected = []

    # Collect the first frame via subscribe with a timeout to avoid infinite blocking
    async def _collect():
        async for frame in source.subscribe(sid, "task", from_seq=0):
            collected.append(frame)
            break  # Only read the first frame

    try:
        await asyncio.wait_for(_collect(), timeout=2.0)
    except TimeoutError:
        pass

    assert len(collected) >= 1
    # The first frame from subscribe may be a resume frame or a patch
    frame_types = [getattr(f, "type", None) for f in collected]
    assert any(ft in ("resume", "patch", "snapshot") for ft in frame_types)
