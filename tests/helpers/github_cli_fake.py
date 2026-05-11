"""Helper: create a fake ``gh`` executable on PATH for subprocess-level tests.

Use when a test exercises code that calls ``subprocess.run`` or
``asyncio.create_subprocess_exec`` with ``gh`` and needs a real process to
run instead of a mock.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def make_fake_gh_bin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: str = "gho_fake_token",
    exit_code: int = 0,
) -> Path:
    """Write a minimal ``gh`` shell script to *tmp_path*/fake-gh-bin/ and
    prepend that directory to ``PATH`` so ``shutil.which("gh")`` resolves to
    it for the duration of the current test.

    The script writes *stdout* to standard output and exits with *exit_code*
    regardless of the arguments it receives.  Returns the path to the script.
    """
    bin_dir = tmp_path / "fake-gh-bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "gh"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{stdout}'\nexit {exit_code}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    return script


__all__ = ["make_fake_gh_bin"]
