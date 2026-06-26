import sys
from unittest.mock import AsyncMock

import pytest

from kagan.core.models import Task
from kagan.core.notifications import NotificationEvent, Notifier


@pytest.mark.asyncio
async def test_notify_rings_bell_and_os(monkeypatch):
    # TUI-NOTIFY-01: an attention event rings the bell and fires the OS toast.
    bell = []
    monkeypatch.setattr(sys.stderr, "write", bell.append)
    notifier = Notifier()
    monkeypatch.setattr(notifier, "_os_notify", AsyncMock())

    await notifier.notify(NotificationEvent.NEEDS_YOU, Task(id="t-1", title="x"))
    assert "\a" in bell
    notifier._os_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_bell_silenced_when_flag_off(monkeypatch):
    # TUI-NOTIFY-01: the bell is gated by the config flag, off means silent.
    bell = []
    monkeypatch.setattr(sys.stderr, "write", bell.append)
    notifier = Notifier(bell=False)
    monkeypatch.setattr(notifier, "_os_notify", AsyncMock())

    await notifier.notify(NotificationEvent.REVIEW, Task(id="t-1", title="x"))
    assert "\a" not in bell


@pytest.mark.asyncio
async def test_webhook_posts_event(monkeypatch):
    # TUI-NOTIFY-03: an optional webhook posts the canonical event token.
    posted = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *, json, timeout):
            posted.append((url, json))

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: FakeClient())
    notifier = Notifier(webhook_url="http://example.com/hook")
    monkeypatch.setattr(notifier, "_os_notify", AsyncMock())
    monkeypatch.setattr(sys.stderr, "write", lambda _: None)

    await notifier.notify(NotificationEvent.DRIFT, Task(id="t-1", title="x"))
    assert posted[0][0] == "http://example.com/hook"
    assert posted[0][1]["event"] == "drift"


@pytest.mark.asyncio
async def test_os_notify_noop_when_binary_missing(monkeypatch):
    # P12: a missing toast binary must no-op, never raise, never block the gate.
    monkeypatch.setattr("shutil.which", lambda _: None)
    notifier = Notifier()
    monkeypatch.setattr(sys.stderr, "write", lambda _: None)
    await notifier.notify(NotificationEvent.FINISHED, Task(id="t-1", title="x"))
