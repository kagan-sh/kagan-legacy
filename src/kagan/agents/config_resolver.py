"""Unified agent configuration resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kagan.config import AgentConfig, KaganConfig
    from kagan.database.models import Ticket


def resolve_agent_config(
    ticket: Ticket,
    config: KaganConfig,
) -> AgentConfig:
    """Resolve agent config with documented priority order.

    Priority:
    1. ticket.agent_backend (explicit override per ticket)
    2. ticket.assigned_hat (DEPRECATED - backward compat, will be removed)
    3. config.general.default_worker_agent (project default)
    4. Fallback agent config (hardcoded sensible default)

    Args:
        ticket: The ticket to resolve config for
        config: The Kagan configuration

    Returns:
        The resolved AgentConfig
    """
    from kagan.config import get_fallback_agent_config
    from kagan.data.builtin_agents import get_builtin_agent

    # Priority 1: ticket's agent_backend field
    if ticket.agent_backend:
        if builtin := get_builtin_agent(ticket.agent_backend):
            return builtin.config
        # Also check custom agents in config
        if agent_config := config.get_agent(ticket.agent_backend):
            return agent_config

    # Priority 2: assigned_hat (DEPRECATED - for backward compatibility only)
    # TODO: Remove in future version once migration is complete
    if ticket.assigned_hat:
        if builtin := get_builtin_agent(ticket.assigned_hat):
            return builtin.config
        if agent_config := config.get_agent(ticket.assigned_hat):
            return agent_config

    # Priority 3: config's default_worker_agent
    default_agent = config.general.default_worker_agent
    if builtin := get_builtin_agent(default_agent):
        return builtin.config
    if agent_config := config.get_agent(default_agent):
        return agent_config

    # Priority 4: fallback
    return get_fallback_agent_config()
