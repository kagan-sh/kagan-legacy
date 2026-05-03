"""Unit tests for the CLI streaming + permission seam.

Phase 5c retargets these tests at :class:`CLIRenderer` (ChatEvent dispatch)
and :class:`PermissionUI` (engine-driven decision dispatch). The legacy
ACP-response shape lives in ``_CaptureACPClient`` and is covered by
``tests/core/unit/test_long_lived_acp_factory.py``.
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

import kagan.cli.chat._chat_acp as chat_acp_module
from kagan.cli.chat._permission_ui import PermissionUI
from kagan.cli.chat._renderer import CLIRenderer
from kagan.core.chat.events import (
    AssistantChunk,
    PermissionRequest,
    ToolCallStart,
)

pytestmark = [pytest.mark.unit]


class _FakeConsoleFile:
    def __init__(self) -> None:
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1


class _FakeConsole:
    """Minimal stand-in used by the permission-flow tests."""

    def __init__(self) -> None:
        self.file = _FakeConsoleFile()
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def print(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _real_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None, width=80)
    return console, buf


class _FakeEngine:
    """Records ``resolve_permission`` calls so tests can assert on them."""

    def __init__(self) -> None:
        self.resolve_calls: list[tuple[str, str, str, str | None]] = []

    async def resolve_permission(
        self,
        session_id: str,
        future_id: str,
        *,
        outcome: str,
        feedback: str | None = None,
    ) -> None:
        self.resolve_calls.append((session_id, future_id, outcome, feedback))


def _options(*kinds: str) -> list[dict[str, Any]]:
    return [
        {"kind": kind, "name": kind.replace("_", " ").title(), "option_id": f"{kind}-1"}
        for kind in kinds
    ]


def _request(future_id: str, title: str, kinds: tuple[str, ...]) -> PermissionRequest:
    return PermissionRequest(
        future_id=future_id,
        tool_call={"title": title, "tool_call_id": f"tc-{title}"},
        options=_options(*kinds),
    )


# ---------------------------------------------------------------------------
# CLIRenderer streaming tests
# ---------------------------------------------------------------------------


def test_streamed_chunks_are_collected_and_returned_by_finish_turn() -> None:
    console, _ = _real_console()
    renderer = CLIRenderer(console)
    renderer.start_turn()

    renderer.on_assistant_chunk("a")
    renderer.on_assistant_chunk("b")
    renderer.on_assistant_chunk("c")

    response = renderer.finish_turn()
    assert response == "abc"


def test_markdown_region_renders_reply_to_console_at_finish_turn() -> None:
    console, buf = _real_console()
    renderer = CLIRenderer(console)
    renderer.start_turn()

    renderer.on_assistant_chunk("| col |\n| --- |\n| val |\n")
    renderer.finish_turn()

    output = buf.getvalue()
    assert "━" in output or "─" in output
    assert "val" in output


def test_markdown_region_finalizes_before_tool_call_start() -> None:
    console, buf = _real_console()
    renderer = CLIRenderer(console)
    renderer.start_turn()

    renderer.on_assistant_chunk("Looking up files.")
    renderer.on_tool_call_start(
        ToolCallStart(tool_id="tool-1", title="Read file", kind_hint=None, args=None)
    )
    renderer.finish_turn()

    output = buf.getvalue()
    text_pos = output.find("Looking up files")
    tool_pos = output.find("Read file")
    assert text_pos != -1
    assert tool_pos != -1
    assert text_pos < tool_pos


def test_start_turn_discards_in_flight_markdown_region() -> None:
    console, _ = _real_console()
    renderer = CLIRenderer(console)
    renderer.start_turn()
    renderer.on_assistant_chunk("partial")

    assert renderer._md_region.is_active

    renderer.start_turn()
    assert not renderer._md_region.is_active
    assert renderer._response_chunks.is_empty


# ---------------------------------------------------------------------------
# PermissionUI engine-driven dispatch
# ---------------------------------------------------------------------------


async def test_permission_request_routes_deny_in_noninteractive_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: False)

    engine = _FakeEngine()
    ui = PermissionUI(engine=engine, renderer=None)

    await ui.handle_request(
        _request("fid-1", "Edit file", ("allow_once", "allow_always")), session_id="s-1"
    )

    assert engine.resolve_calls == [("s-1", "fid-1", "deny", None)]


async def test_permission_request_routes_allow_always_in_interactive_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kagan.cli.chat._approval_batch as batch_module

    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: True)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.0)

    async def _fake_panel(*_a: Any, **_kw: Any) -> tuple[int, str]:
        return (1, "")

    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_panel)
    chat_acp_module._session_approvals.revoke("run command")

    engine = _FakeEngine()
    ui = PermissionUI(engine=engine, renderer=None)

    await ui.handle_request(
        _request("fid-2", "Run command", ("allow_once", "allow_always", "reject_once")),
        session_id="s-2",
    )

    assert engine.resolve_calls == [("s-2", "fid-2", "allow_always", None)]
    chat_acp_module._session_approvals.revoke("run command")


async def test_permission_request_routes_deny_when_user_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kagan.cli.chat._approval_batch as batch_module

    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: True)
    monkeypatch.setattr(batch_module, "_debounce_seconds", lambda: 0.0)

    async def _fake_panel(*_a: Any, **_kw: Any) -> tuple[int, str]:
        return (2, "")

    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_panel)
    chat_acp_module._session_approvals.revoke("run command")

    engine = _FakeEngine()
    ui = PermissionUI(engine=engine, renderer=None)

    await ui.handle_request(
        _request("fid-3", "Run command", ("allow_once", "reject_once")),
        session_id="s-3",
    )

    assert engine.resolve_calls == [("s-3", "fid-3", "deny", None)]


async def test_permission_request_with_no_valid_options_routes_deny() -> None:
    engine = _FakeEngine()
    ui = PermissionUI(engine=engine, renderer=None)

    # The engine emits PermissionRequest with options dicts; if none of the
    # options match the four allowed kinds, the UI should immediately deny.
    event = PermissionRequest(
        future_id="fid-4",
        tool_call={"title": "Mystery"},
        options=[{"kind": "weird", "name": "Strange"}],
    )
    await ui.handle_request(event, session_id="s-4")

    assert engine.resolve_calls == [("s-4", "fid-4", "deny", None)]


async def test_permission_request_yolo_short_circuits_to_allow_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)

    engine = _FakeEngine()
    ui = PermissionUI(engine=engine, renderer=None, yolo=True)

    await ui.handle_request(
        _request("fid-5", "yolo_tool", ("allow_once", "allow_always")),
        session_id="s-5",
    )

    assert engine.resolve_calls == [("s-5", "fid-5", "allow_once", None)]


async def test_permission_request_raises_when_engine_unbound() -> None:
    ui = PermissionUI(engine=None, renderer=None)
    event = _request("fid-x", "tool", ("allow_once",))
    with pytest.raises(RuntimeError, match="bind_engine"):
        await ui.handle_request(event, session_id="s")


def test_permission_ui_bind_engine_swaps_queue() -> None:
    ui = PermissionUI(engine=SimpleNamespace(), renderer=None)
    first_queue = ui._batch_queue
    new_engine = _FakeEngine()
    ui.bind_engine(new_engine)
    assert ui._batch_queue is not first_queue
    assert ui._batch_queue._engine is new_engine
