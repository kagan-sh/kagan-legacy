"""Discriminated union types for agent backend configuration."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from pydantic import BaseModel, Field


class ClaudeAgentConfig(BaseModel):
    """Configuration for the Claude Code agent backend."""

    type: Literal["claude"] = "claude"
    model: str = "sonnet"
    allowed_tools: list[str] = Field(default_factory=list)


class OpenCodeAgentConfig(BaseModel):
    """Configuration for the OpenCode agent backend."""

    type: Literal["opencode"] = "opencode"
    model: str = "sonnet"


class CopilotAgentConfig(BaseModel):
    """Configuration for the GitHub Copilot agent backend."""

    type: Literal["copilot"] = "copilot"
    model: str = "claude-sonnet-4"


class GeminiAgentConfig(BaseModel):
    """Configuration for the Gemini CLI agent backend."""

    type: Literal["gemini"] = "gemini"
    model: str = "gemini-2.5-pro"


class KimiAgentConfig(BaseModel):
    """Configuration for the Kimi CLI agent backend."""

    type: Literal["kimi"] = "kimi"
    model: str = "kimi-k2"


class CodexAgentConfig(BaseModel):
    """Configuration for the Codex agent backend."""

    type: Literal["codex"] = "codex"
    model: str = "o3"


class GooseAgentConfig(BaseModel):
    """Configuration for the Goose (Block) agent backend."""

    type: Literal["goose"] = "goose"
    model: str = ""


class OpenHandsAgentConfig(BaseModel):
    """Configuration for the OpenHands agent backend."""

    type: Literal["openhands"] = "openhands"
    model: str = ""


class AuggieAgentConfig(BaseModel):
    """Configuration for the Auggie (Augment Code) agent backend."""

    type: Literal["auggie"] = "auggie"
    model: str = ""


class AmpAgentConfig(BaseModel):
    """Configuration for the Amp (AmpCode) agent backend."""

    type: Literal["amp"] = "amp"
    model: str = ""


class CagentAgentConfig(BaseModel):
    """Configuration for the Docker cagent backend."""

    type: Literal["cagent"] = "cagent"
    model: str = ""


class StakpakAgentConfig(BaseModel):
    """Configuration for the Stakpak agent backend."""

    type: Literal["stakpak"] = "stakpak"
    model: str = ""


class VibeAgentConfig(BaseModel):
    """Configuration for the Mistral Vibe agent backend."""

    type: Literal["vibe"] = "vibe"
    model: str = ""


class VTCodeAgentConfig(BaseModel):
    """Configuration for the VT Code agent backend."""

    type: Literal["vtcode"] = "vtcode"
    model: str = ""


AgentBackendConfig = Annotated[
    ClaudeAgentConfig
    | OpenCodeAgentConfig
    | CopilotAgentConfig
    | GeminiAgentConfig
    | KimiAgentConfig
    | CodexAgentConfig
    | GooseAgentConfig
    | OpenHandsAgentConfig
    | AuggieAgentConfig
    | AmpAgentConfig
    | CagentAgentConfig
    | StakpakAgentConfig
    | VibeAgentConfig
    | VTCodeAgentConfig,
    Field(discriminator="type"),
]

_BACKEND_CONFIG_CLASSES: tuple[type[BaseModel], ...] = (
    ClaudeAgentConfig,
    OpenCodeAgentConfig,
    CopilotAgentConfig,
    GeminiAgentConfig,
    KimiAgentConfig,
    CodexAgentConfig,
    GooseAgentConfig,
    OpenHandsAgentConfig,
    AuggieAgentConfig,
    AmpAgentConfig,
    CagentAgentConfig,
    StakpakAgentConfig,
    VibeAgentConfig,
    VTCodeAgentConfig,
)

BACKEND_CONFIG_DEFAULTS: dict[str, type[BaseModel]] = {
    str(config_cls.model_fields["type"].default): config_cls
    for config_cls in _BACKEND_CONFIG_CLASSES
}


def get_backend_config(agent_type: str) -> AgentBackendConfig:
    """Get the default backend config for a given agent type.

    Args:
        agent_type: The agent type identifier (e.g., 'claude', 'opencode').

    Returns:
        The default AgentBackendConfig for the given type.

    Raises:
        ValueError: If the agent type is unknown.
    """
    config_cls = BACKEND_CONFIG_DEFAULTS.get(agent_type)
    if config_cls is None:
        supported = ", ".join(sorted(BACKEND_CONFIG_DEFAULTS))
        raise ValueError(f"Unknown agent type: {agent_type!r}. Supported: {supported}")
    config = config_cls()
    if isinstance(config, _BACKEND_CONFIG_CLASSES):
        return cast("AgentBackendConfig", config)
    msg = f"Unexpected backend config type: {type(config).__name__}"
    raise TypeError(msg)


__all__ = [
    "BACKEND_CONFIG_DEFAULTS",
    "AgentBackendConfig",
    "AmpAgentConfig",
    "AuggieAgentConfig",
    "CagentAgentConfig",
    "ClaudeAgentConfig",
    "CodexAgentConfig",
    "CopilotAgentConfig",
    "GeminiAgentConfig",
    "GooseAgentConfig",
    "KimiAgentConfig",
    "OpenCodeAgentConfig",
    "OpenHandsAgentConfig",
    "StakpakAgentConfig",
    "VTCodeAgentConfig",
    "VibeAgentConfig",
    "get_backend_config",
]
