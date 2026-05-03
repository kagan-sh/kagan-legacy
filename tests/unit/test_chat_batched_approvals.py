"""Unit tests for batched approval queue in kg chat.

All tests are pure-unit: no real terminal, no prompt_toolkit Application
launched.  ``_run_approval_panel_async`` and ``_run_batch_modal_async`` are
monkeypatched to simulate user responses.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from acp.schema import PermissionOption, ToolCallStart

import kagan.cli.chat._approval_batch as batch_module
import kagan.cli.chat._chat_acp as chat_acp_module
import kagan.cli.chat.controller as chat_controller

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Shared test fixtures / helpers
# ---------------------------------------------------------------------------


def _make_tool_call(title: str = "task_get") -> ToolCallStart:
    return ToolCallStart(title=title, tool_call_id=f"tc-{title}", session_update="tool_call")


def _make_options() -> list[PermissionOption]:
    return [
        PermissionOption(kind="allow_once", name="Allow once", option_id="allow-1"),
        PermissionOption(kind="allow_always", name="Allow always", option_id="allow-all"),
        PermissionOption(kind="reject_once", name="Reject", option_id="deny-1"),
    ]


class _FakeConsole:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    yolo: bool = False,
) -> chat_controller._OrchestratorACPClient:
    """Build an _OrchestratorACPClient with console patched."""
    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: True)
    client = chat_controller._OrchestratorACPClient(yolo=yolo)
    return client


# ---------------------------------------------------------------------------
# test_single_approval_unchanged
# ---------------------------------------------------------------------------


async def test_single_approval_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """N=1: existing single-approval panel is used; batch panel is never rendered."""
    client = _make_client(monkeypatch)

    # Patch _run_approval_panel_async to return allow_once (index 0)
    async def _fake_single(*_a: Any, **_kw: Any) -> tuple[int, str]:
        return (0, "")

    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_single)
    # Ensure batch modal is NOT called
    batch_called: list[bool] = []

    async def _fake_batch(*_a: Any, **_kw: Any) -> None:
        batch_called.append(True)

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)

    # Override debounce to fire immediately
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.0)

    opts = _make_options()
    tool = _make_tool_call("read_file")

    response = await client.request_permission(opts, "session-1", tool)

    assert response.outcome.outcome == "selected"
    assert response.outcome.option_id == "allow-1"
    assert batch_called == [], "batch modal must not be invoked for N=1"


# ---------------------------------------------------------------------------
# test_batch_debounce_groups_concurrent_calls
# ---------------------------------------------------------------------------


async def test_batch_debounce_groups_concurrent_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5 concurrent calls within the debounce window → one combined panel, all resolved."""
    client = _make_client(monkeypatch)
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
        # Approve all remaining (simulate option 5)
        _resolve_all("allow_once")

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    # Also patch run_in_terminal to be a no-op so we don't need a real event loop
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)  # type: ignore[attr-defined]

    opts = _make_options()
    tools = [_make_tool_call(f"tool_{i}") for i in range(5)]

    # Fire all 5 concurrently — they should all land in the same debounce window
    responses = await asyncio.gather(
        *[client.request_permission(opts, "session-1", t) for t in tools]
    )

    assert panel_render_count[0] == 1, "batch panel must render exactly once"
    assert len(responses) == 5
    for r in responses:
        assert r.outcome.outcome == "selected"


# ---------------------------------------------------------------------------
# test_batch_approve_all_option (option 5 / digit 5)
# ---------------------------------------------------------------------------


async def test_batch_approve_all_option(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selecting option 5 resolves all pending items as allow_once."""
    client = _make_client(monkeypatch)
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
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)  # type: ignore[attr-defined]

    opts = _make_options()
    tools = [_make_tool_call(f"bulk_{i}") for i in range(3)]

    responses = await asyncio.gather(
        *[client.request_permission(opts, "session-1", t) for t in tools]
    )

    assert len(responses) == 3
    for r in responses:
        assert r.outcome.outcome == "selected"
        assert r.outcome.option_id == "allow-1"


# ---------------------------------------------------------------------------
# test_batch_deny_all_option (option 6 / digit 6)
# ---------------------------------------------------------------------------


async def test_batch_deny_all_option(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selecting option 6 resolves all pending items as reject_once (cancelled)."""
    client = _make_client(monkeypatch)
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
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)  # type: ignore[attr-defined]

    opts = _make_options()
    tools = [_make_tool_call(f"deny_{i}") for i in range(3)]

    responses = await asyncio.gather(
        *[client.request_permission(opts, "session-1", t) for t in tools]
    )

    assert len(responses) == 3
    for r in responses:
        assert r.outcome.outcome == "cancelled"


# ---------------------------------------------------------------------------
# test_batch_does_not_group_sequential_calls
# ---------------------------------------------------------------------------


async def test_batch_does_not_group_sequential_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two calls >debounce apart → two separate panel renders."""
    client = _make_client(monkeypatch)
    # Debounce is 20 ms; we'll sleep 30 ms between calls
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.020)

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

    async def _fake_single_panel(*_a: Any, **_kw: Any) -> tuple[int, str]:
        return (0, "")

    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_single_panel)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)  # type: ignore[attr-defined]

    opts = _make_options()

    # First call — arms debounce, flushes after 20 ms
    r1 = asyncio.create_task(client.request_permission(opts, "s-1", _make_tool_call("seq_1")))
    await asyncio.sleep(0.040)  # wait for first debounce to expire
    assert r1.done(), "first call must have resolved"

    # Second call — new debounce window
    r2 = asyncio.create_task(client.request_permission(opts, "s-1", _make_tool_call("seq_2")))
    await asyncio.sleep(0.040)

    await r1
    await r2

    # N=1 for each → single-approval path; batch modal not called
    # (but single-approval path is used via _flush_single → _run_approval_panel_async)
    assert panel_render_count[0] == 0, "batch panel must not fire for N=1 debounce windows"


# ---------------------------------------------------------------------------
# test_yolo_bypasses_batch
# ---------------------------------------------------------------------------


async def test_yolo_bypasses_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """--yolo flag: auto-approves immediately, no batch queue involved."""
    client = _make_client(monkeypatch, yolo=True)

    batch_enqueue_called: list[bool] = []
    original_enqueue = client._batch_queue.enqueue

    async def _spy_enqueue(*args: Any, **kwargs: Any) -> Any:
        batch_enqueue_called.append(True)
        return await original_enqueue(*args, **kwargs)

    client._batch_queue.enqueue = _spy_enqueue  # type: ignore[method-assign]

    opts = _make_options()
    tool = _make_tool_call("yolo_tool")

    response = await client.request_permission(opts, "session-1", tool)

    assert response.outcome.outcome == "selected"
    assert batch_enqueue_called == [], "batch queue must not be invoked in --yolo mode"


# ---------------------------------------------------------------------------
# test_batch_feedback_option_on_focused_item
# ---------------------------------------------------------------------------


async def test_batch_feedback_option_on_focused_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deny+feedback on item 1 of 3; items 0 and 2 get approved."""
    client = _make_client(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    async def _fake_batch(
        items: Any,
        *,
        _resolve_item: Any,
        _resolve_all: Any,
        _reject_all: Any,
    ) -> None:
        # item 0: approve once (option 0)
        _resolve_item(0, 0, "")
        # item 1: reject+feedback (option 3)
        _resolve_item(1, 3, "use a safer approach")
        # item 2: approve once (option 0)
        _resolve_item(2, 0, "")

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)  # type: ignore[attr-defined]

    opts = _make_options()
    tools = [_make_tool_call(f"fb_tool_{i}") for i in range(3)]

    responses = await asyncio.gather(
        *[client.request_permission(opts, "session-1", t) for t in tools]
    )

    assert len(responses) == 3
    # item 0: allowed
    assert responses[0].outcome.outcome == "selected"
    # item 1: rejected (feedback path returns None → cancelled)
    assert responses[1].outcome.outcome == "cancelled"
    # item 2: allowed
    assert responses[2].outcome.outcome == "selected"


# ---------------------------------------------------------------------------
# test_tab_moves_between_items
# ---------------------------------------------------------------------------


async def test_tab_moves_between_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Tab/Shift-Tab item navigation doesn't break resolution.

    We simulate a user who Tabs to item 1 then approves both items.
    """
    client = _make_client(monkeypatch)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.005)

    # We simulate a user who resolves item 1 first (via Tab) then item 0
    async def _fake_batch(
        items: Any,
        *,
        _resolve_item: Any,
        _resolve_all: Any,
        _reject_all: Any,
    ) -> None:
        # Tab moved focus to item 1 first
        _resolve_item(1, 0, "")  # approve
        _resolve_item(0, 0, "")  # approve

    monkeypatch.setattr(batch_module, "_run_batch_modal_async", _fake_batch)
    monkeypatch.setattr(batch_module, "run_in_terminal", lambda fn: fn() if callable(fn) else None)  # type: ignore[attr-defined]

    opts = _make_options()
    tools = [_make_tool_call("tab_tool_a"), _make_tool_call("tab_tool_b")]

    responses = await asyncio.gather(
        *[client.request_permission(opts, "session-1", t) for t in tools]
    )

    assert len(responses) == 2
    for r in responses:
        assert r.outcome.outcome == "selected"


# ---------------------------------------------------------------------------
# test_sigint_cancels_pending_futures
# ---------------------------------------------------------------------------


async def test_sigint_cancels_pending_futures(monkeypatch: pytest.MonkeyPatch) -> None:
    """cancel_all() resolves all pending Futures as cancelled without hang."""
    client = _make_client(monkeypatch)
    # Set a long debounce so items stay pending when we call cancel_all
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 10.0)

    opts = _make_options()
    # Enqueue items but don't await the futures yet
    fut1 = await client._batch_queue.enqueue(opts, _make_tool_call("sigint_tool_1"))
    fut2 = await client._batch_queue.enqueue(opts, _make_tool_call("sigint_tool_2"))

    assert not fut1.done()
    assert not fut2.done()

    # Simulate SIGINT
    client.cancel_batch_queue()

    assert fut1.done()
    assert fut2.done()
    assert fut1.result().outcome.outcome == "cancelled"
    assert fut2.result().outcome.outcome == "cancelled"
