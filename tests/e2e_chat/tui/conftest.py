"""TUI-specific fixtures for ``tests/e2e_chat/tui/``.

All tests in this package run in-process against a real :class:`KaganApp`
via :class:`KaganDriver` + ``fake-agent`` backend. The orchestrator chat
backend is patched to a no-op ``warm_orchestrator_backend`` so tests never
try to spawn a real agent subprocess.

Director scheduling is done via :func:`director_inproc.schedule_inproc`
before the turn starts so the fake-agent backend finds its script at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.helpers.driver import KaganDriver
from tests.helpers.fake_agent_backend import ensure_fake_agent_backend_registered

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _register_fake_backend() -> None:
    """Ensure the fake-agent backend is registered for every TUI test."""
    ensure_fake_agent_backend_registered()


@pytest.fixture
async def tui_driver(tmp_path: Path) -> Any:
    """Booted KaganDriver with a project and tutorial dismissed.

    Yields the driver; caller is responsible for app lifecycle (run_test).
    Tears down after the test.
    """
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("E2E Chat TUI Project")
    await driver.settings_update(
        {
            "ui.tui_tutorial_seen": "true",
            "open_last_project_on_startup": "true",
        }
    )
    yield driver
    await driver.teardown()
