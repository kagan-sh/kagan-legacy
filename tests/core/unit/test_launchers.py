"""Feature tests: PAIR Launchers — docs/internal/features/core.md §7.

Tests for launcher command builders and VSCode chat autostart detection.
"""

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

pytestmark = [pytest.mark.unit]


# -----------------------------------------------------------------------------
# Command builders
# -----------------------------------------------------------------------------


def test_build_tmux_command_basic() -> None:
    """Build tmux command with required parameters."""
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
    """Build VSCode open command."""
    cmd = build_ide_command(ide="vscode", worktree_path="/workspace/project")

    assert cmd == ["code", "--new-window", "/workspace/project"]


def test_build_ide_command_cursor() -> None:
    """Build Cursor open command."""
    cmd = build_ide_command(ide="cursor", worktree_path="/workspace/project")

    assert cmd == ["cursor", "--new-window", "/workspace/project"]


def test_build_ide_command_windsurf() -> None:
    """Build Windsurf open command."""
    cmd = build_ide_command(ide="windsurf", worktree_path="/workspace/project")

    assert cmd == ["windsurf", "--new-window", "/workspace/project"]


def test_build_ide_command_kiro() -> None:
    """Build Kiro open command."""
    cmd = build_ide_command(ide="kiro", worktree_path="/workspace/project")

    assert cmd == ["kiro", "--new-window", "/workspace/project"]


def test_build_ide_command_antigravity() -> None:
    """Build Antigravity open command."""
    cmd = build_ide_command(ide="antigravity", worktree_path="/workspace/project")

    assert cmd == ["agy", "--new-window", "/workspace/project"]


def test_build_ide_command_unknown_raises_error() -> None:
    """Unknown IDE raises AgentError."""
    with pytest.raises(AgentError, match="unknown ide"):
        build_ide_command(ide="unknown-ide", worktree_path="/workspace/project")


def test_build_neovim_command() -> None:
    """Build Neovim command."""
    cmd = build_neovim_command(worktree_path="/workspace/project")

    assert cmd == ["nvim", "/workspace/project"]


# -----------------------------------------------------------------------------
# VSCode chat launcher
# -----------------------------------------------------------------------------


def test_build_vscode_chat_launcher_command_basic() -> None:
    """Build VSCode chat command with basic parameters."""
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
    """Build VSCode chat command with seed prompt."""
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
    """Build Cursor chat command."""
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
    """Build Windsurf chat command."""
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
    """Build Kiro chat command."""
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
    """Build Antigravity chat command."""
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
    """Unknown IDE for chat launcher raises AgentError."""
    with pytest.raises(AgentError, match="unknown ide"):
        build_vscode_chat_launcher_command(
            ide="unknown-ide",
            worktree_path="/workspace/project",
            prompt_file="/workspace/project/.kagan/start_prompt.md",
        )


# -----------------------------------------------------------------------------
# VSCode chat autostart detection
# -----------------------------------------------------------------------------


def test_detect_vscode_chat_autostart_returns_false_for_unknown_ide() -> None:
    """Unknown IDE returns False for chat detection."""
    result = detect_vscode_chat_autostart("unknown-ide")
    assert result is False


def test_detect_vscode_chat_autostart_finds_extension(tmp_path: Path) -> None:
    """Detect copilot-chat extension in extensions directory."""
    # Create mock extensions directory structure
    extensions_dir = tmp_path / ".vscode" / "extensions"
    extensions_dir.mkdir(parents=True)

    # Create copilot-chat extension directory
    copilot_dir = extensions_dir / f"{COPILOT_CHAT_EXTENSION_ID}-0.37.6"
    copilot_dir.mkdir()

    with patch(
        "kagan.core._launchers._get_vscode_extensions_dirs",
        return_value=[extensions_dir],
    ):
        result = detect_vscode_chat_autostart("vscode")
        assert result is True


def test_detect_vscode_chat_autostart_no_extension(tmp_path: Path) -> None:
    """Returns False when copilot-chat extension not found."""
    extensions_dir = tmp_path / ".vscode" / "extensions"
    extensions_dir.mkdir(parents=True)

    # Create some other extension directory
    other_dir = extensions_dir / "some.other-extension-1.0.0"
    other_dir.mkdir()

    with patch(
        "kagan.core._launchers._get_vscode_extensions_dirs",
        return_value=[extensions_dir],
    ):
        result = detect_vscode_chat_autostart("vscode")
        assert result is False


def test_detect_vscode_chat_autostart_no_extensions_dir(tmp_path: Path) -> None:
    """Returns False when extensions directory does not exist."""
    nonexistent_dir = tmp_path / ".vscode" / "extensions"

    with patch(
        "kagan.core._launchers._get_vscode_extensions_dirs",
        return_value=[nonexistent_dir],
    ):
        result = detect_vscode_chat_autostart("vscode")
        assert result is False


def test_detect_vscode_chat_autostart_for_all_ides(tmp_path: Path) -> None:
    """Chat detection works for all supported IDEs."""
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


# -----------------------------------------------------------------------------
# Launcher resolution
# -----------------------------------------------------------------------------


def test_resolve_launcher_tmux() -> None:
    """Resolve tmux backend."""
    launcher_key, ide = resolve_launcher("tmux")
    assert launcher_key == "tmux"
    assert ide is None


def test_resolve_launcher_neovim() -> None:
    """Resolve neovim backend."""
    launcher_key, ide = resolve_launcher("neovim")
    assert launcher_key == "neovim"
    assert ide is None


def test_resolve_launcher_nvim_alias() -> None:
    """Resolve nvim alias to neovim."""
    launcher_key, ide = resolve_launcher("nvim")
    assert launcher_key == "neovim"
    assert ide is None


def test_resolve_launcher_vscode() -> None:
    """Resolve vscode to ide launcher."""
    launcher_key, ide = resolve_launcher("vscode")
    assert launcher_key == "ide"
    assert ide == "vscode"


def test_resolve_launcher_cursor() -> None:
    """Resolve cursor to ide launcher."""
    launcher_key, ide = resolve_launcher("cursor")
    assert launcher_key == "ide"
    assert ide == "cursor"


def test_resolve_launcher_windsurf() -> None:
    """Resolve windsurf to ide launcher."""
    launcher_key, ide = resolve_launcher("windsurf")
    assert launcher_key == "ide"
    assert ide == "windsurf"


def test_resolve_launcher_kiro() -> None:
    """Resolve kiro to ide launcher."""
    launcher_key, ide = resolve_launcher("kiro")
    assert launcher_key == "ide"
    assert ide == "kiro"


def test_resolve_launcher_antigravity() -> None:
    """Resolve antigravity to ide launcher."""
    launcher_key, ide = resolve_launcher("antigravity")
    assert launcher_key == "ide"
    assert ide == "antigravity"


def test_resolve_launcher_unknown_fallback() -> None:
    """Unknown backend falls through to ide launcher."""
    launcher_key, ide = resolve_launcher("custom-ide")
    assert launcher_key == "ide"
    assert ide == "custom-ide"


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------


def test_copilot_chat_extension_id() -> None:
    """COPILOT_CHAT_EXTENSION_ID has expected value."""
    assert COPILOT_CHAT_EXTENSION_ID == "github.copilot-chat"
