"""Update-check hardening (F5).

The startup check runs in a daemon thread and a bounded urllib timeout, so a
blocked network never blocks process exit. These guard the two residual hang
paths the bounded socket timeout and the install timeout close.
"""

import socket
import subprocess

from kagan.cli import _bootstrap


def test_fetch_pypi_version_restores_socket_default_timeout(monkeypatch):
    # F5: the fetch bounds DNS by setting the process socket default for the call,
    # then MUST restore the prior default — otherwise it leaks a global timeout onto
    # every later socket in the process. Captures the in-call value to prove it was
    # actually set, and asserts the prior default is restored afterwards.
    import urllib.request

    socket.setdefaulttimeout(None)
    seen: dict = {}

    def _fake_urlopen(url, timeout=None):
        seen["in_call_default"] = socket.getdefaulttimeout()
        raise OSError("blocked network")  # fail-open path

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    result = _bootstrap._fetch_pypi_version(timeout_seconds=2.0)

    assert result is None  # network error fails open, never raises
    assert seen["in_call_default"] == 2.0  # DNS bounded during the call
    assert socket.getdefaulttimeout() is None  # restored after


def test_install_subprocess_timeout_fails_open(monkeypatch):
    # F5: a wedged installer (uv/pipx/pip) must not hang `kagan update`. A
    # TimeoutExpired is caught and reported, not propagated, so the command returns.
    monkeypatch.setattr(_bootstrap, "_current_version", lambda: "1.0.0")
    monkeypatch.setattr(_bootstrap, "_fetch_pypi_version", lambda timeout_seconds=6.0: "2.0.0")
    monkeypatch.setattr(_bootstrap, "_detect_install_method", lambda: "pip")

    def _hang(*_a, **_k):
        raise subprocess.TimeoutExpired(
            cmd="pip install", timeout=_bootstrap._INSTALL_TIMEOUT_SECONDS
        )

    monkeypatch.setattr(_bootstrap.subprocess, "run", _hang)

    ok, message = _bootstrap.check_and_install_update()

    assert ok is False
    assert "timed out" in message.lower()
