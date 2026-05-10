"""Unit tests for the batched approval queue (engine-driven dispatch).

Phase 5c retargets these at :class:`PermissionUI` + a fake engine harness.
The queue dispatches decisions via ``engine.resolve_permission`` rather than
constructing ACP responses; we assert on the recorded call list.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import kagan.cli.chat._approval_batch as batch_module
import kagan.cli.chat._permission_ui as chat_acp_module
from kagan.cli.chat._permission_ui import PermissionUI
from kagan.core.permission import PermissionRequest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeConsole:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


class _FakeEngine:
    def __init__(self) -> None:
        self.resolve_calls: list[tuple[str, str, str, str | None]] = []
        self._lock = asyncio.Lock()

    async def resolve_permission(
        self,
        session_id: str,
        future_id: str,
        *,
        outcome: str,
        feedback: str | None = None,
    ) -> None:
        self.resolve_calls.append((session_id, future_id, outcome, feedback))


def _options() -> list[dict[str, Any]]:
    return [
        {"kind": "allow_once", "name": "Allow once", "option_id": "allow-1"},
        {"kind": "allow_always", "name": "Allow always", "option_id": "allow-all"},
        {"kind": "reject_once", "name": "Reject", "option_id": "deny-1"},
    ]


def _make_request(future_id: str, title: str) -> PermissionRequest:
    return PermissionRequest(
        future_id=future_id,
        tool_call={"title": title, "tool_call_id": f"tc-{title}"},
        options=_options(),
    )


def _make_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PermissionUI, _FakeEngine]:
    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: True)
    engine = _FakeEngine()
    ui = PermissionUI(engine=engine, renderer=None)
    return ui, engine


# ---------------------------------------------------------------------------
# Single-approval path (N=1 after debounce)
# ---------------------------------------------------------------------------


async def test_single_approval_routes_allow_once(monkeypatch: pytest.MonkeyPatch) -> None:
    ui, engine = _make_ui(monkeypatch)

    async def _fake_single(*_a: Any, **_kw: Any) -> tuple[int, str]:
        return (0, "")

    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_single)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.0)

    batch_called: list[bool] = []

    async def _fake_batch(*_a: Any, **_kw: Any) -> None:
        batch_called.append(True)

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)

    await ui.handle_request(_make_request("fid-1", "read_file"), session_id="s-1")

    assert engine.resolve_calls == [("s-1", "fid-1", "allow_once", None)]
    assert batch_called == [], "batch modal must not be invoked for N=1"


# ---------------------------------------------------------------------------
# Batch debounce groups concurrent calls
# ---------------------------------------------------------------------------


async def test_batch_debounce_groups_concurrent_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    panel_render_count: list[int] = [0]

    async def _fake_batch(
        items: Any,
        *,
        _resolve_item: Any,
        _resolve_all: Any,
        _reject_all: Any,
    ) -> None:
        panel_render_count[0] += 1
        _resolve_all("allow_once")

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)

    requests = [_make_request(f"fid-{i}", f"tool_{i}") for i in range(5)]
    await asyncio.gather(*[ui.handle_request(req, session_id="s-1") for req in requests])

    assert panel_render_count[0] == 1
    assert len(engine.resolve_calls) == 5
    for call in engine.resolve_calls:
        assert call[2] == "allow_once"


# ---------------------------------------------------------------------------
# Bulk options
# ---------------------------------------------------------------------------


async def test_batch_approve_all_routes_allow_once(monkeypatch: pytest.MonkeyPatch) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    async def _fake_batch(
        items: Any,
        *,
        _resolve_item: Any,
        _resolve_all: Any,
        _reject_all: Any,
    ) -> None:
        _resolve_all("allow_once")

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)

    requests = [_make_request(f"fid-{i}", f"bulk_{i}") for i in range(3)]
    await asyncio.gather(*[ui.handle_request(req, session_id="s-1") for req in requests])

    assert len(engine.resolve_calls) == 3
    for call in engine.resolve_calls:
        assert call[2] == "allow_once"


async def test_batch_deny_all_routes_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    async def _fake_batch(
        items: Any,
        *,
        _resolve_item: Any,
        _resolve_all: Any,
        _reject_all: Any,
    ) -> None:
        _reject_all()

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)

    requests = [_make_request(f"fid-{i}", f"deny_{i}") for i in range(3)]
    await asyncio.gather(*[ui.handle_request(req, session_id="s-1") for req in requests])

    assert len(engine.resolve_calls) == 3
    for call in engine.resolve_calls:
        assert call[2] == "deny"


# ---------------------------------------------------------------------------
# Sequential calls — separate single-approval renders
# ---------------------------------------------------------------------------


async def test_batch_does_not_group_sequential_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.020)

    panel_render_count: list[int] = [0]

    async def _fake_batch(*_a: Any, **_kw: Any) -> None:
        panel_render_count[0] += 1

    async def _fake_single(*_a: Any, **_kw: Any) -> tuple[int, str]:
        return (0, "")

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_single)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)

    t1 = asyncio.create_task(ui.handle_request(_make_request("fid-1", "seq_1"), session_id="s-1"))
    await asyncio.wait_for(t1, timeout=2.0)
    assert t1.done()

    t2 = asyncio.create_task(ui.handle_request(_make_request("fid-2", "seq_2"), session_id="s-1"))
    await asyncio.wait_for(t2, timeout=2.0)

    assert panel_render_count[0] == 0, "batch modal must not fire for N=1 windows"
    assert len(engine.resolve_calls) == 2


# ---------------------------------------------------------------------------
# Per-item feedback option (slot 3)
# ---------------------------------------------------------------------------


async def test_batch_feedback_option_on_focused_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    async def _fake_batch(
        items: Any,
        *,
        _resolve_item: Any,
        _resolve_all: Any,
        _reject_all: Any,
    ) -> None:
        _resolve_item(0, 0, "")
        _resolve_item(1, 4, "use a safer approach")
        _resolve_item(2, 0, "")

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)

    requests = [_make_request(f"fid-{i}", f"fb_tool_{i}") for i in range(3)]
    await asyncio.gather(*[ui.handle_request(req, session_id="s-1") for req in requests])

    assert len(engine.resolve_calls) == 3
    by_future = {call[1]: call for call in engine.resolve_calls}
    assert by_future["fid-0"][2] == "allow_once"
    assert by_future["fid-1"][2] == "deny_feedback"
    assert by_future["fid-1"][3] == "use a safer approach"
    assert by_future["fid-2"][2] == "allow_once"


# ---------------------------------------------------------------------------
# Tab navigation doesn't break resolution
# ---------------------------------------------------------------------------


async def test_tab_resolves_items_out_of_order(monkeypatch: pytest.MonkeyPatch) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    async def _fake_batch(
        items: Any,
        *,
        _resolve_item: Any,
        _resolve_all: Any,
        _reject_all: Any,
    ) -> None:
        _resolve_item(1, 0, "")
        _resolve_item(0, 0, "")

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)

    reqs = [_make_request("fid-a", "tab_tool_a"), _make_request("fid-b", "tab_tool_b")]
    await asyncio.gather(*[ui.handle_request(req, session_id="s-1") for req in reqs])

    assert len(engine.resolve_calls) == 2
    for call in engine.resolve_calls:
        assert call[2] == "allow_once"


# ---------------------------------------------------------------------------
# Session-allow short-circuit
# ---------------------------------------------------------------------------


async def test_session_approved_items_skip_batch_modal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    chat_acp_module._session_approvals.grant("session_tool")
    try:
        modal_calls: list[list[Any]] = []

        async def _capture_batch(
            items: Any,
            *,
            _resolve_item: Any,
            _resolve_all: Any,
            _reject_all: Any,
        ) -> None:
            modal_calls.append(list(items))
            _reject_all()

        async def _capture_single(
            tool_call: Any,
            *,
            permission_options: Any,
            queue_position: int = 1,
            queue_depth: int = 1,
        ) -> tuple[int, str]:
            modal_calls.append([tool_call])
            return 0, ""

        monkeypatch.setattr(batch_module, "_run_batch_modal_async", _capture_batch)
        monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _capture_single)
        monkeypatch.setattr(
            batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None
        )

        await asyncio.gather(
            ui.handle_request(_make_request("fid-1", "session_tool"), session_id="s-1"),
            ui.handle_request(_make_request("fid-2", "other_tool"), session_id="s-1"),
        )

        # Session-approved item is auto-allowed; only "other_tool" surfaces to
        # the modal (rendered as a single-approval panel because it's the only
        # remaining unresolved item).
        assert len(modal_calls) == 1
        assert len(modal_calls[0]) == 1
        title = modal_calls[0][0]
        title_str = title.get("title") if isinstance(title, dict) else getattr(title, "title", None)
        assert title_str == "other_tool"
        by_future = {call[1]: call for call in engine.resolve_calls}
        assert by_future["fid-1"][2] == "allow_once"
        assert by_future["fid-2"][2] in {"allow_once", "deny"}
    finally:
        chat_acp_module._session_approvals.revoke("session_tool")


# ---------------------------------------------------------------------------
# SIGINT cancellation
# ---------------------------------------------------------------------------


async def test_sigint_cancels_pending_items(monkeypatch: pytest.MonkeyPatch) -> None:
    ui, engine = _make_ui(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 10.0)

    fut1 = await ui._batch_queue.enqueue(
        _options(),
        {"title": "sigint_tool_1"},
        future_id="fid-1",
        session_id="s-1",
    )
    fut2 = await ui._batch_queue.enqueue(
        _options(),
        {"title": "sigint_tool_2"},
        future_id="fid-2",
        session_id="s-1",
    )

    assert not fut1.done()
    assert not fut2.done()

    ui.cancel_batch_queue()
    # Allow the engine.resolve_permission ensure_future calls to run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert fut1.done()
    assert fut2.done()

    by_future = {call[1]: call for call in engine.resolve_calls}
    assert by_future["fid-1"][2] == "deny"
    assert by_future["fid-2"][2] == "deny"
