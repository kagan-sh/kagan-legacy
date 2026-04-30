from __future__ import annotations

import signal

import uvicorn

from kagan.server.server import _KaganUvicornServer


async def _empty_app(scope, receive, send) -> None:
    return None


def test_uvicorn_signal_capture_does_not_replay_sigint(monkeypatch) -> None:
    installed: dict[signal.Signals, object] = {}
    replayed: list[signal.Signals] = []

    def fake_signal(sig, handler):
        previous = installed.get(sig, signal.SIG_DFL)
        installed[sig] = handler
        return previous

    monkeypatch.setattr(signal, "signal", fake_signal)
    monkeypatch.setattr(signal, "raise_signal", lambda sig: replayed.append(sig))

    server = _KaganUvicornServer(uvicorn.Config(_empty_app))

    with server.capture_signals():
        server.handle_exit(signal.SIGINT, None)

    assert server.should_exit is True
    assert replayed == []


def test_second_shutdown_signal_requests_force_exit(monkeypatch) -> None:
    installed: dict[signal.Signals, object] = {}

    def fake_signal(sig, handler):
        previous = installed.get(sig, signal.SIG_DFL)
        installed[sig] = handler
        return previous

    monkeypatch.setattr(signal, "signal", fake_signal)

    server = _KaganUvicornServer(uvicorn.Config(_empty_app))

    with server.capture_signals():
        server.handle_exit(signal.SIGINT, None)
        server.handle_exit(signal.SIGINT, None)

    assert server.should_exit is True
    assert server.force_exit is True
