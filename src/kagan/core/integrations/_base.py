"""kagan.core.integrations._base — Integration Protocol and shared result types.

Integrations pull external items (issues, tickets, cards) into the board as
tasks. Each integration is a plain class that satisfies the ``Integration``
typing.Protocol — no ABC, no metaclass, no entry-point magic.

The Protocol is deliberately small. ``id`` and ``preflight`` are the only
methods uniform across integrations, so they're the only ones in the
contract. ``preview``/``sync`` take integration-specific config and are
called via per-id dispatch in REST and MCP layers — typing them generically
would force a fake uniform-config abstraction that doesn't help anyone.

Adding a new integration::

    1. Create src/kagan/core/integrations/myjira.py with a class that
       declares ``id`` and ``preflight``, plus its own typed ``preview`` and
       ``sync`` methods.
    2. Register it in all_enabled() inside __init__.py.
    3. Add per-id branches in _integration_routes.py and toolsets/integrations.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from kagan.core import PreflightCheckResult


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of an idempotent sync operation."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped

    def with_error(self, error: str) -> ImportResult:
        return replace(self, errors=(*self.errors, error))


@dataclass(frozen=True, slots=True)
class ExternalItem:
    """A single item retrieved from an external source during preview.

    Fields map to the lowest-common-denominator across trackers. Anything
    integration-specific goes in ``extra``.
    """

    id: str
    title: str
    url: str = ""
    state: str = ""
    labels: tuple[str, ...] = field(default_factory=tuple)
    already_synced: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class Integration(Protocol):
    """Uniform contract: identity and health.

    Per-integration ``preview``/``sync`` are concrete on the integration's
    class — not on this protocol — because their configs are integration-
    specific.
    """

    id: str

    def preflight(self) -> list[PreflightCheckResult]: ...


__all__ = [
    "ExternalItem",
    "ImportResult",
    "Integration",
]
