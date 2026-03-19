from __future__ import annotations

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from kagan.server._web_ui import _SPAStaticFiles


def _client(tmp_path) -> TestClient:
    (tmp_path / "index.html").write_text("<html><body>kagan</body></html>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    app = Starlette(routes=[Mount("/", app=_SPAStaticFiles(tmp_path))])
    return TestClient(app)


def test_missing_asset_returns_404_instead_of_spa_fallback(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/assets/missing.js")

    assert response.status_code == 404
    assert response.text == "Not Found"
    assert response.headers["cache-control"] == "no-store"
    assert not response.headers.get("content-type", "").startswith("text/html")


def test_route_path_serves_index_with_no_cache_header(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/board")

    assert response.status_code == 200
    assert response.text == "<html><body>kagan</body></html>"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith("text/html")


def test_non_get_route_like_request_does_not_receive_spa_fallback(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/board")

    assert response.status_code == 404
    assert response.text == "Not Found"
