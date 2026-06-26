"""Phase 10 Track B: the committable subset is committable out of the box, and
Track A: PROTECTED tampering survives the run-artifact strip in the real harvest
path. Each test fails without the Phase 10 fix.
"""

import os
import subprocess
from pathlib import Path

import pytest

from kagan.core import Harness
from tests.helpers.gitrepo import make_repo

# Agent edits the PROTECTED review contract (.kagan/repo.yaml) inside the worktree.
# This is tampering — it must flag as drift, NOT be swallowed by the run-artifact
# strip. (.kagan/ask + .mcp.json the harness writes itself ARE run-artifacts.)
PROTECTED_TAMPERER = """#!/bin/sh
mkdir -p .kagan
echo "evil: true" >> .kagan/repo.yaml
echo '{"type":"done","payload":{}}' >> .kagan/ask
"""


@pytest.fixture
async def repo(tmp_path: Path):
    return await make_repo(tmp_path / "repo")


def _install(bin_dir, name, body):
    bin_dir.mkdir(parents=True, exist_ok=True)
    s = bin_dir / name
    s.write_text(body)
    s.chmod(0o755)


def _check_ignored(repo_root: Path, relpath: str) -> bool:
    # git check-ignore exits 0 when the path IS ignored, 1 when it is not.
    rc = subprocess.run(
        ["git", "-C", str(repo_root), "check-ignore", "-q", relpath],
        capture_output=True,
    ).returncode
    return rc == 0


async def test_protected_edit_flags_as_drift_through_harvest(repo, tmp_path, monkeypatch):
    # Phase 10 Track A: the protection used to be DEAD — _harvest stripped any
    # .kagan/* finding AFTER detect_drift, swallowing an agent edit to the protected
    # review contract. Now run-artifacts are stripped from the DIFF before drift
    # detection, so a .kagan/repo.yaml edit still reaches detect_drift and flags.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "tamperer", PROTECTED_TAMPERER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("x")
    core.configure_task(task.id, agent_cli="tamperer", scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.drift is True
    protected = [f for f in task.findings if "repo.yaml" in f.location and f.severity == "blocking"]
    assert protected, "agent edit to .kagan/repo.yaml must flag as protected-path drift"
    # And kagan's own run-artifacts (.kagan/ask) never appear as drift findings.
    assert not [f for f in task.findings if f.location == ".kagan/ask"]


def test_scaffold_writes_kagan_gitignore_for_committable_subset(repo, monkeypatch):
    # Phase 10 Track B: creating the in-repo ledger scaffolds .kagan/.gitignore so
    # .kagan/state is ignored while .kagan/repo.yaml and .kagan/reviews/ stay
    # trackable. Point the harness at the in-repo default (not an arbitrary tmp dir)
    # so the scaffold guard fires.
    Harness(data_dir=repo / ".kagan" / "state", repo_root=repo)

    gi = repo / ".kagan" / ".gitignore"
    assert gi.exists()
    assert "state/" in gi.read_text().splitlines()

    # git check-ignore confirms the operational store is ignored...
    assert _check_ignored(repo, ".kagan/state")
    assert _check_ignored(repo, ".kagan/state/tasks/t-1/state.json")
    # ...while the committable subset is NOT ignored.
    assert not _check_ignored(repo, ".kagan/repo.yaml")
    assert not _check_ignored(repo, ".kagan/reviews/2026-01-01-x.md")


def test_scaffold_does_not_fire_for_arbitrary_data_dir(repo, tmp_path):
    # The guard must NOT scaffold for a tmp data_dir (tests, KAGAN_DATA_DIR): only
    # the in-repo .kagan/state ledger gets the .gitignore.
    Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    assert not (repo / ".kagan" / ".gitignore").exists()


def test_scaffold_never_clobbers_existing_kagan_gitignore(repo):
    # A hand-edited .kagan/.gitignore is preserved; state/ is appended if missing,
    # left alone if present.
    kagan = repo / ".kagan"
    kagan.mkdir(parents=True, exist_ok=True)
    (kagan / ".gitignore").write_text("# mine\nscratch/\n", encoding="utf-8")

    Harness(data_dir=repo / ".kagan" / "state", repo_root=repo)

    text = (kagan / ".gitignore").read_text()
    assert "# mine" in text
    assert "scratch/" in text
    assert "state/" in text.splitlines()


async def test_worktree_creation_appends_kagan_worktrees_once(repo, tmp_path, monkeypatch):
    # Phase 10 Track B: worktree creation idempotently appends .kagan_worktrees/ to
    # the repo-root .gitignore (never clobbering). Two worktrees -> one entry, and
    # git check-ignore confirms the worktree dir is ignored.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", "#!/bin/sh\nmkdir -p src\necho x >> src/new.py\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    a = core.create_task("a")
    b = core.create_task("b")
    core.configure_task(a.id, agent_cli="fakeagent", scope=["src/**"])
    core.configure_task(b.id, agent_cli="fakeagent", scope=["src/**"])

    await core.start_task(a.id)
    await core.await_agent(a.id)  # harvest lands task a in REVIEW, clearing the cap
    await core.start_task(b.id)
    await core.await_agent(b.id)

    gi = repo / ".gitignore"
    assert gi.read_text().count(".kagan_worktrees/") == 1
    assert _check_ignored(repo, ".kagan_worktrees")
