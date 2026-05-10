"""CLI-specific fixtures for ``tests/e2e_chat/cli``.

Director routing decision
-------------------------
``kg chat --agent fake-agent`` runs an in-process ``KaganCore`` (local SQLite
DB) — it does NOT connect to any ``kagan web`` server.  The
``FakeAgentDirector`` singleton is therefore process-local and cannot be
reached from the test process via HTTP or in-proc scheduling after the
subprocess has been spawned.

Resolution (implemented in Step 5):
- ``KAGAN_FAKE_AGENT=1`` in the subprocess environment causes
  ``run_chat_async`` to call ``register_fake_backend()`` and substitute the
  ``LongLivedACPFactory`` subprocess-spawning path with an in-process
  ``_FakeCLIChatFactory`` (see ``kagan.core._fake_agent.make_fake_chat_factory``).
- Pre-turn scripting uses ``KAGAN_FAKE_AGENT_SCRIPT_FILE``: tests write a JSON
  cue list to a temp file *before* spawning and pass the path via env.  The
  subprocess reads it at factory construction time as the default script for
  every turn that has no per-session director entry.
- Per-session director scheduling (needed for flows that require different
  behaviour per turn, like multiturn) is NOT possible across process boundaries.
  Tests that require per-turn scripting must use a single shared script that
  covers all expected turns, or assert only on the subset of output produced by
  the default script.

Flows that are not testable via CLI PTY without IPC:
- Flow B (multiturn queue drain): separate per-turn scripts are not injectable.
  The test asserts on the first turn reply only.
- Flow C (permission gate): permission approval requires UI signals not exposed
  over PTY.  The test asserts that the tool call appears in output.
- Flow I (interrupt): Ctrl-C during streaming is tested but the guarantee that
  "should not arrive" never appears is best-effort due to timing.

All files in this package use ``pytestmark = [pytest.mark.e2e_chat]`` and
``pytest.mark.skipif(sys.platform == "win32", reason="pty not available on Windows")``.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from tests.e2e_chat.helpers.pty import write_script_file
from tests.helpers.fake_agent_backend import FakeCue


def _write_cues(dest: Path, cues: list[FakeCue]) -> Path:
    """Serialise ``FakeCue`` list to JSON and write to *dest*."""
    items = [{k: v for k, v in asdict(c).items() if v is not None} for c in cues]
    return write_script_file(dest, items)


def _init_git(workdir: Path, home: Path) -> None:
    """Initialise a git repo in *workdir* with an empty commit."""
    git_env = {
        **os.environ,
        "HOME": str(home),
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=workdir,
        check=True,
        capture_output=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=workdir,
        check=True,
        capture_output=True,
        env=git_env,
    )


async def _bootstrap_kagan_project(workdir: Path) -> None:
    """Pre-create a Kagan project linked to *workdir* in the subprocess DB.

    The subprocess uses ``KAGAN_DATA_DIR=workdir``, so the DB lives at
    ``workdir/kagan.db``.  Creating the project here avoids the interactive
    project-name prompt in ``ChatController.ensure_project``.
    """
    from kagan.core._fake_agent import register_fake_backend
    from kagan.core.client import KaganCore

    register_fake_backend()
    db_path = workdir / "kagan.db"
    async with KaganCore(db_path=db_path) as client:
        project = await client.projects.find_by_repo(str(workdir))
        if project is None:
            project = await client.projects.create(workdir.name)
            await client.projects.add_repo(project.id, str(workdir))
        await client.projects.set_active(project.id)


@pytest.fixture
def chat_home(tmp_path: Path) -> Path:
    """Isolated HOME directory for the chat subprocess."""
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def chat_workdir(tmp_path: Path, chat_home: Path) -> Path:
    """Git-initialised workdir with a pre-created Kagan project."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    _init_git(workdir, chat_home)
    asyncio.run(_bootstrap_kagan_project(workdir))
    return workdir


__all__ = ["_write_cues", "chat_home", "chat_workdir"]
