"""HTTP client for ``/api/e2e/fake-agent/*`` routes.

Mirrors ``packages/web/e2e/helpers.ts:scheduleScenario / clearScenario``
so Python tests that boot ``kagan web --fake-agent`` and TS playwright
tests speak the same wire shape to the director.

The routes are only mounted when the server is started with
``--fake-agent`` (``ApiServerOptions.fake_agent=True``).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

import httpx

from tests.helpers.fake_agent_backend import FakeCue, FakeScript

if TYPE_CHECKING:
    from collections.abc import Iterable


def _serialize_cue(cue: FakeCue) -> dict[str, object]:
    payload = asdict(cue)
    return {k: v for k, v in payload.items() if v is not None or k in ("wait", "done")}


async def schedule_http(base_url: str, target_id: str, cues: Iterable[FakeCue]) -> None:
    """POST a script to the running server's director."""
    body = {"target_id": target_id, "cues": [_serialize_cue(c) for c in cues]}
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        response = await client.post("/api/e2e/fake-agent/schedule", json=body)
        response.raise_for_status()


async def clear_http(base_url: str, target_id: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        response = await client.post("/api/e2e/fake-agent/clear", json={"target_id": target_id})
        response.raise_for_status()


async def director_state_http(base_url: str) -> dict[str, object]:
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        response = await client.get("/api/e2e/fake-agent/director")
        response.raise_for_status()
        return response.json()


__all__ = [
    "FakeCue",
    "FakeScript",
    "clear_http",
    "director_state_http",
    "schedule_http",
]
