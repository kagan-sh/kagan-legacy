"""TUI-flow fixtures.

All tests in this package run in-process against a real :class:`KaganApp`
via :class:`KaganDriver`. The fake-agent backend is auto-registered.

Mock at the ACP seam (``app.core.chat._acp``) — never at the widget
level. Patches must be applied before ``app.run_test()``; restore in
``finally`` to keep tests isolated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.helpers.driver import KaganDriver
from tests.helpers.fake_agent_backend import ensure_fake_agent_backend_registered

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


@pytest.fixture(autouse=True)
def _register_fake_backend() -> None:
    """Ensure the fake-agent backend is registered for every flow test."""
    ensure_fake_agent_backend_registered()


@pytest.fixture
async def tui_driver(tmp_path: Path) -> Any:
    """Booted KaganDriver with a project + tutorial dismissed.

    Caller drives the lifecycle: ``async with app.run_test() as pilot:``.
    Teardown closes the core context after the test.
    """
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("E2E TUI Project")
    await driver.settings_update(
        {
            "ui.tui_tutorial_seen": "true",
            "open_last_project_on_startup": "true",
        }
    )
    yield driver
    await driver.teardown()
