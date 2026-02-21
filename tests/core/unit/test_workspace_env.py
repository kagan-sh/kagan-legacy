"""Tests for shared workspace cache environment overrides."""

from __future__ import annotations

import sys
from pathlib import Path

from kagan.core.acp.kagan_agent import KaganAgent
from kagan.core.acp.terminal import TerminalRunner
from kagan.core.config import AgentConfig
from kagan.core.services.sessions import build_kagan_session_env
from kagan.core.workspace_env import workspace_env_overrides


def _create_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.1.0"\n')
    (repo / "uv.lock").write_text("version = 1\n")
    return repo


def test_workspace_env_overrides_sets_shared_cargo_and_uv_paths(tmp_path: Path) -> None:
    repo = _create_repo(tmp_path)
    cache_root = tmp_path / "shared-cache"

    overrides = workspace_env_overrides(
        repo,
        base_env={"KAGAN_SHARED_WORKSPACE_CACHE_ROOT": str(cache_root)},
    )

    assert "CARGO_TARGET_DIR" in overrides
    assert Path(overrides["CARGO_TARGET_DIR"]).is_relative_to(cache_root)
    assert "cargo-target" in Path(overrides["CARGO_TARGET_DIR"]).parts

    assert "UV_PROJECT_ENVIRONMENT" in overrides
    assert Path(overrides["UV_PROJECT_ENVIRONMENT"]).is_relative_to(cache_root)
    assert "uv-envs" in Path(overrides["UV_PROJECT_ENVIRONMENT"]).parts
    assert f"py{sys.version_info.major}.{sys.version_info.minor}" in (
        Path(overrides["UV_PROJECT_ENVIRONMENT"]).name
    )


def test_workspace_env_overrides_respects_disable_flag_and_existing_env(tmp_path: Path) -> None:
    repo = _create_repo(tmp_path)

    disabled = workspace_env_overrides(repo, base_env={"KAGAN_SHARED_WORKSPACE_CACHE": "off"})
    assert disabled == {}

    existing = workspace_env_overrides(
        repo,
        base_env={
            "CARGO_TARGET_DIR": "/tmp/already-set-cargo",
            "UV_PROJECT_ENVIRONMENT": "/tmp/already-set-uv",
        },
    )
    assert "CARGO_TARGET_DIR" not in existing
    assert "UV_PROJECT_ENVIRONMENT" not in existing


def test_build_kagan_session_env_includes_shared_workspace_cache(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _create_repo(tmp_path)
    cache_root = tmp_path / "cache-root"
    monkeypatch.setenv("KAGAN_SHARED_WORKSPACE_CACHE_ROOT", str(cache_root))
    monkeypatch.delenv("CARGO_TARGET_DIR", raising=False)
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)

    env = build_kagan_session_env(
        task_id="task-123",
        task_title="Task Title",
        worktree_path=repo,
        project_root=repo,
    )

    assert env["KAGAN_TASK_ID"] == "task-123"
    assert env["KAGAN_TASK_TITLE"] == "Task Title"
    assert env["KAGAN_WORKTREE_PATH"] == str(repo)
    assert env["KAGAN_PROJECT_ROOT"] == str(repo)
    assert Path(env["CARGO_TARGET_DIR"]).is_relative_to(cache_root)
    assert Path(env["UV_PROJECT_ENVIRONMENT"]).is_relative_to(cache_root)


def test_kagan_agent_build_process_env_includes_shared_workspace_cache(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _create_repo(tmp_path)
    cache_root = tmp_path / "cache-root"
    monkeypatch.setenv("KAGAN_SHARED_WORKSPACE_CACHE_ROOT", str(cache_root))
    monkeypatch.delenv("CARGO_TARGET_DIR", raising=False)
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)

    agent = KaganAgent(
        repo,
        AgentConfig(
            identity="claude.com",
            name="Claude Code",
            short_name="claude",
            run_command={"*": "echo"},
        ),
    )
    env = agent._build_process_env()

    assert env["KAGAN_CWD"] == str(repo.absolute())
    assert Path(env["CARGO_TARGET_DIR"]).is_relative_to(cache_root)
    assert Path(env["UV_PROJECT_ENVIRONMENT"]).is_relative_to(cache_root)


def test_terminal_runner_build_environment_includes_shared_workspace_cache(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _create_repo(tmp_path)
    cache_root = tmp_path / "cache-root"
    monkeypatch.setenv("KAGAN_SHARED_WORKSPACE_CACHE_ROOT", str(cache_root))
    monkeypatch.delenv("CARGO_TARGET_DIR", raising=False)
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)

    runner = TerminalRunner(terminal_id="terminal-1", command="echo", project_root=repo)
    env = runner._build_environment(str(repo))

    assert Path(env["CARGO_TARGET_DIR"]).is_relative_to(cache_root)
    assert Path(env["UV_PROJECT_ENVIRONMENT"]).is_relative_to(cache_root)
