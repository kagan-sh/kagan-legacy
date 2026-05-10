"""Fake-agent fixture isolation from production session orchestration."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from kagan.core import KaganCore

pytestmark = [pytest.mark.unit]

if TYPE_CHECKING:
    from pathlib import Path


def _init_git(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "test@kagan.dev"],
        ["git", "config", "user.name", "Test"],
        ["git", "commit", "--allow-empty", "-m", "init"],
    ):
        subprocess.run(cmd, cwd=path, check=True, capture_output=True)
    return path


async def test_normal_acp_session_run_does_not_import_fake_agent_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A normal ACP backend should not load the web/e2e fake-agent fixture."""
    sys.modules.pop("kagan.core._fake_agent", None)

    async def _spawn_agent_via_acp(*args: Any, **kwargs: Any) -> tuple[int, asyncio.Task[None]]:
        del args, kwargs
        task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(0))
        return 12345, task

    monkeypatch.setattr("kagan.core._sessions.spawn_agent_via_acp", _spawn_agent_via_acp)

    core = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        project = await core.projects.create("Normal ACP Project")
        await core.projects.set_active(project.id)
        await core.projects.add_repo(project.id, str(_init_git(tmp_path / "repo")))
        task = await core.tasks.create("Normal ACP run")

        await core.tasks.run(task.id, agent_backend="claude-code")

        assert "kagan.core._fake_agent" not in sys.modules
    finally:
        await core.aclose()
