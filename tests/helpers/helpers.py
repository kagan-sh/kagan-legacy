"""Shared test helpers: git repo setup, commit utilities."""

import asyncio
from pathlib import Path


async def _run_git(*args: str, cwd: Path) -> tuple[int, str, str]:
    """Run a git command, returning (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout_bytes.decode(errors="replace").strip(),
        stderr_bytes.decode(errors="replace").strip(),
    )


async def make_git_repo(repo_path: Path, base_branch: str = "main") -> dict[str, object]:
    """Initialize a git repo with initial commit. Returns result dict for assertions."""
    repo_path.mkdir(parents=True, exist_ok=True)
    await _run_git("init", "-b", base_branch, cwd=repo_path)
    await _run_git("config", "user.email", "test@example.com", cwd=repo_path)
    await _run_git("config", "user.name", "Test User", cwd=repo_path)
    # Create initial commit so the branch exists
    readme = repo_path / "README.md"
    readme.write_text("# Test repo\n", encoding="utf-8")
    await _run_git("add", "README.md", cwd=repo_path)
    rc, _, stderr = await _run_git(
        "commit", "--no-gpg-sign", "-m", "chore: initial commit", cwd=repo_path
    )
    return {"path": repo_path, "branch": base_branch, "success": rc == 0, "stderr": stderr}


async def commit_file(
    repo_path: Path,
    relative_path: str,
    content: str,
    *,
    message: str = "feat: add file",
) -> bool:
    """Write a file and commit it in the repo. Returns True on success."""
    file_path = repo_path / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    rc_add, _, _ = await _run_git("add", relative_path, cwd=repo_path)
    if rc_add != 0:
        return False
    rc_commit, _, _ = await _run_git("commit", "--no-gpg-sign", "-m", message, cwd=repo_path)
    return rc_commit == 0
