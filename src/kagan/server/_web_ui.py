"""kagan.server._web_ui — Static file serving for the bundled web UI.

Mounts the bundled React/Vite static build as a Starlette static-files
application with SPA fallback: any non-API, non-file path returns
``index.html`` so client-side routing works correctly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from starlette.responses import FileResponse, HTMLResponse
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.types import Receive, Scope, Send

_WEB_STATIC_DIR: Path = Path(__file__).parent / "_web_static"

_RESERVED_PREFIXES = ("/api/", "/health", "/ws", "/mcp", "/sse")
_HTML_CACHE_HEADERS = {"Cache-Control": "no-cache"}
_MISSING_ASSET_HEADERS = {"Cache-Control": "no-store"}


def web_static_dir() -> Path:
    """Return the path to the bundled web static assets."""
    return _WEB_STATIC_DIR


def has_web_bundle() -> bool:
    """Return ``True`` if a usable web bundle exists."""
    index = _WEB_STATIC_DIR / "index.html"
    return index.is_file()


class _SPAStaticFiles:
    """ASGI app: serve static files, fall back to ``index.html`` for SPA routes."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._static = StaticFiles(directory=str(directory), html=True)
        self._index = directory / "index.html"

    @staticmethod
    def _is_asset_request(path: str) -> bool:
        if path in {"", "/"}:
            return False
        return bool(Path(path).suffix)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # WebSocket or other non-HTTP scopes — reject cleanly.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4004})
            return

        path: str = scope.get("path", "/")
        method = scope.get("method", "GET").upper()

        # Never intercept reserved API/ws paths.
        if any(path.startswith(prefix) for prefix in _RESERVED_PREFIXES):
            from starlette.responses import Response

            response = Response("Not Found", status_code=404)
            await response(scope, receive, send)
            return

        if self._is_asset_request(path):
            from starlette.responses import Response

            try:
                await self._static(scope, receive, send)
            except Exception:
                response = Response("Not Found", status_code=404, headers=_MISSING_ASSET_HEADERS)
                await response(scope, receive, send)
            return

        if method not in {"GET", "HEAD"}:
            from starlette.responses import Response

            response = Response("Not Found", status_code=404)
            await response(scope, receive, send)
            return

        if self._index.is_file():
            response = FileResponse(
                str(self._index), media_type="text/html", headers=_HTML_CACHE_HEADERS
            )
            await response(scope, receive, send)
            return

        response = HTMLResponse("<h1>Web UI not found</h1>", status_code=404)
        await response(scope, receive, send)


def register_web_ui(mcp: FastMCP) -> None:
    """Mount the bundled web UI on the server.

    Appends a catch-all ``Mount`` to the FastMCP custom Starlette routes.
    Must be called **after** all API/ws routes have been registered so
    the SPA fallback is the lowest-priority route.

    No-ops silently when the web bundle directory is missing or empty.
    """
    if not has_web_bundle():
        logger.debug("Web UI bundle not found at {}; skipping mount", _WEB_STATIC_DIR)
        return

    spa = _SPAStaticFiles(directory=_WEB_STATIC_DIR)
    mount = Mount("/", app=spa, name="web-ui")
    routes = cast("list[Any]", mcp._custom_starlette_routes)
    routes.append(mount)
    logger.info("Web UI mounted from {}", _WEB_STATIC_DIR)
