"""Git helper utilities for tests that need a real git repo.

Promotes the inline ``make_git_repo`` pattern from
``tests/helpers/helpers.py`` into a named entry-point so call-sites
can import a single, canonical function rather than duplicating setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.helpers.helpers import make_git_repo as _make_git_repo

if TYPE_CHECKING:
    from pathlib import Path


async def init_git_repo(repo_path: Path, *, base_branch: str = "main") -> Path:
    """Initialise a bare-bones git repo at *repo_path* with one commit.

    Creates the directory if absent, configures a local identity,
    writes a ``README.md``, and makes an initial commit.

    Returns *repo_path* on success.
    Raises ``RuntimeError`` if the initial commit fails (e.g. git not
    installed in this environment).
    """
    result = await _make_git_repo(repo_path, base_branch)
    if not result.get("success"):
        raise RuntimeError(
            f"Failed to initialise git repo at {repo_path}: {result.get('stderr', '')}"
        )
    return repo_path


__all__ = ["init_git_repo"]
