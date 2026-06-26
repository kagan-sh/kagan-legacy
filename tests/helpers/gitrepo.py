from pathlib import Path

from kagan.core import git


async def make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    await git.init_repo(path, initial_branch="main", create_initial_commit=True)
    return path
