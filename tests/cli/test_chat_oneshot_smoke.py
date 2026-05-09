"""Smoke: ``run_chat_async`` one-shot with ``fake-agent`` backend.

Registers :func:`register_fake_backend` (same contract as ``kagan web`` with
``KAGAN_FAKE_AGENT=1``). Uses an isolated ``KAGAN_DATA_DIR`` and a seeded git
repo so :meth:`ChatController.ensure_project` succeeds non-interactively.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from tests.helpers.driver import KaganDriver

from kagan.cli.chat.repl import run_chat_async
from kagan.core._fake_agent import register_fake_backend

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.smoke, pytest.mark.asyncio]


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "test@kagan.dev"],
        ["git", "config", "user.name", "Test"],
        ["git", "commit", "--allow-empty", "-m", "init"],
    ):
        subprocess.run(cmd, cwd=path, check=True, capture_output=True)


async def test_chat_oneshot_fake_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAGAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAGAN_FAKE_AGENT_DELAY_MS", "0")
    monkeypatch.setenv("KAGAN_CHAT_SKIP_BOOT_ANIMATION", "1")

    repo = tmp_path / "repo"
    _git_init(repo)

    driver = await KaganDriver.boot(tmp_path)
    try:
        await driver.create_project("CLI chat smoke", repo_path=str(repo.resolve()))
    finally:
        await driver.teardown()

    register_fake_backend()
    monkeypatch.chdir(repo)

    await run_chat_async(prompt="ping", agent="fake-agent")
