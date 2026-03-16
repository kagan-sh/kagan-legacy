"""Feature tests: PAIR Launchers — docs/internal/features/core.md §7."""

from pathlib import Path
from unittest.mock import patch

import pytest

from kagan.core import AgentError
from kagan.core._launchers import (
    COPILOT_CHAT_EXTENSION_ID,
    build_ide_command,
    build_neovim_command,
    build_tmux_command,
    build_vscode_chat_launcher_command,
    detect_vscode_chat_autostart,
    resolve_launcher,
)

pytestmark = [pytest.mark.core, pytest.mark.unit]


def test_build_tmux_command_basic() -> None:
    cmd = build_tmux_command(
        session_name="kagan-abc123",
        worktree_path="/workspace/project",
        agent_cmd="claude",
    )

    assert cmd == [
        "tmux",
        "new-session",
        "-d",
        "-s",
        "kagan-abc123",
        "-c",
        "/workspace/project",
        "claude",
    ]


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


def test_build_ide_command_unknown_raises_error() -> None:
    with pytest.raises(AgentError, match="unknown ide"):
        build_ide_command(ide="unknown-ide", worktree_path="/workspace/project")


def test_build_neovim_command() -> None:
    cmd = build_neovim_command(worktree_path="/workspace/project")

    assert cmd == ["nvim", "/workspace/project"]


def test_build_vscode_chat_launcher_command_basic() -> None:
    cmd = build_vscode_chat_launcher_command(
        ide="vscode",
        worktree_path="/workspace/project",
        prompt_file="/workspace/project/.kagan/start_prompt.md",
    )

    assert cmd == [
        "code",
        "chat",
        "--mode",
        "agent",
        "--add-file",
        "/workspace/project/.kagan/start_prompt.md",
        "--new-window",
    ]


def test_build_vscode_chat_launcher_command_with_seed_prompt() -> None:
    cmd = build_vscode_chat_launcher_command(
        ide="vscode",
        worktree_path="/workspace/project",
        prompt_file="/workspace/project/.kagan/start_prompt.md",
        seed_prompt="Implement feature X",
    )

    assert cmd == [
        "code",
        "chat",
        "--mode",
        "agent",
        "--add-file",
        "/workspace/project/.kagan/start_prompt.md",
        "--new-window",
        "Implement feature X",
    ]


def test_build_vscode_chat_launcher_command_cursor() -> None:
    cmd = build_vscode_chat_launcher_command(
        ide="cursor",
        worktree_path="/workspace/project",
        prompt_file="/workspace/project/.kagan/start_prompt.md",
    )

    assert cmd == [
        "cursor",
        "chat",
        "--mode",
        "agent",
        "--add-file",
        "/workspace/project/.kagan/start_prompt.md",
        "--new-window",
    ]


def test_build_vscode_chat_launcher_command_windsurf() -> None:
    cmd = build_vscode_chat_launcher_command(
        ide="windsurf",
        worktree_path="/workspace/project",
        prompt_file="/workspace/project/.kagan/start_prompt.md",
    )

    assert cmd == [
        "windsurf",
        "chat",
        "--mode",
        "agent",
        "--add-file",
        "/workspace/project/.kagan/start_prompt.md",
        "--new-window",
    ]


def test_build_vscode_chat_launcher_command_kiro() -> None:
    cmd = build_vscode_chat_launcher_command(
        ide="kiro",
        worktree_path="/workspace/project",
        prompt_file="/workspace/project/.kagan/start_prompt.md",
    )

    assert cmd == [
        "kiro",
        "chat",
        "--mode",
        "agent",
        "--add-file",
        "/workspace/project/.kagan/start_prompt.md",
        "--new-window",
    ]


def test_build_vscode_chat_launcher_command_antigravity() -> None:
    cmd = build_vscode_chat_launcher_command(
        ide="antigravity",
        worktree_path="/workspace/project",
        prompt_file="/workspace/project/.kagan/start_prompt.md",
    )

    assert cmd == [
        "agy",
        "chat",
        "--mode",
        "agent",
        "--add-file",
        "/workspace/project/.kagan/start_prompt.md",
        "--new-window",
    ]


def test_build_vscode_chat_launcher_command_unknown_raises_error() -> None:
    with pytest.raises(AgentError, match="unknown ide"):
        build_vscode_chat_launcher_command(
            ide="unknown-ide",
            worktree_path="/workspace/project",
            prompt_file="/workspace/project/.kagan/start_prompt.md",
        )


def test_detect_vscode_chat_autostart_returns_false_for_unknown_ide() -> None:
    result = detect_vscode_chat_autostart("unknown-ide")
    assert result is False


def test_detect_vscode_chat_autostart_finds_extension(tmp_path: Path) -> None:
    extensions_dir = tmp_path / ".vscode" / "extensions"
    extensions_dir.mkdir(parents=True)

    copilot_dir = extensions_dir / f"{COPILOT_CHAT_EXTENSION_ID}-0.37.6"
    copilot_dir.mkdir()

    with patch(
        "kagan.core._launchers._get_vscode_extensions_dirs",
        return_value=[extensions_dir],
    ):
        result = detect_vscode_chat_autostart("vscode")
        assert result is True


def test_detect_vscode_chat_autostart_no_extension(tmp_path: Path) -> None:
    extensions_dir = tmp_path / ".vscode" / "extensions"
    extensions_dir.mkdir(parents=True)

    other_dir = extensions_dir / "some.other-extension-1.0.0"
    other_dir.mkdir()

    with patch(
        "kagan.core._launchers._get_vscode_extensions_dirs",
        return_value=[extensions_dir],
    ):
        result = detect_vscode_chat_autostart("vscode")
        assert result is False


def test_detect_vscode_chat_autostart_no_extensions_dir(tmp_path: Path) -> None:
    nonexistent_dir = tmp_path / ".vscode" / "extensions"

    with patch(
        "kagan.core._launchers._get_vscode_extensions_dirs",
        return_value=[nonexistent_dir],
    ):
        result = detect_vscode_chat_autostart("vscode")
        assert result is False


def test_detect_vscode_chat_autostart_for_all_ides(tmp_path: Path) -> None:
    ides = ["vscode", "cursor", "windsurf", "kiro", "antigravity"]

    for ide in ides:
        extensions_dir = tmp_path / f".{ide}" / "extensions"
        extensions_dir.mkdir(parents=True)

        copilot_dir = extensions_dir / f"{COPILOT_CHAT_EXTENSION_ID}-0.37.6"
        copilot_dir.mkdir()

        with patch(
            "kagan.core._launchers._get_vscode_extensions_dirs",
            return_value=[extensions_dir],
        ):
            result = detect_vscode_chat_autostart(ide)
            assert result is True, f"Expected True for {ide}"


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


def test_copilot_chat_extension_id() -> None:
    assert COPILOT_CHAT_EXTENSION_ID == "github.copilot-chat"
