from __future__ import annotations

import os

import pytest

from kagan.cli.main import _sanitize_startup_environment

pytestmark = [pytest.mark.unit]


def test_sanitize_startup_environment_removes_macos_malloc_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("kagan.cli._env.sys.platform", "darwin")
    monkeypatch.setenv("MALLOCSTACKLOGGING", "1")
    monkeypatch.setenv("MALLOCSTACKLOGGINGNOCOMPACT", "1")
    monkeypatch.setenv("MALLOCSTACKLOGGINGDIRECTORY", "/tmp/msl")
    monkeypatch.setenv("__XPC_MALLOCSTACKLOGGING", "1")

    _sanitize_startup_environment()

    assert os.environ.get("MALLOCSTACKLOGGING") is None
    assert os.environ.get("MALLOCSTACKLOGGINGNOCOMPACT") is None
    assert os.environ.get("MALLOCSTACKLOGGINGDIRECTORY") is None
    assert os.environ.get("__XPC_MALLOCSTACKLOGGING") is None
