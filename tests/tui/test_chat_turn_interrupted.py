"""Tests for CHAT_TURN_TERMINATED / turn-interrupted behaviour in the TUI.

Coverage:
- ChatPanel.add_system_message shows "⚡ Turn interrupted" in rendered messages.
- watch_chat_session exits immediately when http_client is None.
- watch_chat_session delivers a Textual notification on a takeover event.
- watch_chat_session ignores non-takeover CHAT_TURN_TERMINATED events.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import pytest

pytestmark = [pytest.mark.tui, pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSSELine:
    """Simulates a single SSE data line yielded by response.aiter_lines()."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._line = f"data: {json.dumps(payload)}"

    def __str__(self) -> str:
        return self._line


class _FakeResponse:
    """Minimal fake of an httpx streaming response."""

    def __init__(self, lines: list[str], *, status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeHTTPClient:
    """Minimal fake of an httpx.AsyncClient with streaming support."""

    def __init__(self, lines: list[str], *, status_code: int = 200) -> None:
        self._lines = lines
        self._status_code = status_code

    @asynccontextmanager
    async def stream(self, method: str, url: str):
        yield _FakeResponse(self._lines, status_code=self._status_code)


# ---------------------------------------------------------------------------
# Task A: "⚡ Turn interrupted" system message
# ---------------------------------------------------------------------------


async def test_add_system_message_turn_interrupted_appears_in_rendered() -> None:
    """ChatPanel.add_system_message stores the message in state, visible via export."""
    from textual.app import App, ComposeResult

    from kagan.tui.widgets.chat import ChatPanel

    class _TestApp(App[None]):
        def compose(self) -> ComposeResult:
            yield ChatPanel(classes="chat-overlay")

    app = _TestApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)
        panel.add_system_message("⚡ Turn interrupted")
        await pilot.pause()

        rendered = panel.export_rendered_messages()
        assert any("Turn interrupted" in line for line in rendered), (
            f"Expected 'Turn interrupted' in rendered messages, got: {rendered}"
        )


async def test_interrupted_turn_message_visible_in_mounted_panel(
    tmp_path,
) -> None:
    """When a turn is interrupted the system message is added and survives session render."""
    from textual.app import App, ComposeResult

    from kagan.tui.widgets.chat import ChatPanel

    class _TestApp(App[None]):
        def compose(self) -> ComposeResult:
            panel = ChatPanel(classes="chat-overlay")
            panel.set_class(True, "visible")
            yield panel

    app = _TestApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)
        panel.add_system_message("⚡ Turn interrupted")
        await pilot.pause()

        rendered = panel.export_rendered_messages()
        assert any("Turn interrupted" in line for line in rendered), (
            f"Expected 'Turn interrupted' in rendered messages after mount, got: {rendered}"
        )


# ---------------------------------------------------------------------------
# Task B: watch_chat_session
# ---------------------------------------------------------------------------


async def test_watch_chat_session_exits_when_no_http_client() -> None:
    """watch_chat_session must return immediately when http_client is None."""
    from textual.app import App, ComposeResult

    from kagan.tui.screens._chat_runner import watch_chat_session
    from kagan.tui.widgets.chat import ChatPanel

    class _TestApp(App[None]):
        def compose(self) -> ComposeResult:
            yield ChatPanel(classes="chat-overlay")

    app = _TestApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)

        # Must complete synchronously (no retry loop entered).
        await asyncio.wait_for(
            watch_chat_session(
                session_id="test-session-123",
                panel=panel,
                http_client=None,
            ),
            timeout=1.0,
        )


async def test_watch_chat_session_exits_on_404() -> None:
    """watch_chat_session exits cleanly when the server returns 404 (endpoint not available)."""
    from textual.app import App, ComposeResult

    from kagan.tui.screens._chat_runner import watch_chat_session
    from kagan.tui.widgets.chat import ChatPanel

    class _TestApp(App[None]):
        def compose(self) -> ComposeResult:
            yield ChatPanel(classes="chat-overlay")

    app = _TestApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)

        fake_client = _FakeHTTPClient([], status_code=404)
        await asyncio.wait_for(
            watch_chat_session(
                session_id="test-session-404",
                panel=panel,
                http_client=fake_client,  # type: ignore[arg-type]
            ),
            timeout=1.0,
        )


async def test_watch_chat_session_notifies_on_takeover() -> None:
    """watch_chat_session calls app.notify on CHAT_TURN_TERMINATED with reason=takeover."""
    from textual.app import App, ComposeResult

    from kagan.tui.screens._chat_runner import watch_chat_session
    from kagan.tui.widgets.chat import ChatPanel

    class _TestApp(App[None]):
        def __init__(self) -> None:
            super().__init__()
            self.notifications: list[str] = []

        def compose(self) -> ComposeResult:
            yield ChatPanel(classes="chat-overlay")

        def notify(self, message: str, *, severity: str = "information", **kwargs: Any) -> None:  # type: ignore[override]
            self.notifications.append(message)

    takeover_event = json.dumps({"t": "CHAT_TURN_TERMINATED", "reason": "takeover"})
    sse_lines = [f"data: {takeover_event}"]
    fake_client = _FakeHTTPClient(sse_lines, status_code=200)

    app = _TestApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)

        # The watch task will consume the single event then retry after delay.
        # Cancel it after a short wait so we don't block on the retry sleep.
        task = asyncio.create_task(
            watch_chat_session(
                session_id="test-session-takeover",
                panel=panel,
                http_client=fake_client,  # type: ignore[arg-type]
            )
        )
        # Give the coroutine time to process the SSE line.
        await pilot.pause()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert any(
            "taken over" in msg.lower() or "interrupted" in msg.lower() for msg in app.notifications
        ), f"Expected takeover notification, got: {app.notifications}"


async def test_watch_chat_session_ignores_non_takeover_termination() -> None:
    """watch_chat_session must NOT notify for CHAT_TURN_TERMINATED with reason != takeover."""
    from textual.app import App, ComposeResult

    from kagan.tui.screens._chat_runner import watch_chat_session
    from kagan.tui.widgets.chat import ChatPanel

    class _TestApp(App[None]):
        def __init__(self) -> None:
            super().__init__()
            self.notifications: list[str] = []

        def compose(self) -> ComposeResult:
            yield ChatPanel(classes="chat-overlay")

        def notify(self, message: str, *, severity: str = "information", **kwargs: Any) -> None:  # type: ignore[override]
            self.notifications.append(message)

    # reason is "user_interrupt" not "takeover"
    event_line = json.dumps({"t": "CHAT_TURN_TERMINATED", "reason": "user_interrupt"})
    sse_lines = [f"data: {event_line}"]
    fake_client = _FakeHTTPClient(sse_lines, status_code=200)

    app = _TestApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)

        task = asyncio.create_task(
            watch_chat_session(
                session_id="test-session-non-takeover",
                panel=panel,
                http_client=fake_client,  # type: ignore[arg-type]
            )
        )
        await pilot.pause()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert not app.notifications, (
            f"Expected no notifications for non-takeover event, got: {app.notifications}"
        )
