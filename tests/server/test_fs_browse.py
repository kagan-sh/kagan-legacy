"""Tests for GET /api/fs/browse — Windows-safe filesystem browser endpoint."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

if TYPE_CHECKING:
    from starlette.responses import JSONResponse

import kagan.server._helpers as server_helpers
from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint, json_body
from tests.helpers.server_ws import make_api_server

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ctx() -> SimpleNamespace:
    async def _get_settings() -> dict[str, str]:
        return {}

    async def _no_repo_path(**_kwargs: Any) -> None:
        return None

    return SimpleNamespace(
        client=SimpleNamespace(
            settings=SimpleNamespace(get=_get_settings),
            projects=SimpleNamespace(resolve_repo_path=_no_repo_path),
        ),
        opts=ServerOptions(),
    )


def _make_browse_request(path: str | None = None) -> Request:
    """Build a Starlette Request for the browse endpoint with an optional path param."""
    qs = urlencode({"path": path}).encode() if path is not None else b""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/fs/browse",
        "raw_path": b"/api/fs/browse",
        "headers": [],
        "query_string": qs,
        "scheme": "http",
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 12345),
        "path_params": {},
    }
    return Request(scope)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def browse_endpoint(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return the browse endpoint with a real ctx stub."""
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: _make_ctx())
    return get_http_endpoint(mcp, "/api/fs/browse", "GET")


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_browse_home_returns_entries(browse_endpoint: Any) -> None:
    response = await browse_endpoint(_make_browse_request("~"))
    body = json_body(response)

    assert body["ok"] is True
    data = body["data"]
    assert data["path"] == str(Path.home())
    assert isinstance(data["entries"], list)
    assert isinstance(data["separator"], str)
    assert len(data["separator"]) == 1
    assert isinstance(data["roots"], list)
    assert len(data["roots"]) >= 1


async def test_browse_default_path_is_home(browse_endpoint: Any) -> None:
    """Omitting path param should default to '~'."""
    response = await browse_endpoint(_make_browse_request())
    body = json_body(response)

    assert body["ok"] is True
    assert body["data"]["path"] == str(Path.home())


async def test_browse_separator_matches_os_sep(browse_endpoint: Any) -> None:
    response = await browse_endpoint(_make_browse_request("~"))
    body = json_body(response)

    assert body["data"]["separator"] == os.sep


async def test_browse_roots_contains_posix_root_on_posix(browse_endpoint: Any) -> None:
    if os.name == "nt":
        pytest.skip("POSIX-only test")
    response = await browse_endpoint(_make_browse_request("~"))
    body = json_body(response)

    assert "/" in body["data"]["roots"]


async def test_browse_parent_correct_for_nested_dir(browse_endpoint: Any, tmp_path: Path) -> None:
    child = tmp_path / "subdir"
    child.mkdir()

    response = await browse_endpoint(_make_browse_request(str(child)))
    body = json_body(response)

    assert body["ok"] is True
    assert body["data"]["parent"] == str(tmp_path)


async def test_browse_parent_is_null_at_root(browse_endpoint: Any) -> None:
    if os.name == "nt":
        pytest.skip("POSIX-only root null test")
    response = await browse_endpoint(_make_browse_request("/"))
    body = json_body(response)

    assert body["ok"] is True
    assert body["data"]["parent"] is None


async def test_browse_nonexistent_path_returns_400(browse_endpoint: Any) -> None:
    response = await browse_endpoint(_make_browse_request("/definitely/does/not/exist/xyz123"))
    assert cast("JSONResponse", response).status_code == 400
    body = json_body(response)
    assert body["ok"] is False


async def test_browse_file_path_returns_400(browse_endpoint: Any, tmp_path: Path) -> None:
    file_path = tmp_path / "afile.txt"
    file_path.write_text("hello")

    response = await browse_endpoint(_make_browse_request(str(file_path)))
    assert cast("JSONResponse", response).status_code == 400
    body = json_body(response)
    assert body["ok"] is False


async def test_browse_git_repo_dir_is_flagged(browse_endpoint: Any, tmp_path: Path) -> None:
    git_dir = tmp_path / "myrepo"
    git_dir.mkdir()
    (git_dir / ".git").mkdir()

    response = await browse_endpoint(_make_browse_request(str(tmp_path)))
    body = json_body(response)

    assert body["ok"] is True
    entries = {e["name"]: e for e in body["data"]["entries"]}
    assert "myrepo" in entries
    assert entries["myrepo"]["is_git_repo"] is True


async def test_browse_dot_prefixed_entries_filtered(browse_endpoint: Any, tmp_path: Path) -> None:
    (tmp_path / ".hidden_dir").mkdir()
    (tmp_path / "visible_dir").mkdir()

    response = await browse_endpoint(_make_browse_request(str(tmp_path)))
    body = json_body(response)

    assert body["ok"] is True
    names = [e["name"] for e in body["data"]["entries"]]
    assert ".hidden_dir" not in names
    assert "visible_dir" in names


async def test_browse_symlink_to_dir_included_and_flagged(
    browse_endpoint: Any, tmp_path: Path
) -> None:
    if sys.platform == "win32":
        pytest.skip("Symlink creation requires elevated privileges on Windows")

    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(real_dir)

    response = await browse_endpoint(_make_browse_request(str(tmp_path)))
    body = json_body(response)

    assert body["ok"] is True
    entries = {e["name"]: e for e in body["data"]["entries"]}
    assert "linked" in entries, f"symlink not in entries; got: {list(entries)}"
    assert entries["linked"]["is_link"] is True
    assert entries["linked"]["is_dir"] is True


async def test_browse_entry_shape_has_required_fields(browse_endpoint: Any, tmp_path: Path) -> None:
    (tmp_path / "a_dir").mkdir()
    response = await browse_endpoint(_make_browse_request(str(tmp_path)))
    body = json_body(response)

    entry = next(e for e in body["data"]["entries"] if e["name"] == "a_dir")
    for field in ("name", "path", "is_dir", "is_git_repo", "is_link"):
        assert field in entry, f"missing field {field!r}"


# ── Windows-specific tests ─────────────────────────────────────────────────────

_WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")


@pytest.mark.windows_ci
@_WINDOWS_ONLY
async def test_windows_roots_include_c_drive(browse_endpoint: Any) -> None:
    response = await browse_endpoint(_make_browse_request("~"))
    body = json_body(response)

    roots = body["data"]["roots"]
    # The test runner's drive (usually C:\) must be in the list.
    cwd_drive = Path.cwd().drive + "\\"
    assert cwd_drive in roots, f"Expected {cwd_drive!r} in roots; got {roots}"


@pytest.mark.windows_ci
@_WINDOWS_ONLY
async def test_windows_parent_of_users_is_drive(browse_endpoint: Any) -> None:
    users = Path("C:\\Users")
    if not users.exists():
        pytest.skip("C:\\Users does not exist on this runner")

    response = await browse_endpoint(_make_browse_request(str(users)))
    body = json_body(response)

    assert body["ok"] is True
    assert body["data"]["parent"] == "C:\\"


@pytest.mark.windows_ci
@_WINDOWS_ONLY
async def test_windows_parent_of_c_root_is_null(browse_endpoint: Any) -> None:
    c_root = Path("C:\\")
    if not c_root.exists():
        pytest.skip("C:\\ does not exist on this runner")

    response = await browse_endpoint(_make_browse_request(str(c_root)))
    body = json_body(response)

    assert body["ok"] is True
    assert body["data"]["parent"] is None
