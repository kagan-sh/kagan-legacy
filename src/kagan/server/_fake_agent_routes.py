"""Internal fake-agent control routes.

Mounted only when the server is started with ``--fake-agent`` / ``KAGAN_FAKE_AGENT=1``.
These endpoints let E2E tests declaratively schedule agent behaviour so that
Playwright specs can exercise full user journeys without mocking HTTP clients
or the database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse

from kagan.core._fake_agent import FakeCue, FakeScript, director

if TYPE_CHECKING:
    from starlette.requests import Request


def _decode_script(body: dict[str, Any]) -> FakeScript:
    cues: list[FakeCue] = []
    for row in body.get("cues", []):
        cues.append(
            FakeCue(
                wait=float(row.get("wait", 0.0)),
                emit=row.get("emit"),
                workspace=row.get("workspace"),
                done=bool(row.get("done", False)),
                error=row.get("error"),
            )
        )
    return FakeScript(cues=cues)


def register_fake_agent_routes(mcp: Any) -> None:
    """Mount ``/api/e2e/fake-agent/*`` endpoints on the FastMCP server."""

    @mcp.custom_route("/api/e2e/fake-agent/schedule", methods=["POST"])
    async def schedule(request: Request) -> JSONResponse:
        body = await request.json()
        target_id = str(body.get("target_id", ""))
        if not target_id:
            return JSONResponse({"error": "target_id required"}, status_code=400)

        script = _decode_script(body)
        await director.schedule(target_id, script)
        return JSONResponse({"scheduled": target_id, "cues": len(script.cues)})

    @mcp.custom_route("/api/e2e/fake-agent/clear", methods=["POST"])
    async def clear(request: Request) -> JSONResponse:
        body = await request.json()
        target_id = str(body.get("target_id", ""))
        if not target_id:
            return JSONResponse({"error": "target_id required"}, status_code=400)

        await director.clear(target_id)
        return JSONResponse({"cleared": target_id})

    @mcp.custom_route("/api/e2e/fake-agent/director", methods=["GET"])
    async def director_state(_request: Request) -> JSONResponse:
        """Debug peek — lists scheduled target IDs only (no cue payloads)."""
        return JSONResponse({"targets": list(director._scripts.keys())})
