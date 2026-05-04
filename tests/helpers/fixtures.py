from pathlib import Path

import pytest

from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo


@pytest.fixture
async def bare_board(tmp_path: Path) -> KaganDriver:
    """KaganDriver with no project created — for project-management tests."""
    driver = await KaganDriver.boot(tmp_path)
    yield driver  # type: ignore[misc]
    await driver.teardown()


@pytest.fixture
async def board(tmp_path: Path) -> KaganDriver:
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Test Project")
    await driver.settings_update({"open_last_project_on_startup": "true"})
    yield driver  # type: ignore[misc]
    await driver.teardown()


@pytest.fixture
async def board_with_task(tmp_path: Path) -> KaganDriver:
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Test Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Test Task")
    yield driver  # type: ignore[misc]
    await driver.teardown()


@pytest.fixture
async def git_board(tmp_path: Path) -> KaganDriver:
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Test Project", repo_path=str(repo_path))
    await driver.settings_update({"open_last_project_on_startup": "true"})
    yield driver  # type: ignore[misc]
    await driver.teardown()
