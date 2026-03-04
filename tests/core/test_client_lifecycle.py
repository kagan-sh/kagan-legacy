"""Feature tests: Client Lifecycle — docs/internal/features/core.md §1.

Behavioral specs using KaganDriver DSL and KaganCore public API.
No private imports (kagan.core._*). No monkeypatching of production code.
Each test is isolated with its own tmp_path and fresh DB.
"""

import asyncio
from pathlib import Path

import pytest

from kagan.core import KaganCore
from tests.helpers.driver import KaganDriver

pytestmark = pytest.mark.core


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(db_path: Path, request: pytest.FixtureRequest) -> KaganCore:
    c = KaganCore(db_path=db_path)
    request.addfinalizer(c.close)
    return c


# ---------------------------------------------------------------------------
# §1.1 — Construct with default db_path (respects KAGAN_DATA_DIR override)
# ---------------------------------------------------------------------------


async def test_default_db_path_uses_kagan_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Client uses KAGAN_DATA_DIR env var to resolve default db_path."""
    monkeypatch.setenv("KAGAN_DATA_DIR", str(tmp_path))
    client = KaganCore()
    assert client is not None
    # DB file is created inside the overridden data dir
    assert (tmp_path / "kagan.db").exists()
    client.close()


# ---------------------------------------------------------------------------
# §1.2 — Construct with custom db_path
# ---------------------------------------------------------------------------


async def test_custom_db_path_creates_db_file(tmp_path: Path) -> None:
    """Client creates the DB file at the specified custom path."""
    db_path = tmp_path / "custom" / "kagan.db"
    client = KaganCore(db_path=db_path)
    assert db_path.exists()
    client.close()


# ---------------------------------------------------------------------------
# §1.3 — Works without an active project
# ---------------------------------------------------------------------------


async def test_client_works_without_active_project(tmp_path: Path) -> None:
    """Client can list and create projects without setting an active project."""
    driver = await KaganDriver.boot(tmp_path)
    try:
        # list_projects works with no active project
        projects = await driver.list_projects()
        assert isinstance(projects, list)

        # create_project works with no active project
        project_id = await driver.create_project("Standalone Project")
        assert project_id is not None

        # project appears in list
        projects = await driver.list_projects()
        assert any(p.id == project_id for p in projects)
    finally:
        await driver.teardown()


# ---------------------------------------------------------------------------
# §1.4 — Async context manager disposes cleanly
# ---------------------------------------------------------------------------


async def test_async_context_manager_disposes_cleanly(tmp_path: Path) -> None:
    """Async context manager calls close() on exit without raising."""
    db_path = tmp_path / "ctx.db"
    async with KaganCore(db_path=db_path) as client:
        # Client is usable inside the context
        project = await client.projects.create("CM Project")
        assert project.id is not None
    # After exit, close was called — no error raised


# ---------------------------------------------------------------------------
# §1.5 — Preflight returns structured pass/warn/fail results
# ---------------------------------------------------------------------------


async def test_preflight_returns_structured_results(tmp_path: Path) -> None:
    """preflight() returns a list of PreflightCheckResult with name, status, message, fix_hint."""
    db_path = tmp_path / "preflight.db"
    client = KaganCore(db_path=db_path)
    try:
        results = await client.preflight()
        assert isinstance(results, list)
        assert len(results) >= 1

        for result in results:
            # Each result has the required fields
            assert hasattr(result, "name")
            assert hasattr(result, "status")
            assert hasattr(result, "message")
            assert hasattr(result, "fix_hint")
            # Status is one of pass/warn/fail
            assert result.status in ("pass", "warn", "fail")

        # git check is always present (git is available in test env)
        git_check = next((r for r in results if r.name == "git"), None)
        assert git_check is not None
        assert git_check.status == "pass"
    finally:
        client.close()


def test_client_constructs_with_db_path(db_path: Path) -> None:
    """Client can be constructed with an explicit db_path."""
    c = KaganCore(db_path=db_path)
    assert c is not None
    c.close()


def test_client_close_is_idempotent(client: KaganCore) -> None:
    """Calling close() twice does not raise."""
    client.close()
    client.close()


def test_client_async_context_manager(db_path: Path) -> None:
    """Client works as async context manager and disposes on exit."""

    async def run():
        async with KaganCore(db_path=db_path) as c:
            assert c is not None

    asyncio.run(run())


def test_client_has_workspace_namespace(client: KaganCore) -> None:
    """client.worktrees is a Worktrees instance."""
    from kagan.core.client import Worktrees

    assert isinstance(client.worktrees, Worktrees)


def test_client_has_review_namespace(client: KaganCore) -> None:
    """client.reviews is a Reviews instance."""
    from kagan.core.client import Reviews

    assert isinstance(client.reviews, Reviews)


def test_reset_wipes_all_data(client: KaganCore) -> None:
    """client.reset() removes all projects and tasks."""

    async def run():
        project = await client.projects.create("WipeMe")
        await client.projects.set_active(project.id)
        await client.tasks.create("Doomed task")
        await client.reset()
        projects = await client.projects.list()
        assert projects == []

    asyncio.run(run())


__all__: list[str] = []
