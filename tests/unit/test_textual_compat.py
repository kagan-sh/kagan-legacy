import asyncio
from typing import Any

import pytest

from kagan.tui.textual_compat import install_asyncio_subprocess_exception_filter

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


def test_asyncio_subprocess_exception_filter_suppresses_known_invalid_state() -> None:
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


def test_asyncio_subprocess_exception_filter_forwards_unrelated_errors() -> None:
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
