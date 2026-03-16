from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from starlette.requests import Request

import kagan.server._auth as auth_module
from kagan.mcp.server import ServerOptions
from kagan.server._auth import BearerAuthMiddleware
from kagan.server.server import ApiServerOptions, create_api_server

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.fastmcp import FastMCP


def _make_api_server() -> FastMCP:
    return create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))


def _get_endpoint(
    mcp: FastMCP,
    path: str,
) -> Callable[[Request], Awaitable[object]]:
    route = next(route for route in mcp._custom_starlette_routes if route.path == path)
    return route.endpoint


def _make_request(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    payload = json.dumps(body).encode() if body is not None else b""
    raw_headers = []
    if headers is not None:
        raw_headers = [(key.lower().encode(), value.encode()) for key, value in headers.items()]

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "headers": raw_headers,
        "query_string": b"",
        "scheme": "http",
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 12345),
    }

    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(scope, receive)


def test_create_api_server_installs_bearer_auth_middleware() -> None:
    mcp = _make_api_server()

    app = mcp.streamable_http_app()

    assert any(layer.cls is BearerAuthMiddleware for layer in app.user_middleware)


@pytest.mark.asyncio
async def test_pair_with_valid_secret_returns_token() -> None:
    mcp = _make_api_server()
    pair = _get_endpoint(mcp, "/auth/pair")

    request = _make_request(
        method="POST",
        path="/auth/pair",
        body={"secret": auth_module._pairing_secret, "device_id": "device-1"},
    )
    response = await pair(request)
    data = json.loads(response.body)

    assert response.status_code == 200
    assert data["ok"] is True
    assert len(data["data"]["token"]) == 64


@pytest.mark.asyncio
async def test_verify_without_authorization_header_returns_401() -> None:
    mcp = _make_api_server()
    verify = _get_endpoint(mcp, "/auth/verify")

    request = _make_request(method="GET", path="/auth/verify")
    response = await verify(request)

    assert response.status_code == 401
    assert json.loads(response.body) == {"ok": False, "error": "Missing token"}


@pytest.mark.asyncio
async def test_verify_with_invalid_token_returns_401() -> None:
    mcp = _make_api_server()
    verify = _get_endpoint(mcp, "/auth/verify")

    request = _make_request(
        method="GET",
        path="/auth/verify",
        headers={"Authorization": "Bearer invalid-token"},
    )
    response = await verify(request)

    assert response.status_code == 401
    assert json.loads(response.body) == {"ok": False, "error": "Invalid token"}


@pytest.mark.asyncio
async def test_verify_with_valid_token_returns_ok() -> None:
    mcp = _make_api_server()
    pair = _get_endpoint(mcp, "/auth/pair")
    verify = _get_endpoint(mcp, "/auth/verify")

    pair_request = _make_request(
        method="POST",
        path="/auth/pair",
        body={"secret": auth_module._pairing_secret, "device_id": "device-2"},
    )
    pair_response = await pair(pair_request)
    token = json.loads(pair_response.body)["data"]["token"]

    verify_request = _make_request(
        method="GET",
        path="/auth/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    verify_response = await verify(verify_request)

    assert verify_response.status_code == 200
    assert json.loads(verify_response.body) == {"ok": True}
