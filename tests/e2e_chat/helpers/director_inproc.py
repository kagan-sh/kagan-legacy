"""In-process FakeAgentDirector facade.

Used by TUI Pilot tests and any other in-process consumer that drives
``KaganCore`` directly. The web Playwright surface uses
:mod:`tests.e2e_chat.helpers.director_client` instead because the server
runs in a separate process and only the HTTP path is shared.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.helpers.fake_agent_backend import (
    FakeCue,
    FakeScript,
    director,
    register_fake_backend,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


async def schedule_inproc(target_id: str, cues: Iterable[FakeCue]) -> None:
    """Register ``cues`` for ``target_id`` (task or session id)."""
    await director.schedule(target_id, FakeScript(cues=list(cues)))


async def clear_inproc(target_id: str) -> None:
    await director.clear(target_id)


__all__ = [
    "FakeCue",
    "FakeScript",
    "clear_inproc",
    "director",
    "register_fake_backend",
    "schedule_inproc",
]
