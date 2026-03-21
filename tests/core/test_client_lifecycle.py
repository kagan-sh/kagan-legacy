"""Feature tests: Client Lifecycle — docs/internal/features/core.md §1."""

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


async def test_default_db_path_uses_kagan_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Client uses KAGAN_DATA_DIR env var to resolve default db_path."""
    monkeypatch.setenv("KAGAN_DATA_DIR", str(tmp_path))
    client = KaganCore()
    assert client is not None
    assert (tmp_path / "kagan.db").exists()
    client.close()


async def test_custom_db_path_creates_db_file(tmp_path: Path) -> None:
    """Client creates the DB file at the specified custom path."""
    db_path = tmp_path / "custom" / "kagan.db"
    client = KaganCore(db_path=db_path)
    assert db_path.exists()
    client.close()


async def test_client_works_without_active_project(tmp_path: Path) -> None:
    """Client can list and create projects without setting an active project."""
    driver = await KaganDriver.boot(tmp_path)
    try:
        projects = await driver.list_projects()
        assert isinstance(projects, list)

        project_id = await driver.create_project("Standalone Project")
        assert project_id is not None

        projects = await driver.list_projects()
        assert any(p.id == project_id for p in projects)
    finally:
        await driver.teardown()


async def test_async_context_manager_disposes_cleanly(tmp_path: Path) -> None:
    """Async context manager calls close() on exit without raising."""
    db_path = tmp_path / "ctx.db"
    async with KaganCore(db_path=db_path) as client:
        project = await client.projects.create("CM Project")
        assert project.id is not None


async def test_preflight_returns_structured_results(tmp_path: Path) -> None:
    """preflight() returns PreflightCheckResult list with required fields."""
    db_path = tmp_path / "preflight.db"
    client = KaganCore(db_path=db_path)
    try:
        results = await client.preflight()
        assert isinstance(results, list)
        assert len(results) >= 1

        for result in results:
            assert hasattr(result, "name")
            assert hasattr(result, "status")
            assert hasattr(result, "message")
            assert hasattr(result, "fix_hint")
            assert result.status in ("pass", "warn", "fail")

        git_check = next((r for r in results if r.name == "git"), None)
        assert git_check is not None
        assert git_check.status == "pass"
    finally:
        client.close()


def test_client_close_is_idempotent(client: KaganCore) -> None:
    client.close()
    client.close()


def test_reset_wipes_all_data(client: KaganCore) -> None:
    async def run():
        project = await client.projects.create("WipeMe")
        await client.projects.set_active(project.id)
        await client.tasks.create("Doomed task")
        await client.reset()
        projects = await client.projects.list()
        assert projects == []

    asyncio.run(run())
