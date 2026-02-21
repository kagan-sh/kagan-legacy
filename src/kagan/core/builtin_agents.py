"""Built-in agent definitions for Kagan."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from kagan.core.agents.backend_config import (
    AgentBackendConfig,
    AmpAgentConfig,
    AuggieAgentConfig,
    CagentAgentConfig,
    ClaudeAgentConfig,
    CodexAgentConfig,
    CopilotAgentConfig,
    GeminiAgentConfig,
    GooseAgentConfig,
    KimiAgentConfig,
    OpenCodeAgentConfig,
    OpenHandsAgentConfig,
    StakpakAgentConfig,
    VibeAgentConfig,
    VTCodeAgentConfig,
)
from kagan.core.command_utils import split_command_string
from kagan.core.config import AgentConfig, get_os_value


@dataclass
class BuiltinAgent:
    """Extended agent info with metadata for welcome screen."""

    config: AgentConfig
    author: str
    description: str
    install_command: str
    docs_url: str = ""
    mcp_config_file: str = ".mcp.json"
    mcp_config_format: str = "claude"
    backend_config: AgentBackendConfig = field(default_factory=ClaudeAgentConfig)


@dataclass
class AgentAvailability:
    """Availability status for an agent."""

    agent: BuiltinAgent
    interactive_available: bool = False
    acp_available: bool = False

    @property
    def is_available(self) -> bool:
        """Check if agent is available in any mode."""
        return self.interactive_available or self.acp_available

    @property
    def install_hint(self) -> str:
        """Get one-liner install instruction."""
        return self.agent.install_command

    @property
    def docs_url(self) -> str:
        """Get documentation URL."""
        return self.agent.docs_url


AGENT_PRIORITY = [
    "claude",
    "opencode",
    "codex",
    "gemini",
    "kimi",
    "copilot",
    "goose",
    "openhands",
    "auggie",
    "amp",
    "cagent",
    "stakpak",
    "vibe",
    "vtcode",
]

BUILTIN_AGENTS: dict[str, BuiltinAgent] = {
    "claude": BuiltinAgent(
        config=AgentConfig(
            identity="claude.com",
            name="Claude Code",
            short_name="claude",
            run_command={"*": "npx claude-code-acp"},
            interactive_command={"*": "claude"},
            active=True,
            model_env_var="ANTHROPIC_MODEL",
        ),
        author="Anthropic",
        description="Agentic AI for coding tasks",
        install_command="curl -fsSL https://claude.ai/install.sh | bash",
        docs_url="https://docs.anthropic.com/en/docs/claude-code",
        mcp_config_file=".mcp.json",
        mcp_config_format="claude",
        backend_config=ClaudeAgentConfig(),
    ),
    "opencode": BuiltinAgent(
        config=AgentConfig(
            identity="opencode.ai",
            name="OpenCode",
            short_name="opencode",
            run_command={"*": "opencode acp"},
            interactive_command={"*": "opencode"},
            active=True,
            model_env_var="",
        ),
        author="SST",
        description="Multi-model CLI with TUI",
        install_command="npm i -g opencode-ai",
        docs_url="https://opencode.ai/docs",
        mcp_config_file="opencode.json",
        mcp_config_format="opencode",
        backend_config=OpenCodeAgentConfig(),
    ),
    "codex": BuiltinAgent(
        config=AgentConfig(
            identity="codex.openai.com",
            name="Codex",
            short_name="codex",
            run_command={"*": "npx @zed-industries/codex-acp"},
            interactive_command={"*": "codex"},
            active=True,
            model_env_var="",
        ),
        author="OpenAI",
        description="OpenAI CLI coding agent",
        install_command="npm install -g @openai/codex",
        docs_url="https://github.com/openai/codex",
        backend_config=CodexAgentConfig(),
    ),
    "gemini": BuiltinAgent(
        config=AgentConfig(
            identity="gemini.google.com",
            name="Gemini CLI",
            short_name="gemini",
            run_command={"*": "gemini --experimental-acp"},
            interactive_command={"*": "gemini"},
            active=True,
            model_env_var="",
        ),
        author="Google",
        description="Google Gemini CLI agent",
        install_command="npm install -g @google/gemini-cli",
        docs_url="https://github.com/google-gemini/gemini-cli",
        backend_config=GeminiAgentConfig(),
    ),
    "kimi": BuiltinAgent(
        config=AgentConfig(
            identity="kimi.moonshot.cn",
            name="Kimi CLI",
            short_name="kimi",
            run_command={"*": "kimi acp"},
            interactive_command={"*": "kimi"},
            active=True,
            model_env_var="",
        ),
        author="Moonshot AI",
        description="Kimi CLI coding agent",
        install_command="uv tool install kimi-cli --no-cache",
        docs_url="https://github.com/MoonshotAI/kimi-cli",
        backend_config=KimiAgentConfig(),
    ),
    "copilot": BuiltinAgent(
        config=AgentConfig(
            identity="copilot.github.com",
            name="GitHub Copilot",
            short_name="copilot",
            run_command={"*": "copilot --acp"},
            interactive_command={"*": "copilot"},
            active=True,
            model_env_var="",
        ),
        author="GitHub",
        description="GitHub Copilot CLI agent",
        install_command="npm install -g @github/copilot@prerelease",
        docs_url="https://github.com/github/copilot-cli",
        mcp_config_file=".mcp.json",
        mcp_config_format="claude",
        backend_config=CopilotAgentConfig(),
    ),
    "goose": BuiltinAgent(
        config=AgentConfig(
            identity="goose.ai",
            name="Goose",
            short_name="goose",
            run_command={"*": "goose acp"},
            interactive_command={"*": "goose"},
            active=True,
            model_env_var="GOOSE_MODEL",
        ),
        author="Block",
        description="Open-source, extensible AI agent that goes beyond code suggestions",
        install_command=(
            "curl -fsSL https://github.com/block/goose/releases/download/stable"
            "/download_cli.sh | bash"
        ),
        docs_url="https://block.github.io/goose/",
        backend_config=GooseAgentConfig(),
    ),
    "openhands": BuiltinAgent(
        config=AgentConfig(
            identity="openhands.dev",
            name="OpenHands",
            short_name="openhands",
            run_command={"*": "openhands acp"},
            interactive_command={"*": "openhands"},
            active=True,
            model_env_var="",
        ),
        author="OpenHands",
        description="Open platform for cloud coding agents, model-agnostic and enterprise-ready",
        install_command="uv tool install openhands -U --python 3.12",
        docs_url="https://openhands.dev/",
        backend_config=OpenHandsAgentConfig(),
    ),
    "auggie": BuiltinAgent(
        config=AgentConfig(
            identity="augmentcode.com",
            name="Auggie",
            short_name="auggie",
            run_command={"*": "auggie --acp"},
            interactive_command={"*": "auggie"},
            active=True,
            model_env_var="",
        ),
        author="Augment Code",
        description="AI agent with ACP support for terminal and editor integration",
        install_command="npm install -g @augmentcode/auggie",
        docs_url="https://docs.augmentcode.com/cli/setup-auggie/install-auggie-cli",
        backend_config=AuggieAgentConfig(),
    ),
    "amp": BuiltinAgent(
        config=AgentConfig(
            identity="ampcode.com",
            name="Amp",
            short_name="amp",
            run_command={"*": "npx -y amp-acp"},
            interactive_command={"*": "amp"},
            active=True,
            model_env_var="",
        ),
        author="Sourcegraph",
        description="Frontier coding agent for the terminal built by Sourcegraph",
        install_command="curl -fsSL https://ampcode.com/install.sh | bash",
        docs_url="https://ampcode.com",
        backend_config=AmpAgentConfig(),
    ),
    "cagent": BuiltinAgent(
        config=AgentConfig(
            identity="docker.com",
            name="Docker cagent",
            short_name="cagent",
            run_command={"*": "cagent acp"},
            interactive_command={"*": "cagent"},
            active=True,
            model_env_var="",
        ),
        author="Docker",
        description="Agent Builder and Runtime by Docker Engineering with MCP and ACP support",
        install_command="Install Docker Desktop 4.49+ which includes cagent: https://www.docker.com/products/docker-desktop/",
        docs_url="https://docs.docker.com/ai/cagent/",
        backend_config=CagentAgentConfig(),
    ),
    "stakpak": BuiltinAgent(
        config=AgentConfig(
            identity="stakpak.dev",
            name="Stakpak",
            short_name="stakpak",
            run_command={"*": "stakpak acp"},
            interactive_command={"*": "stakpak"},
            active=True,
            model_env_var="",
        ),
        author="Stakpak",
        description="Terminal-native DevOps Agent in Rust with enterprise-grade security",
        install_command="cargo install stakpak",
        docs_url="https://stakpak.dev/",
        backend_config=StakpakAgentConfig(),
    ),
    "vibe": BuiltinAgent(
        config=AgentConfig(
            identity="vibe.mistral.ai",
            name="Mistral Vibe",
            short_name="vibe",
            run_command={"*": "vibe-acp"},
            interactive_command={"*": "vibe"},
            active=True,
            model_env_var="",
        ),
        author="Mistral",
        description="State-of-the-art open-source agentic coding CLI backed by Devstral models",
        install_command="curl -LsSf https://mistral.ai/vibe/install.sh | bash",
        docs_url="https://mistral.ai/news/devstral-2-vibe-cli",
        backend_config=VibeAgentConfig(),
    ),
    "vtcode": BuiltinAgent(
        config=AgentConfig(
            identity="vtcode.dev",
            name="VT Code",
            short_name="vtcode",
            run_command={"*": "vtcode acp"},
            interactive_command={"*": "vtcode"},
            active=True,
            model_env_var="",
        ),
        author="Vinh Nguyen",
        description="Rust-based terminal coding agent with semantic code intelligence",
        install_command="cargo install --git https://github.com/vinhnx/vtcode",
        docs_url="https://github.com/vinhnx/vtcode",
        backend_config=VTCodeAgentConfig(),
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


def _check_command_available(command: str | None) -> bool:
    """Check if a command's executable is available in PATH."""
    if not command:
        return False

    try:
        parts = split_command_string(command)
        executable = parts[0] if parts else command
    except ValueError:
        return shutil.which(command) is not None

    if executable == "npx" and len(parts) > 1:
        package = parts[1]

        binary = package.split("/")[-1] if "/" in package else package

        # npx can run packages on demand, but we can't verify that without running it
        return shutil.which(binary) is not None

    return shutil.which(executable) is not None


def check_agent_availability(agent: BuiltinAgent) -> AgentAvailability:
    """Check if an agent's commands are available in PATH.

    Args:
        agent: The BuiltinAgent to check.

    Returns:
        AgentAvailability with status for both interactive and ACP modes.
    """
    interactive_cmd = get_os_value(agent.config.interactive_command)
    acp_cmd = get_os_value(agent.config.run_command)

    return AgentAvailability(
        agent=agent,
        interactive_available=_check_command_available(interactive_cmd),
        acp_available=_check_command_available(acp_cmd),
    )


def get_all_agent_availability() -> list[AgentAvailability]:
    """Get availability status for all built-in agents.

    Returns agents in priority order (claude first, then opencode).

    Returns:
        List of AgentAvailability for all agents in priority order.
    """
    result = []
    for key in AGENT_PRIORITY:
        if agent := BUILTIN_AGENTS.get(key):
            result.append(check_agent_availability(agent))
    return result


def get_first_available_agent() -> BuiltinAgent | None:
    """Get the first available agent based on priority.

    Priority: claude > opencode

    Returns:
        The first available BuiltinAgent, or None if none available.
    """
    for availability in get_all_agent_availability():
        if availability.is_available:
            return availability.agent
    return None


def any_agent_available() -> bool:
    """Check if any agent is available.

    Returns:
        True if at least one agent is available.
    """
    return any(a.is_available for a in get_all_agent_availability())


def list_available_agents() -> list[BuiltinAgent]:
    """Return list of agents that are currently installed.

    Checks if each agent's interactive command executable is available in PATH.

    Returns:
        List of BuiltinAgent objects for agents that are installed.
    """
    available = []
    for availability in get_all_agent_availability():
        if availability.is_available:
            available.append(availability.agent)
    return available


def get_agent_status() -> dict[str, bool]:
    """Return availability status for all agents.

    Returns:
        Dictionary mapping agent short_name to availability boolean.
        Example: {"claude": True, "opencode": False, "codex": False, ...}
    """
    return {
        agent.config.short_name: availability.is_available
        for agent in BUILTIN_AGENTS.values()
        if (availability := check_agent_availability(agent))
    }
