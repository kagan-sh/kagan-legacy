"""git.repo_root — the sync toplevel finder the entrypoint uses to scope the ledger."""

import subprocess
from pathlib import Path

import pytest

from kagan.core import git
from kagan.core.errors import WorktreeError


def _init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)


def test_repo_root_from_subdir_returns_toplevel(tmp_path: Path) -> None:
    # CLI ledger scope: run from a nested subdir of a git repo and still resolve
    # the toplevel, so a deep cwd does not split the ledger into a sibling folder.
    repo = tmp_path / "proj"
    repo.mkdir()
    _init(repo)
    subdir = repo / "a" / "b"
    subdir.mkdir(parents=True)

    assert git.repo_root(subdir) == repo.resolve()


def test_repo_root_outside_a_repo_is_none(tmp_path: Path) -> None:
    # Outside any git repo there is no toplevel; the entrypoint must fall back to
    # cwd rather than crash or guess a wrong root.
    assert git.repo_root(tmp_path) is None


@pytest.mark.parametrize(
    "args", [["push", "origin", "main"], ["merge", "main"], ["reset", "--hard"]]
)
async def test_run_git_rejects_mutating_subcommands(tmp_path: Path, args: list[str]) -> None:
    # TUI-SHIP-05: the no-push/no-merge guarantee is structural — run_git only
    # permits read-only subcommands, so push/merge/reset raise rather than execute.
    # Fails if the allowlist is dropped and run_git forwards arbitrary git to disk.
    repo = tmp_path / "proj"
    repo.mkdir()
    _init(repo)
    with pytest.raises(WorktreeError, match="not permitted"):
        await git.run_git(args, cwd=repo)


def test_git_subcommand_skips_global_flag_values() -> None:
    # R1: the denylist must read the real subcommand past git's global flags. The
    # `-c name=value` value token is NOT the subcommand (commit_all uses exactly this
    # shape: `-c commit.gpgsign=false commit`); a naive first-non-flag scan mis-reads it.
    assert git.git_subcommand(("-c", "commit.gpgsign=false", "commit", "-m", "x")) == "commit"
    assert git.git_subcommand(("-C", "/some/path", "status")) == "status"
    assert git.git_subcommand(("rev-parse", "HEAD")) == "rev-parse"


@pytest.mark.parametrize(
    "args", [["push", "origin", "main"], ["reset", "--hard"], ["clean", "-fdx"], ["rebase", "main"]]
)
async def test_private_run_git_denies_irreversible_verbs(tmp_path: Path, args: list[str]) -> None:
    # R1: the ruin-guard is symmetric — even the PRIVATE _run_git (which mutating
    # internals use) refuses push/reset/clean/rebase at the spawn chokepoint, so a
    # future careless internal call raises instead of externalizing ruin.
    repo = tmp_path / "proj"
    repo.mkdir()
    _init(repo)
    with pytest.raises(WorktreeError, match="denied"):
        await git._run_git(*args, cwd=repo, check=False)


async def test_ruin_guard_does_not_block_kagan_own_mutations(tmp_path: Path) -> None:
    # R1 must not trip kagan's own legitimate git: init + add + `-c ... commit`. If the
    # denylist over-reached (e.g. denied "commit" via the -c value), this would raise.
    repo = tmp_path / "proj"
    await git.init_repo(repo, create_initial_commit=True)
    (repo / "f.txt").write_text("x", encoding="utf-8")
    await git.commit_all(repo, "add file")
    head = await git.run_git(["rev-parse", "HEAD"], cwd=repo)
    assert head


async def test_delete_kagan_task_branches_only_deletes_owned_prefix(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    await git.init_repo(repo, create_initial_commit=True)
    await git._run_git("branch", "kagan/task-abc12345", cwd=repo)
    await git._run_git("branch", "kagan/other", cwd=repo)

    deleted, failed = await git.delete_kagan_task_branches(repo)

    assert deleted == ["kagan/task-abc12345"]
    assert failed == []
    branches, _ = await git._run_git("branch", "--format=%(refname:short)", cwd=repo)
    assert "kagan/task-abc12345" not in branches
    assert "kagan/other" in branches


def test_user_identity_reads_name_and_email(tmp_path: Path) -> None:
    # Lever 6: the approver string is "Name <email>" from the repo's git config.
    # config is NOT in run_git's allowlist, so this uses the sync subprocess helper.
    repo = tmp_path / "proj"
    repo.mkdir()
    _init(repo)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "a@x.io"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Alice"], check=True)
    assert git.user_identity(repo) == "Alice <a@x.io>"


def test_user_identity_none_when_email_unset(tmp_path: Path, monkeypatch) -> None:
    # No configured email -> no distinct approver identity (the cross-team caveat).
    # Point HOME at an empty dir so the dev/CI global gitconfig can't leak in.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    repo = tmp_path / "proj"
    repo.mkdir()
    _init(repo)
    assert git.user_identity(repo) is None


async def test_remote_has_branch_tri_state(tmp_path: Path) -> None:
    # Phase 12c ship §2: read-only `git ls-remote --heads origin <branch>`.
    # True when the branch is on origin, False when absent, None when unverifiable
    # (no origin configured / network error).
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    _init(work)
    env = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(
        ["git", "-C", str(work), *env, "commit", "--allow-empty", "-m", "x", "-q"], check=True
    )
    subprocess.run(["git", "-C", str(work), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(origin)], check=True)

    # absent before push
    assert await git.remote_has_branch(work, "main") is False
    subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "main"], check=True)
    # present after push
    assert await git.remote_has_branch(work, "main") is True
    # a branch that was never pushed stays absent
    assert await git.remote_has_branch(work, "feature/never-pushed") is False

    # no origin configured -> unverifiable (None), never a false "absent"
    lone = tmp_path / "lone"
    lone.mkdir()
    _init(lone)
    assert await git.remote_has_branch(lone, "main") is None


async def test_run_git_allows_read_only_inspection(tmp_path: Path) -> None:
    # The allowlist must still let the harness's own read-only callers through
    # (rev-parse/diff); otherwise base-commit capture and diff harvest break.
    repo = tmp_path / "proj"
    repo.mkdir()
    _init(repo)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-m",
            "x",
            "-q",
        ],
        check=True,
    )
    head = await git.run_git(["rev-parse", "HEAD"], cwd=repo)
    assert head.strip()
