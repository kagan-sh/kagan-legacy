"""Optional fake-agent backend registration for behavioral tests.

Production entry points use ``--fake-agent`` / env; tests call
:func:`ensure_fake_agent_backend_registered` so ``tests/server`` code stays on
the public ``KaganCore`` surface without importing ``kagan.core._fake_agent``.
"""

from __future__ import annotations

FAKE_AGENT_BACKEND_NAME = "fake-agent"


def ensure_fake_agent_backend_registered() -> None:
    """Idempotently register the fake-agent backend spec with the agent registry."""
    from kagan.core._fake_agent import register_fake_backend

    register_fake_backend()
