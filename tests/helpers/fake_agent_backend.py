"""Public seam over fake-agent backend for behavioral / e2e tests.

Production entry points use ``--fake-agent`` / env; tests import from this
module so they stay off ``kagan.core._fake_agent`` (per
``docs/internal/testing.md`` boundary rule).
"""

from __future__ import annotations

from kagan.core._fake_agent import (
    FakeCue,
    FakeScript,
    _cues_to_json,
    director,
    make_fake_chat_factory,
    register_fake_backend,
)

FAKE_AGENT_BACKEND_NAME = "fake-agent"


def ensure_fake_agent_backend_registered() -> None:
    """Idempotently register the fake-agent backend spec with the agent registry."""
    register_fake_backend()


__all__ = [
    "FAKE_AGENT_BACKEND_NAME",
    "FakeCue",
    "FakeScript",
    "_cues_to_json",
    "director",
    "ensure_fake_agent_backend_registered",
    "make_fake_chat_factory",
    "register_fake_backend",
]
