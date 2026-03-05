"""Canonical test fixtures: standardised board and git_board environments.

Import these in conftest.py to provide project-wide fixtures.
Test files that need customised setup (extra tasks, special config)
should define local fixtures that build on ``board`` or ``git_board``.
"""

from pathlib import Path

import pytest

from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo


@pytest.fixture
async def board(tmp_path: Path) -> KaganDriver:
    """Fresh KaganDriver with an active project (no git repo)."""
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Test Project")
    yield driver  # type: ignore[misc]
    await driver.teardown()


@pytest.fixture
async def git_board(tmp_path: Path) -> KaganDriver:
    """Fresh KaganDriver with an active project linked to a real git repo."""
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Test Project", repo_path=str(repo_path))
    yield driver  # type: ignore[misc]
    await driver.teardown()
