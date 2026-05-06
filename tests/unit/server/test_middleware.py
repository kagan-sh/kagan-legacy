from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from kagan.server._middleware import RateLimitMiddleware, install_security_middleware

pytestmark = [pytest.mark.unit]


async def _board(_request) -> PlainTextResponse:
    return PlainTextResponse("board")


async def _api_example(_request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _client() -> TestClient:
    app = Starlette(
        routes=[
            Route("/board", _board),
            Route("/api/example", _api_example),
        ]
    )
    install_security_middleware(app)
    return TestClient(app)


def test_rate_limiter_skips_non_api_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kagan.server._middleware._RATE_LIMIT_DEFAULT", 2)

    with _client() as client:
        for _ in range(5):
            response = client.get("/board")
            assert response.status_code == 200
            assert response.text == "board"


def test_rate_limiter_applies_to_api_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kagan.server._middleware._RATE_LIMIT_DEFAULT", 2)

    with _client() as client:
        assert client.get("/api/example").status_code == 200
        assert client.get("/api/example").status_code == 200

        response = client.get("/api/example")
        assert response.status_code == 429
        assert response.json()["error"] == "Rate limit exceeded — try again later"


def test_rate_limit_log_key_does_not_leak_token() -> None:
    raw = "token:sk_live_supersecret_AAAAAAAAAAAAAAAA"
    safe = RateLimitMiddleware._safe_log_key(raw)
    assert safe.startswith("token:")
    assert "supersecret" not in safe
    assert "sk_live" not in safe
    assert len(safe) <= len("token:") + 8

    assert RateLimitMiddleware._safe_log_key("192.0.2.1") == "192.0.2.1"
