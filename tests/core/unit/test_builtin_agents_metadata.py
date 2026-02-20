"""Tier-0 metadata completeness tests for all registered agent backends.

These tests require no binary, no API key, and no environment variable.
They are always run as part of the standard unit test suite.

Path-based marker policy auto-applies ``core`` and ``unit`` markers to
everything under tests/core/unit/.
"""

from __future__ import annotations

import pytest

from kagan.core.agents.installer import AgentType
from kagan.core.builtin_agents import AGENT_PRIORITY, BUILTIN_AGENTS
from kagan.core.config import get_os_value

_ALL_AGENT_NAMES = list(BUILTIN_AGENTS.keys())


@pytest.mark.parametrize("agent_name", _ALL_AGENT_NAMES)
def test_agent_metadata_complete(agent_name: str) -> None:
    """Every registered agent must have all required metadata fields populated."""
    agent = BUILTIN_AGENTS[agent_name]
    cfg = agent.config

    assert cfg.identity, f"{agent_name}: config.identity is empty"
    assert cfg.name, f"{agent_name}: config.name is empty"
    assert cfg.short_name == agent_name, (
        f"{agent_name}: short_name {cfg.short_name!r} must match dict key"
    )
    assert cfg.run_command, f"{agent_name}: run_command is empty"
    assert cfg.interactive_command, f"{agent_name}: interactive_command is empty"
    assert agent.install_command, f"{agent_name}: install_command is empty"
    assert agent.author, f"{agent_name}: author is empty"
    assert agent.description, f"{agent_name}: description is empty"
    assert agent.backend_config is not None, f"{agent_name}: backend_config is None"


@pytest.mark.parametrize("agent_name", _ALL_AGENT_NAMES)
def test_agent_priority_registered(agent_name: str) -> None:
    """Every agent in BUILTIN_AGENTS must appear in AGENT_PRIORITY."""
    assert agent_name in AGENT_PRIORITY, (
        f"{agent_name} is in BUILTIN_AGENTS but missing from AGENT_PRIORITY"
    )


def test_priority_no_unknown_entries() -> None:
    """AGENT_PRIORITY must not reference agents absent from BUILTIN_AGENTS."""
    unknown = [n for n in AGENT_PRIORITY if n not in BUILTIN_AGENTS]
    assert not unknown, f"AGENT_PRIORITY references unknown agents: {unknown}"


@pytest.mark.parametrize("agent_name", _ALL_AGENT_NAMES)
def test_agent_run_command_has_wildcard_or_os_key(agent_name: str) -> None:
    """run_command must resolve to a non-empty string on the current OS."""
    agent = BUILTIN_AGENTS[agent_name]
    resolved = get_os_value(agent.config.run_command)
    assert resolved, f"{agent_name}: run_command has no entry for current OS or wildcard '*'"


@pytest.mark.parametrize("agent_name", _ALL_AGENT_NAMES)
def test_agent_interactive_command_has_wildcard_or_os_key(agent_name: str) -> None:
    """interactive_command must resolve to a non-empty string on the current OS."""
    agent = BUILTIN_AGENTS[agent_name]
    resolved = get_os_value(agent.config.interactive_command)
    assert resolved, (
        f"{agent_name}: interactive_command has no entry for current OS or wildcard '*'"
    )


@pytest.mark.parametrize("agent_name", _ALL_AGENT_NAMES)
def test_agent_installer_enum_registered(agent_name: str) -> None:
    """Every BUILTIN_AGENTS entry must have a corresponding AgentType enum member."""
    assert agent_name in {member.value for member in AgentType}, (
        f"{agent_name} is in BUILTIN_AGENTS but not in AgentType enum — "
        "add it to installer.py:AgentType"
    )
