import asyncio
import sys
from typing import Any

import pytest

from kagan.core import install_asyncio_subprocess_exception_filter

pytestmark = [pytest.mark.unit]


class _FakeHandle:
    def __init__(self, callback_qualname: str) -> None:
        self._callback = type("_Cb", (), {"__qualname__": callback_qualname})()


class _FakeLoop:
    def __init__(self) -> None:
        self._handler: Any = None
        self.default_calls: list[dict[str, Any]] = []

    def get_exception_handler(self) -> Any:
        return self._handler

    def set_exception_handler(self, handler: Any) -> None:
        self._handler = handler

    def default_exception_handler(self, context: dict[str, Any]) -> None:
        self.default_calls.append(context)


class _FakeUnraisable:
    def __init__(self, exc_value: BaseException, obj: object) -> None:
        self.exc_type = type(exc_value)
        self.exc_value = exc_value
        self.exc_traceback = None
        self.err_msg = None
        self.object = obj


def _reset_unraisable_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "unraisablehook", sys.__unraisablehook__)
    monkeypatch.delattr(sys, "_kagan_asyncio_unraisable_hook_patched", raising=False)


def _fake_proactor_del() -> None:
    pass


_fake_proactor_del.__module__ = "asyncio.proactor_events"
_fake_proactor_del.__qualname__ = "_ProactorBasePipeTransport.__del__"


def test_asyncio_subprocess_exception_filter_suppresses_known_invalid_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_unraisable_hook(monkeypatch)
    loop = _FakeLoop()
    previous_calls: list[dict[str, Any]] = []

    def previous_handler(_loop: Any, context: dict[str, Any]) -> None:
        previous_calls.append(context)

    loop.set_exception_handler(previous_handler)
    install_asyncio_subprocess_exception_filter(loop=loop)
    handler = loop.get_exception_handler()
    assert handler is not None

    context = {
        "message": "Exception in callback BaseSubprocessTransport._call_connection_lost()",
        "exception": asyncio.InvalidStateError("invalid state"),
        "handle": _FakeHandle("BaseSubprocessTransport._call_connection_lost"),
    }
    handler(loop, context)

    assert previous_calls == []
    assert loop.default_calls == []


def test_asyncio_subprocess_exception_filter_forwards_unrelated_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_unraisable_hook(monkeypatch)
    loop = _FakeLoop()
    previous_calls: list[dict[str, Any]] = []

    def previous_handler(_loop: Any, context: dict[str, Any]) -> None:
        previous_calls.append(context)

    loop.set_exception_handler(previous_handler)
    install_asyncio_subprocess_exception_filter(loop=loop)
    handler = loop.get_exception_handler()
    assert handler is not None

    context = {
        "message": "Exception in callback something_else",
        "exception": asyncio.InvalidStateError("invalid state"),
        "handle": _FakeHandle("Task._wakeup"),
    }
    handler(loop, context)

    assert len(previous_calls) == 1
    assert previous_calls[0] is context


def test_asyncio_subprocess_exception_filter_suppresses_windows_proactor_unraisable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded: list[Any] = []
    monkeypatch.setattr(sys, "unraisablehook", lambda args: forwarded.append(args))
    monkeypatch.delattr(sys, "_kagan_asyncio_unraisable_hook_patched", raising=False)

    install_asyncio_subprocess_exception_filter(loop=_FakeLoop())
    sys.unraisablehook(
        _FakeUnraisable(
            ValueError("I/O operation on closed pipe"),
            _fake_proactor_del,
        )
    )

    assert forwarded == []


def test_asyncio_subprocess_exception_filter_forwards_unrelated_unraisable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded: list[Any] = []
    monkeypatch.setattr(sys, "unraisablehook", lambda args: forwarded.append(args))
    monkeypatch.delattr(sys, "_kagan_asyncio_unraisable_hook_patched", raising=False)
    unraisable = _FakeUnraisable(ValueError("other failure"), _fake_proactor_del)

    install_asyncio_subprocess_exception_filter(loop=_FakeLoop())
    sys.unraisablehook(unraisable)

    assert forwarded == [unraisable]


def test_asyncio_subprocess_exception_filter_installs_without_running_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_unraisable_hook(monkeypatch)

    def raise_no_running_loop() -> asyncio.AbstractEventLoop:
        raise RuntimeError("no running event loop")

    monkeypatch.setattr(asyncio, "get_running_loop", raise_no_running_loop)

    install_asyncio_subprocess_exception_filter()

    assert sys._kagan_asyncio_unraisable_hook_patched is True
