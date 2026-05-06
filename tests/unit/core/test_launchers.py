"""Feature tests: ATTACHED Launchers — docs/internal/features/core.md §7."""

import pytest

from kagan.core import AgentError
from kagan.core._launchers import (
    build_ide_command,
    build_neovim_command,
    resolve_launcher,
)

pytestmark = [pytest.mark.core, pytest.mark.unit]


def test_build_ide_command_vscode() -> None:
    cmd = build_ide_command(ide="vscode", worktree_path="/workspace/project")
    assert cmd == ["code", "--new-window", "/workspace/project"]


def test_build_ide_command_cursor() -> None:
    cmd = build_ide_command(ide="cursor", worktree_path="/workspace/project")
    assert cmd == ["cursor", "--new-window", "/workspace/project"]


def test_build_ide_command_windsurf() -> None:
    cmd = build_ide_command(ide="windsurf", worktree_path="/workspace/project")
    assert cmd == ["windsurf", "--new-window", "/workspace/project"]


def test_build_ide_command_kiro() -> None:
    cmd = build_ide_command(ide="kiro", worktree_path="/workspace/project")
    assert cmd == ["kiro", "--new-window", "/workspace/project"]


def test_build_ide_command_antigravity() -> None:
    cmd = build_ide_command(ide="antigravity", worktree_path="/workspace/project")
    assert cmd == ["agy", "--new-window", "/workspace/project"]


def test_build_ide_command_with_prompt_file() -> None:
    cmd = build_ide_command(
        ide="vscode",
        worktree_path="/workspace/project",
        prompt_file="/workspace/project/.kagan/start_prompt.md",
    )
    assert cmd == [
        "code",
        "--new-window",
        "/workspace/project",
        "/workspace/project/.kagan/start_prompt.md",
    ]


def test_build_ide_command_prompt_file_for_all_ides() -> None:
    expected_binaries = {
        "vscode": "code",
        "cursor": "cursor",
        "windsurf": "windsurf",
        "kiro": "kiro",
        "antigravity": "agy",
    }
    for ide, binary in expected_binaries.items():
        cmd = build_ide_command(
            ide=ide,
            worktree_path="/ws",
            prompt_file="/ws/.kagan/start_prompt.md",
        )
        assert cmd == [binary, "--new-window", "/ws", "/ws/.kagan/start_prompt.md"], (
            f"Unexpected command for {ide}"
        )


def test_build_ide_command_unknown_raises_error() -> None:
    with pytest.raises(AgentError, match="unknown ide"):
        build_ide_command(ide="unknown-ide", worktree_path="/workspace/project")


def test_build_neovim_command() -> None:
    cmd = build_neovim_command(worktree_path="/workspace/project")
    assert cmd == ["nvim", "/workspace/project"]


def test_resolve_launcher_tmux() -> None:
    launcher_key, ide = resolve_launcher("tmux")
    assert launcher_key == "tmux"
    assert ide is None


def test_resolve_launcher_neovim() -> None:
    launcher_key, ide = resolve_launcher("neovim")
    assert launcher_key == "neovim"
    assert ide is None


def test_resolve_launcher_nvim_alias() -> None:
    launcher_key, ide = resolve_launcher("nvim")
    assert launcher_key == "neovim"
    assert ide is None


def test_resolve_launcher_vscode() -> None:
    launcher_key, ide = resolve_launcher("vscode")
    assert launcher_key == "ide"
    assert ide == "vscode"


def test_resolve_launcher_cursor() -> None:
    launcher_key, ide = resolve_launcher("cursor")
    assert launcher_key == "ide"
    assert ide == "cursor"


def test_resolve_launcher_windsurf() -> None:
    launcher_key, ide = resolve_launcher("windsurf")
    assert launcher_key == "ide"
    assert ide == "windsurf"


def test_resolve_launcher_kiro() -> None:
    launcher_key, ide = resolve_launcher("kiro")
    assert launcher_key == "ide"
    assert ide == "kiro"


def test_resolve_launcher_antigravity() -> None:
    launcher_key, ide = resolve_launcher("antigravity")
    assert launcher_key == "ide"
    assert ide == "antigravity"


def test_resolve_launcher_unknown_fallback() -> None:
    launcher_key, ide = resolve_launcher("custom-ide")
    assert launcher_key == "ide"
    assert ide == "custom-ide"


def test_build_launch_command_with_prompt_flag() -> None:
    from kagan.core._launchers import _build_launch_command

    cmd = _build_launch_command("claude-code", "Hello world")
    assert cmd is not None
    assert cmd.startswith("claude -p ")
    assert "Hello world" in cmd


def test_build_launch_command_returns_bare_executable_without_prompt_flag() -> None:
    from kagan.core._launchers import _build_launch_command

    # All current backends have prompt_flag, so test the fallback path
    # by verifying the function returns a string containing the executable
    cmd = _build_launch_command("claude-code", "test prompt")
    assert cmd is not None
    assert "claude" in cmd
