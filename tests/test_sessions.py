"""Tests for SessionManager with mock tmux."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

import pytest

from kagan.config import KaganConfig
from kagan.database.models import TicketCreate
from kagan.sessions.manager import SessionManager


@pytest.fixture
def mock_tmux(monkeypatch):
    """Intercept tmux subprocess calls."""
    sessions: dict[str, dict[str, Any]] = {}

    async def fake_run_tmux(*args: str) -> str:
        command = args[0]
        if command == "new-session":
            name = args[args.index("-s") + 1]
            cwd = args[args.index("-c") + 1]
            env: dict[str, str] = {}
            for idx, value in enumerate(args):
                if value == "-e" and idx + 1 < len(args):
                    key, _, env_value = args[idx + 1].partition("=")
                    env[key] = env_value
            sessions[name] = {"cwd": cwd, "env": env, "sent_keys": []}
            return ""
        if command == "send-keys":
            name = args[args.index("-t") + 1]
            # Capture the text sent (args after -t name, excluding "Enter")
            key_text = args[args.index("-t") + 2]
            if name in sessions:
                sessions[name]["sent_keys"].append(key_text)
            return ""
        if command == "list-sessions":
            return "\n".join(sorted(sessions.keys()))
        if command == "kill-session":
            name = args[args.index("-t") + 1]
            sessions.pop(name, None)
            return ""
        return ""

    monkeypatch.setattr("kagan.sessions.manager.run_tmux", fake_run_tmux)
    return sessions


class TestSessionManager:
    """Session manager behavior tests."""

    async def test_create_session_writes_mcp_config(self, state_manager, mock_tmux, tmp_path: Path):
        """Test that session creation writes MCP config and sets up environment."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Add login",
                description="Implement OAuth",
                acceptance_criteria=["Tests pass"],
            )
        )
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        session_name = await manager.create_session(ticket, worktree_path)

        assert session_name in mock_tmux
        env = mock_tmux[session_name]["env"]
        assert env["KAGAN_TICKET_ID"] == ticket.id
        assert env["KAGAN_TICKET_TITLE"] == ticket.title
        assert env["KAGAN_WORKTREE_PATH"] == str(worktree_path)
        assert env["KAGAN_PROJECT_ROOT"] == str(project_root)

        # Check .mcp.json is created for default (Claude) agent
        mcp_config_path = worktree_path / ".mcp.json"
        assert mcp_config_path.exists()
        import json

        mcp_config = json.loads(mcp_config_path.read_text())
        assert "mcpServers" in mcp_config
        assert "kagan" in mcp_config["mcpServers"]
        assert mcp_config["mcpServers"]["kagan"]["command"] == "kagan"
        assert mcp_config["mcpServers"]["kagan"]["args"] == ["mcp"]

        # No CONTEXT.md, CLAUDE.md, or AGENTS.md symlink created anymore
        # (worktree already has user's files from git clone, context via MCP tool)
        assert not (worktree_path / ".kagan-context").exists()

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.session_active is True

    async def test_create_session_opencode_mcp_config(
        self, state_manager, mock_tmux, tmp_path: Path
    ):
        """Test that OpenCode agent gets opencode.json MCP config format."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        ticket = await state_manager.create_ticket(
            TicketCreate(title="OpenCode task", agent_backend="opencode")
        )
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)

        # Check opencode.json is created instead of .mcp.json
        assert not (worktree_path / ".mcp.json").exists()
        opencode_config_path = worktree_path / "opencode.json"
        assert opencode_config_path.exists()

        import json

        opencode_config = json.loads(opencode_config_path.read_text())
        assert "$schema" in opencode_config
        assert opencode_config["$schema"] == "https://opencode.ai/config.json"
        assert "mcp" in opencode_config
        assert "kagan" in opencode_config["mcp"]
        assert opencode_config["mcp"]["kagan"]["type"] == "local"
        assert opencode_config["mcp"]["kagan"]["command"] == ["kagan", "mcp"]
        assert opencode_config["mcp"]["kagan"]["enabled"] is True

    async def test_create_session_merges_existing_mcp_config(
        self, state_manager, mock_tmux, tmp_path: Path
    ):
        """Test that existing MCP config is merged, not overwritten."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        import json

        # Create existing .mcp.json with user's servers
        existing_config = {
            "mcpServers": {"my-server": {"command": "my-mcp", "args": ["--port", "8080"]}}
        }
        (worktree_path / ".mcp.json").write_text(json.dumps(existing_config))

        ticket = await state_manager.create_ticket(TicketCreate(title="Task"))
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)

        merged_config = json.loads((worktree_path / ".mcp.json").read_text())
        # Original server preserved
        assert "my-server" in merged_config["mcpServers"]
        assert merged_config["mcpServers"]["my-server"]["command"] == "my-mcp"
        # Kagan server added
        assert "kagan" in merged_config["mcpServers"]
        assert merged_config["mcpServers"]["kagan"]["command"] == "kagan"

    async def test_create_session_sends_startup_prompt(
        self, state_manager, mock_tmux, tmp_path: Path
    ):
        """Test that startup prompt is embedded in launch command."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        ticket = await state_manager.create_ticket(
            TicketCreate(title="Test task", description="Do something useful")
        )
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)

        # Check that send-keys was called with launch command containing prompt
        session_name = f"kagan-{ticket.id}"
        assert session_name in mock_tmux
        sent_keys = mock_tmux[session_name].get("sent_keys", [])
        # Should have single launch command with embedded prompt
        assert len(sent_keys) >= 1
        launch_cmd = sent_keys[0]  # Launch command includes the prompt
        assert ticket.id in launch_cmd
        assert "Test task" in launch_cmd
        assert "kagan_get_context" in launch_cmd
        # Should start with claude (default agent)
        assert launch_cmd.startswith("claude ")

    async def test_session_exists_and_kill(self, state_manager, mock_tmux, tmp_path: Path):
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        ticket = await state_manager.create_ticket(TicketCreate(title="Work"))
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)
        assert await manager.session_exists(ticket.id) is True

        await manager.kill_session(ticket.id)
        assert await manager.session_exists(ticket.id) is False

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.session_active is False

    async def test_create_session_writes_gitignore(self, state_manager, mock_tmux, tmp_path: Path):
        """Test that worktree .gitignore is created with MCP config entry."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        ticket = await state_manager.create_ticket(TicketCreate(title="Task"))
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)

        gitignore = worktree_path / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        # Only the MCP config file is gitignored now
        assert ".mcp.json" in content
        # These are no longer generated, so not gitignored
        assert ".kagan-context/" not in content
        assert "CLAUDE.md" not in content

    async def test_create_session_appends_to_existing_gitignore(
        self, state_manager, mock_tmux, tmp_path: Path
    ):
        """Test that existing .gitignore is preserved and appended to."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        # Create existing .gitignore
        existing_content = "node_modules/\n*.pyc\n"
        (worktree_path / ".gitignore").write_text(existing_content)

        ticket = await state_manager.create_ticket(TicketCreate(title="Task"))
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)

        content = (worktree_path / ".gitignore").read_text()
        # Original content preserved
        assert "node_modules/" in content
        assert "*.pyc" in content
        # MCP config entry added
        assert ".mcp.json" in content

    async def test_create_session_skips_duplicate_gitignore_entries(
        self, state_manager, mock_tmux, tmp_path: Path
    ):
        """Test that MCP config entry is not duplicated in .gitignore."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        # Create .gitignore with MCP config already present
        existing_content = ".mcp.json\n"
        (worktree_path / ".gitignore").write_text(existing_content)

        ticket = await state_manager.create_ticket(TicketCreate(title="Task"))
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)

        content = (worktree_path / ".gitignore").read_text()
        # Should not have duplicates - content should be unchanged
        assert content == existing_content
