"""Tests for project api adapter functions (formerly CQRS handlers)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from kagan.core.adapters.db.schema import Project
from kagan.core.commands.plugins import tui_api_call
from kagan.core.commands.projects import (
    add_repo as handle_project_add_repo,
)
from kagan.core.commands.projects import (
    find_project_by_repo_path as handle_project_find_by_repo_path,
)


def _ctx(**services: object) -> Any:
    ctx = SimpleNamespace(**services)
    project_service = services.get("project_service")
    get_repo_details = getattr(project_service, "get_project_repo_details", None)
    if get_repo_details is None:

        async def _empty_repo_details(_project_id: str) -> list[dict[str, object]]:
            return []

        get_repo_details = _empty_repo_details
    ctx.api = SimpleNamespace(get_project_repo_details=get_repo_details)
    return ctx


async def test_project_add_repo_returns_repo_id() -> None:
    class _ProjectService:
        async def add_repo_to_project(
            self,
            project_id: str,
            repo_path: str,
            is_primary: bool = False,
        ) -> str:
            assert project_id == "P1"
            assert repo_path == "/tmp/repo"
            assert is_primary is True
            return "R1"

    f = _ctx(project_service=_ProjectService())
    result = await handle_project_add_repo(
        f,
        {"project_id": "P1", "repo_path": "/tmp/repo", "is_primary": True},
    )

    assert result["success"] is True
    assert result["repo_id"] == "R1"


async def test_project_repo_details_returns_count() -> None:
    class _ProjectService:
        async def get_project_repo_details(self, project_id: str) -> list[dict[str, object]]:
            assert project_id == "P1"
            return [
                {"id": "R1", "path": "/tmp/r1"},
                {"id": "R2", "path": "/tmp/r2"},
            ]

    f = _ctx(project_service=_ProjectService())
    result = await tui_api_call(
        f,
        {"method": "get_project_repo_details", "kwargs": {"project_id": "P1"}},
    )

    assert result["success"] is True
    assert result["value"]["count"] == 2
    assert len(result["value"]["repos"]) == 2


async def test_project_find_by_repo_path_handles_missing() -> None:
    class _ProjectService:
        async def find_project_by_repo_path(self, repo_path: str) -> Project | None:
            assert repo_path == "/tmp/missing"
            return None

    f = _ctx(project_service=_ProjectService())
    result = await handle_project_find_by_repo_path(f, {"repo_path": "/tmp/missing"})

    assert result == {"found": False, "project": None}


async def test_project_find_by_repo_path_returns_project() -> None:
    class _ProjectService:
        async def find_project_by_repo_path(self, repo_path: str) -> Project | None:
            assert repo_path == "/tmp/repo"
            return Project(name="Demo", description="desc")

    f = _ctx(project_service=_ProjectService())
    result = await handle_project_find_by_repo_path(f, {"repo_path": "/tmp/repo"})

    assert result["found"] is True
    assert result["project"]["name"] == "Demo"
