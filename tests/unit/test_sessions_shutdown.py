import asyncio
from typing import Any, cast

import pytest

from kagan.core._sessions import Sessions
from kagan.core.enums import SessionEventType

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _FakeEvents:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, Any, dict[str, Any], str | None, bool]] = []

    async def emit(
        self,
        task_id: str,
        event_type: Any,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        persist: bool = True,
    ) -> None:
        self.emitted.append((task_id, event_type, payload, session_id, persist))


async def _stub_get_task(_task_id: str) -> Any:
    raise AssertionError("_get_task should not run in this shutdown path")


def _stub_set_status(_task_id: str, _status: Any) -> Any:
    raise AssertionError("_set_status should not run in this shutdown path")


async def _stub_ensure_workspace(_task_id: str) -> Any:
    raise AssertionError("_ensure_workspace should not run in this shutdown path")


async def test_handle_acp_done_ignores_executor_shutdown_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    async def fake_to_thread(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Executor shutdown has been called")

    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)

    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task

    await sessions._handle_acp_done(done_task, "task-1", "session-1")
    assert events.emitted == []


async def test_make_acp_callback_emits_output_chunks_without_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OUTPUT_CHUNK events must not be persisted to avoid DB bloat."""
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    monkeypatch.setattr(
        "kagan.core._acp.map_acp_update_to_event",
        lambda _update: (SessionEventType.OUTPUT_CHUNK, {"text": "hello"}),
    )

    callback = sessions._make_acp_callback("task-1", "session-1")
    await callback("acp-session-1", object())

    assert events.emitted == [
        ("task-1", SessionEventType.OUTPUT_CHUNK, {"text": "hello"}, "session-1", False)
    ]


async def test_handle_acp_done_reraises_unrelated_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _FakeEvents()
    sessions = Sessions(
        cast("Any", object()),
        cast("Any", events),
        get_task=_stub_get_task,
        set_status=_stub_set_status,
        ensure_workspace=_stub_ensure_workspace,
    )

    async def fake_to_thread(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("unexpected runtime failure")

    monkeypatch.setattr("kagan.core._sessions.asyncio.to_thread", fake_to_thread)

    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task

    with pytest.raises(RuntimeError, match="unexpected runtime failure"):
        await sessions._handle_acp_done(done_task, "task-2", "session-2")
