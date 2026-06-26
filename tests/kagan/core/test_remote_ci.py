import os
from pathlib import Path

import pytest

from kagan.core.models import Task
from kagan.core.remote_ci import RemoteCi


@pytest.fixture
def remote_ci(tmp_path: Path):
    return RemoteCi(tmp_path)


@pytest.mark.asyncio
async def test_no_pr_url_returns_unknown(remote_ci):
    # TUI-POSTPR-01: with no PR open there is nothing remote to read -> unknown.
    status, checks = await remote_ci.fetch(Task(id="t-1", title="x"))
    assert status == "unknown"
    assert checks == []


@pytest.mark.asyncio
async def test_gh_failure_degrades_to_unknown(remote_ci, monkeypatch):
    # TUI-POSTPR-04: gh missing / non-zero / bad JSON must degrade, never crash a gate.
    task = Task(id="t-1", title="x", remote_pr_url="https://github.com/o/r/pull/1")

    async def fake(_args):
        return None  # gh missing / non-zero / bad JSON

    monkeypatch.setattr(remote_ci, "_gh_json", fake)
    status, checks = await remote_ci.fetch(task)
    assert status == "unknown"
    assert checks == []


@pytest.mark.asyncio
async def test_parses_failure_as_canonical_fail(remote_ci, monkeypatch):
    # TUI-POSTPR-02: raw gh "FAILURE" must normalize to canonical "fail" so the inbox
    # derives ci_failed == (remote_ci_status == "fail").
    task = Task(id="t-1", title="x", remote_pr_url="https://github.com/o/r/pull/1")

    async def fake(_args):
        return [
            {"name": "test", "state": "SUCCESS", "link": "http://x"},
            {"name": "lint", "state": "FAILURE", "link": "http://y"},
        ]

    monkeypatch.setattr(remote_ci, "_gh_json", fake)
    status, checks = await remote_ci.fetch(task)
    assert status == "fail"  # NOT the raw "failure"/"failing"
    assert len(checks) == 2
    assert checks[1].passed is False


@pytest.mark.asyncio
async def test_parses_pending(remote_ci, monkeypatch):
    # TUI-POSTPR-01: an in-progress check normalizes to "pending", not pass/fail.
    task = Task(id="t-1", title="x", remote_pr_url="https://github.com/o/r/pull/2")

    async def fake(_args):
        return [{"name": "test", "state": "PENDING", "link": "http://x"}]

    monkeypatch.setattr(remote_ci, "_gh_json", fake)
    status, _ = await remote_ci.fetch(task)
    assert status == "pending"


@pytest.mark.asyncio
async def test_parses_success_as_canonical_pass(remote_ci, monkeypatch):
    # TUI-MIRROR-03: an all-green PR normalizes to canonical "pass".
    task = Task(id="t-1", title="x", remote_pr_url="https://github.com/o/r/pull/3")

    async def fake(_args):
        return [{"name": "test", "state": "SUCCESS", "link": "http://x"}]

    monkeypatch.setattr(remote_ci, "_gh_json", fake)
    status, _ = await remote_ci.fetch(task)
    assert status == "pass"


@pytest.mark.asyncio
async def test_pr_url_reads_url_for_branch(remote_ci, monkeypatch):
    # Lever 7 prereq: `gh pr view <branch> --json url` -> the PR URL so the inert
    # tripwire goes live. The branch must be passed through to gh.
    seen: dict = {}

    async def fake(args):
        seen["args"] = args
        return {"url": "https://github.com/o/r/pull/7"}

    monkeypatch.setattr(remote_ci, "_gh_json", fake)
    url = await remote_ci.pr_url("kagan/task-1")
    assert url == "https://github.com/o/r/pull/7"
    assert "kagan/task-1" in seen["args"]


@pytest.mark.asyncio
async def test_pr_url_is_none_when_gh_absent_or_no_pr(remote_ci, monkeypatch):
    # gh missing / no PR yet (human pushed before `gh pr create`) must degrade to
    # None, never crash — the state flip must not depend on it.
    async def fake(_args):
        return None

    monkeypatch.setattr(remote_ci, "_gh_json", fake)
    assert await remote_ci.pr_url("kagan/task-1") is None
    assert await remote_ci.pr_url(None) is None  # no branch -> no gh call, None


@pytest.mark.asyncio
async def test_gh_timeout_degrades_to_unknown(tmp_path, monkeypatch):
    # F4: a network-stalled gh must not hang the ship / CI-poll path. A real sleeping
    # `gh` on PATH is killed at the (lowered) timeout and degrades to unknown — parity
    # with the git/mirror bounded-subprocess idiom.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/sh\nsleep 10\n")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setattr("kagan.core.remote_ci._TIMEOUT", 0.3)
    rc = RemoteCi(tmp_path)
    task = Task(id="t-1", title="x", remote_pr_url="https://github.com/o/r/pull/1")
    status, checks = await rc.fetch(task)
    assert status == "unknown"
    assert checks == []
