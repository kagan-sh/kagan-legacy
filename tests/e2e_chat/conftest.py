"""Shared fixtures for ``tests/e2e_chat``.

Two director routings:

- ``mode="inproc"`` — TUI Pilot tests that run ``KaganCore`` in the same
  Python process as the test. Uses
  :mod:`tests.e2e_chat.helpers.director_inproc`.
- ``mode="http"`` — CLI PTY tests and Playwright tests that talk to a
  separate ``kagan web --fake-agent`` subprocess. Uses
  :mod:`tests.e2e_chat.helpers.director_client`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tests.e2e_chat.helpers import director_client, director_inproc
from tests.e2e_chat.helpers.server_runtime import ServerHandle, boot_kagan_web
from tests.helpers.fake_agent_backend import (
    FakeCue,
    ensure_fake_agent_backend_registered,
)

pytestmark = [pytest.mark.e2e_chat]


class ScriptedLLM:
    """Facade with a uniform interface over the in-proc and HTTP director."""

    def __init__(self, *, base_url: str | None) -> None:
        self._base_url = base_url

    async def schedule(self, target_id: str, *cues: FakeCue) -> None:
        if self._base_url:
            await director_client.schedule_http(self._base_url, target_id, cues)
        else:
            await director_inproc.schedule_inproc(target_id, cues)

    async def clear(self, target_id: str) -> None:
        if self._base_url:
            await director_client.clear_http(self._base_url, target_id)
        else:
            await director_inproc.clear_inproc(target_id)


@pytest.fixture
def fake_agent_registered() -> None:
    ensure_fake_agent_backend_registered()


@pytest.fixture
async def kagan_server(tmp_path: Path) -> AsyncIterator[ServerHandle]:
    """Boot ``kagan web --fake-agent`` for HTTP-mode tests."""
    handle = await boot_kagan_web(tmp_path)
    try:
        yield handle
    finally:
        await handle.aclose()


@pytest.fixture
def fake_llm_inproc(fake_agent_registered: None) -> ScriptedLLM:
    return ScriptedLLM(base_url=None)


@pytest.fixture
async def fake_llm_http(kagan_server: ServerHandle) -> ScriptedLLM:
    return ScriptedLLM(base_url=kagan_server.base_url)
