"""Built-in agent definitions for Kagan."""

from __future__ import annotations

from dataclasses import dataclass

from kagan.config import AgentConfig


@dataclass
class BuiltinAgent:
    """Extended agent info with metadata for welcome screen."""

    config: AgentConfig
    author: str
    description: str
    install_command: str
    mcp_config_file: str = ".mcp.json"  # Filename for MCP config
    mcp_config_format: str = "claude"  # Format: "claude" | "opencode"


# Built-in agents that ship with Kagan
# run_command: ACP protocol command for AUTO mode (programmatic)
# interactive_command: CLI command for PAIR mode (interactive tmux session)
# NOTE: Only OpenCode and Claude Code are supported. Other CLI tools removed.
#
# MCP config formats:
# - claude: Uses .mcp.json with {"mcpServers": {"name": {"command": ..., "args": [...]}}}
# - opencode: Uses opencode.json with {"mcp": {"name": {"type": "local", "command": [...]}}}
BUILTIN_AGENTS: dict[str, BuiltinAgent] = {
    "claude": BuiltinAgent(
        config=AgentConfig(
            identity="claude.com",
            name="Claude Code",
            short_name="claude",
            run_command={"*": "npx claude-code-acp"},
            interactive_command={"*": "claude"},
            active=True,
        ),
        author="Anthropic",
        description="Agentic AI for coding tasks",
        install_command="curl -fsSL https://claude.ai/install.sh | bash",
        mcp_config_file=".mcp.json",
        mcp_config_format="claude",
    ),
    "opencode": BuiltinAgent(
        config=AgentConfig(
            identity="opencode.ai",
            name="OpenCode",
            short_name="opencode",
            run_command={"*": "opencode acp"},
            interactive_command={"*": "opencode"},
            active=True,
        ),
        author="SST",
        description="Multi-model CLI with TUI",
        install_command="npm i -g opencode-ai",
        mcp_config_file="opencode.json",
        mcp_config_format="opencode",
    ),
}


def get_builtin_agent(name: str) -> BuiltinAgent | None:
    """Get a built-in agent by short name.

    Args:
        name: The short name of the agent (e.g., 'claude', 'opencode').

    Returns:
        The BuiltinAgent if found, None otherwise.
    """
    return BUILTIN_AGENTS.get(name)


def list_builtin_agents() -> list[BuiltinAgent]:
    """Get all built-in agents.

    Returns:
        A list of all BuiltinAgent objects.
    """
    return list(BUILTIN_AGENTS.values())
