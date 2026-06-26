"""Load per-file old/new text for lazy in-session diff viewing."""

from pathlib import Path
from typing import TYPE_CHECKING

from kagan.core.errors import WorktreeError
from kagan.core.git import resolve_base_ref, run_git
from kagan.format.diff import DiffViewport, FileDiff, compute_file_diff

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kagan.core.models import Task
    from kagan.format.diff import FileDiff


async def load_file_diff(wt: Path, base_ref: str, path: str) -> FileDiff | None:
    old_text = await _old_text(wt, base_ref, path)
    new_text = _new_text(wt, path)
    return await compute_file_diff(path, old_text, new_text)


async def open_diff_viewport(task: Task) -> DiffViewport | None:
    if not task.changed_files or task.worktree_path is None:
        return None
    wt = Path(task.worktree_path)
    if not wt.is_dir():
        return None
    base_ref = await resolve_base_ref(wt, task.base_branch)

    async def _loader(path: str) -> FileDiff | None:
        return await load_file_diff(wt, base_ref, path)

    return DiffViewport(task.changed_files, loader=_loader)


def make_diff_viewport(
    paths: list[str],
    loader: Callable[[str], Awaitable[FileDiff | None]],
) -> DiffViewport:
    return DiffViewport(paths, loader=loader)


async def _old_text(wt: Path, base_ref: str, path: str) -> str:
    try:
        return await run_git(["show", f"{base_ref}:{path}"], cwd=wt)
    except WorktreeError:
        return ""


def _new_text(wt: Path, path: str) -> str:
    file_path = wt / path
    if not file_path.is_file():
        return ""
    return file_path.read_text(encoding="utf-8", errors="replace")


__all__ = [
    "DiffViewport",
    "load_file_diff",
    "make_diff_viewport",
    "open_diff_viewport",
]
