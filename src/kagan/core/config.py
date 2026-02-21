"""Configuration loader for Kagan."""

from __future__ import annotations

import asyncio
import os
import platform
import tempfile
import tomllib
from typing import TYPE_CHECKING, Literal

import tomlkit
from pydantic import BaseModel, Field, field_validator, model_validator

from kagan.core.domain.pair_terminal_backends import (
    PAIR_TERMINAL_BACKEND_VALUE_SET,
    PairTerminalBackendLiteral,
    default_pair_terminal_backend_for_os,
)
from kagan.core.paths import ensure_directories, get_config_path
from kagan.core.settings_bounds import (
    DEFAULT_MAX_CONCURRENT_AGENTS,
    coerce_max_concurrent_agents,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    """Write file atomically to avoid partial/corrupt writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        Path(tmp_path).replace(path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


type OS = Literal["linux", "macos", "windows", "*"]
type DoctorVerbosityLiteral = Literal[
    "tldr",
    "short",
    "technical",
]
type InteractionVerbosityLiteral = Literal[
    "tldr",
    "short",
    "technical",
]
type WorktreeBaseRefStrategyLiteral = Literal[
    "remote",
    "local_if_ahead",
    "local",
]

_OS_MAP = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}
CURRENT_OS: str = _OS_MAP.get(platform.system(), "linux")
PAIR_TERMINAL_BACKEND_VALUES = PAIR_TERMINAL_BACKEND_VALUE_SET
DOCTOR_VERBOSITY_VALUES = frozenset({"tldr", "short", "technical"})
INTERACTION_VERBOSITY_VALUES = frozenset({"tldr", "short", "technical"})
WORKTREE_BASE_REF_STRATEGY_VALUES = frozenset({"remote", "local_if_ahead", "local"})
DEFAULT_WORKER_PERSONA = (
    "Implementer: ship the smallest correct change, verify with tests, "
    "and keep commits clean and auditable."
)
DEFAULT_ORCHESTRATOR_PERSONA = (
    "Orchestrator: clarify intent, plan concrete tasks, and communicate decisions concisely."
)
DEFAULT_PR_REVIEWER_PERSONA = (
    "PR Reviewer: validate requirements, correctness, regressions, and tests; "
    "reject when evidence is insufficient."
)


def _default_pair_terminal_backend() -> PairTerminalBackendLiteral:
    return default_pair_terminal_backend_for_os(CURRENT_OS)


def get_os_value[T](matrix: Mapping[str, T]) -> T | None:
    """Get OS-specific value with wildcard fallback.

    Args:
        matrix: Dict mapping OS names to values (e.g., {"macos": "cmd1", "*": "cmd2"})

    Returns:
        The value for the current OS, or the wildcard "*" value, or None.
    """
    return matrix.get(CURRENT_OS) or matrix.get("*")


class RefinementConfig(BaseModel):
    """Configuration for prompt refinement."""

    enabled: bool = Field(default=True, description="Enable prompt refinement feature")
    hotkey: str = Field(default="f2", description="Hotkey to trigger refinement")
    skip_length_under: int = Field(default=20, description="Skip refinement for short inputs")
    skip_prefixes: list[str] = Field(
        default_factory=lambda: ["/", "!", "?"],
        description="Prefixes that skip refinement (commands, quick questions)",
    )


class GeneralConfig(BaseModel):
    """General configuration settings."""

    max_concurrent_agents: int = Field(default=DEFAULT_MAX_CONCURRENT_AGENTS)
    mcp_server_name: str = Field(
        default="kagan",
        description="MCP server name for tool registration and config entries",
    )
    worktree_base_ref_strategy: WorktreeBaseRefStrategyLiteral = Field(
        default="local_if_ahead",
        description=("Worktree base ref preference: local_if_ahead (default), remote, or local"),
    )
    auto_review: bool = Field(default=True, description="Run AI review on task completion")
    auto_approve: bool = Field(
        default=True,
        description="Skip permission prompts in the planner agent (workers always auto-approve)",
    )
    auto_commit_changes: bool = Field(
        default=False,
        description="Allow automation to auto-commit changes and push linked task branches",
    )
    auto_skill_discovery: bool = Field(
        default=False,
        description=(
            "Discover local Agent Skills metadata for orchestrator chat commands. "
            "Disabled by default for security."
        ),
    )
    require_review_approval: bool = Field(
        default=False, description="Require approved review before merge actions"
    )
    serialize_merges: bool = Field(
        default=True, description="Serialize manual merges to reduce conflicts"
    )
    default_worker_agent: str = Field(default="claude")
    worker_persona: str = Field(
        default=DEFAULT_WORKER_PERSONA,
        description="Global persona preset applied to AUTO worker task runs",
    )
    orchestrator_persona: str = Field(
        default=DEFAULT_ORCHESTRATOR_PERSONA,
        description="Global persona preset applied to orchestrator/planning chat behavior",
    )
    pr_reviewer_persona: str = Field(
        default=DEFAULT_PR_REVIEWER_PERSONA,
        description="Global persona preset applied to PR review agents",
    )
    default_pair_terminal_backend: PairTerminalBackendLiteral = Field(
        default_factory=_default_pair_terminal_backend,
        description="Default terminal backend for PAIR tasks",
    )
    doctor_verbosity: DoctorVerbosityLiteral = Field(
        default="short",
        description="Default verbosity for doctor diagnostics output",
    )
    interaction_verbosity: InteractionVerbosityLiteral = Field(
        default="short",
        description="Default verbosity for user-facing TUI interaction messages",
    )
    default_model_claude: str | None = Field(
        default=None, description="Default Claude model alias or full name (None = agent default)"
    )
    default_model_opencode: str | None = Field(
        default=None, description="Default OpenCode model (None = agent default)"
    )
    default_model_codex: str | None = Field(
        default=None, description="Default Codex model (None = agent default)"
    )
    default_model_gemini: str | None = Field(
        default=None, description="Default Gemini model (None = agent default)"
    )
    default_model_kimi: str | None = Field(
        default=None, description="Default Kimi model (None = agent default)"
    )
    default_model_copilot: str | None = Field(
        default=None,
        description="Preferred Copilot model label for display (runtime set via /model)",
    )
    default_model_goose: str | None = Field(
        default=None,
        description="Default Goose model passed via GOOSE_MODEL (None = agent default)",
    )
    default_model_openhands: str | None = Field(
        default=None, description="Default OpenHands model (None = agent default)"
    )
    default_model_auggie: str | None = Field(
        default=None, description="Default Auggie model (None = agent default)"
    )
    default_model_amp: str | None = Field(
        default=None, description="Default Amp model (None = agent default)"
    )
    default_model_cagent: str | None = Field(
        default=None, description="Default Docker cagent model (None = agent default)"
    )
    default_model_stakpak: str | None = Field(
        default=None, description="Default Stakpak model (None = agent default)"
    )
    default_model_vibe: str | None = Field(
        default=None, description="Default Mistral Vibe model (None = agent default)"
    )
    default_model_vtcode: str | None = Field(
        default=None, description="Default VT Code model (None = agent default)"
    )

    @field_validator("max_concurrent_agents", mode="before")
    @classmethod
    def validate_max_concurrent_agents(cls, value: object) -> int:
        """Gracefully coerce invalid max-concurrency values to default."""
        return coerce_max_concurrent_agents(value)

    # Core process settings
    core_idle_timeout_seconds: int = Field(
        default=180,
        description="Seconds with no connected clients before the core process shuts down",
    )
    core_autostart: bool = Field(
        default=True,
        description="Automatically start the core process when a client connects",
    )
    core_transport_preference: str = Field(
        default="auto",
        description="IPC transport preference: auto|socket|tcp",
    )
    tasks_wait_default_timeout_seconds: int = Field(
        default=1800,
        description="Default timeout in seconds for tasks_wait long-poll (30 minutes)",
    )
    tasks_wait_max_timeout_seconds: int = Field(
        default=3600,
        description="Maximum allowed timeout in seconds for tasks_wait long-poll (60 minutes)",
    )

    @field_validator("worktree_base_ref_strategy", mode="before")
    @classmethod
    def validate_worktree_base_ref_strategy(cls, value: object) -> str:
        """Gracefully coerce invalid base-ref strategy values to local_if_ahead."""
        match value:
            case str() as strategy if strategy in WORKTREE_BASE_REF_STRATEGY_VALUES:
                return strategy
            case _:
                pass
        return "local_if_ahead"

    @field_validator("default_pair_terminal_backend", mode="before")
    @classmethod
    def validate_default_pair_terminal_backend(cls, value: object) -> str:
        """Gracefully coerce invalid values to platform default."""
        match value:
            case str() as backend if backend in PAIR_TERMINAL_BACKEND_VALUES:
                return backend
            case _:
                pass
        return _default_pair_terminal_backend()

    @field_validator("doctor_verbosity", mode="before")
    @classmethod
    def validate_doctor_verbosity(cls, value: object) -> str:
        """Gracefully coerce invalid doctor verbosity values to short."""
        match value:
            case str() as verbosity:
                normalized = verbosity.strip().lower()
                if normalized in DOCTOR_VERBOSITY_VALUES:
                    return normalized
            case _:
                pass
        return "short"

    @field_validator("interaction_verbosity", mode="before")
    @classmethod
    def validate_interaction_verbosity(cls, value: object) -> str:
        """Gracefully coerce invalid interaction verbosity values to short."""
        match value:
            case str() as verbosity:
                normalized = verbosity.strip().lower()
                if normalized in INTERACTION_VERBOSITY_VALUES:
                    return normalized
            case _:
                pass
        return "short"

    @field_validator("worker_persona", mode="before")
    @classmethod
    def validate_worker_persona(cls, value: object) -> str:
        """Coerce empty worker persona values to default preset."""
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
        return DEFAULT_WORKER_PERSONA

    @field_validator("orchestrator_persona", mode="before")
    @classmethod
    def validate_orchestrator_persona(cls, value: object) -> str:
        """Coerce empty orchestrator persona values to default preset."""
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
        return DEFAULT_ORCHESTRATOR_PERSONA

    @field_validator("pr_reviewer_persona", mode="before")
    @classmethod
    def validate_pr_reviewer_persona(cls, value: object) -> str:
        """Coerce empty PR reviewer persona values to default preset."""
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
        return DEFAULT_PR_REVIEWER_PERSONA

    @field_validator("core_transport_preference", mode="before")
    @classmethod
    def validate_core_transport_preference(cls, value: object) -> str:
        """Coerce invalid transport values to 'auto'."""
        valid = {"auto", "socket", "tcp"}
        match value:
            case str() as transport if transport in valid:
                return transport
            case _:
                pass
        return "auto"

    @model_validator(mode="after")
    def validate_tasks_wait_bounds(self) -> GeneralConfig:
        """Ensure task wait timeouts are positive and ordered."""
        if self.tasks_wait_default_timeout_seconds <= 0:
            msg = "general.tasks_wait_default_timeout_seconds must be > 0"
            raise ValueError(msg)
        if self.tasks_wait_max_timeout_seconds <= 0:
            msg = "general.tasks_wait_max_timeout_seconds must be > 0"
            raise ValueError(msg)
        if self.tasks_wait_max_timeout_seconds < self.tasks_wait_default_timeout_seconds:
            msg = (
                "general.tasks_wait_max_timeout_seconds must be >= "
                "general.tasks_wait_default_timeout_seconds"
            )
            raise ValueError(msg)
        return self


class UIConfig(BaseModel):
    """UI-related user preferences."""

    skip_pair_instructions: bool = Field(
        default=False,
        description="Skip pair mode instructions popup when opening PAIR sessions",
    )
    theme: str | None = Field(
        default=None,
        description=(
            "Persisted Textual theme name (e.g. 'kagan', 'dracula', 'tokyo-night'). "
            "None means auto-detect based on terminal capabilities."
        ),
    )
    show_beginner_hints: bool = Field(
        default=True,
        description="Show beginner quick-start hints and first-empty-board guidance in the TUI",
    )
    tui_plugin_ui_allowlist: list[str] = Field(
        default_factory=list,
        description=(
            "Allowlisted plugin IDs that may contribute declarative UI definitions to the TUI. "
            "Empty list means all registered plugins are allowed."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_skip_tmux_gateway(cls, data: object) -> object:
        match data:
            case dict() as mapping:
                if "skip_pair_instructions" in mapping:
                    return data
                if "skip_tmux_gateway" in mapping:
                    migrated = dict(mapping)
                    migrated["skip_pair_instructions"] = migrated["skip_tmux_gateway"]
                    return migrated
                return data
            case _:
                return data


class AgentConfig(BaseModel):
    """Configuration for an ACP agent."""

    identity: str = Field(..., description="Unique identifier (e.g., 'claude.com')")
    name: str = Field(..., description="Display name (e.g., 'Claude Code')")
    short_name: str = Field(..., description="CLI alias (e.g., 'claude')")
    protocol: Literal["acp"] = Field(default="acp", description="Protocol type")
    run_command: dict[str, str] = Field(
        default_factory=dict,
        description="OS-specific ACP commands for AUTO mode (e.g., 'npx claude-code-acp')",
    )
    interactive_command: dict[str, str] = Field(
        default_factory=dict,
        description="OS-specific CLI commands for PAIR mode (e.g., 'claude')",
    )
    active: bool = Field(default=True, description="Whether this agent is active")
    model_env_var: str = Field(default="", description="Environment variable for model selection")


class PluginsConfig(BaseModel):
    """Plugin discovery configuration."""

    discovery: list[str] = Field(
        default_factory=lambda: [
            "kagan.core.plugins.github.plugin:GitHubPlugin",
        ],
        description="Plugin entrypoints to discover and register (module:Class format).",
    )


class KaganConfig(BaseModel):
    """Root configuration model."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    refinement: RefinementConfig = Field(default_factory=RefinementConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> KaganConfig:
        """Load configuration from TOML file or use defaults."""
        ensure_directories()
        if config_path is None:
            config_path = get_config_path()

        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            return cls.model_validate(data)

        return cls()

    def get_agent(self, name: str) -> AgentConfig | None:
        """Get agent configuration by name."""
        return self.agents.get(name)

    def get_worker_agent(self) -> AgentConfig | None:
        """Get the configured worker agent."""
        return self.get_agent(self.general.default_worker_agent)

    async def save(self, path: Path) -> None:
        """Serialize current config to TOML file.

        Args:
            path: Path to write config file (created if missing)
        """
        doc = tomlkit.document()

        general_table = tomlkit.table()
        for key, value in self.general.model_dump().items():
            if value is not None:
                general_table[key] = value
        doc["general"] = general_table

        if self.agents:
            agents_table = tomlkit.table()
            for agent_name, agent_cfg in self.agents.items():
                agent_table = tomlkit.table()
                for key, value in agent_cfg.model_dump().items():
                    if value is not None and value != {}:
                        agent_table[key] = value
                agents_table[agent_name] = agent_table
            doc["agents"] = agents_table

        refinement_table = tomlkit.table()
        for key, value in self.refinement.model_dump().items():
            if value is not None:
                refinement_table[key] = value
        doc["refinement"] = refinement_table

        ui_table = tomlkit.table()
        for key, value in self.ui.model_dump().items():
            if value is not None:
                ui_table[key] = value
        doc["ui"] = ui_table

        plugins_table = tomlkit.table()
        for key, value in self.plugins.model_dump().items():
            if value is not None:
                plugins_table[key] = value
        doc["plugins"] = plugins_table

        content = tomlkit.dumps(doc)
        await asyncio.to_thread(atomic_write, path, content)

    async def update_ui_preferences(
        self,
        path: Path,
        *,
        skip_pair_instructions: bool | None = None,
    ) -> None:
        """Update UI preferences in existing TOML file (preserves comments).

        Args:
            path: Path to config file (created if missing)
            skip_pair_instructions: Value for skip_pair_instructions (None = no change)
        """
        import aiofiles

        if path.exists():
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
            doc = tomlkit.parse(content)
        else:
            doc = tomlkit.document()
            doc["general"] = tomlkit.table()

        if "ui" not in doc:
            doc["ui"] = tomlkit.table()

        if skip_pair_instructions is not None:
            doc["ui"]["skip_pair_instructions"] = skip_pair_instructions  # type: ignore[index] — tomlkit Table supports subscript assignment at runtime

        content = tomlkit.dumps(doc)
        await asyncio.to_thread(atomic_write, path, content)


def get_fallback_agent_config() -> AgentConfig:
    """Get fallback agent config when none configured."""
    return AgentConfig(
        identity="claude.com",
        name="Claude Code",
        short_name="claude",
        run_command={"*": "npx claude-code-acp"},
        interactive_command={"*": "claude"},
        model_env_var="ANTHROPIC_MODEL",
    )
