"""Shared value types and the Integration protocol for native integrations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from kagan.core._preflight import PreflightCheckResult
    from kagan.core.client import KaganCore


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


@runtime_checkable
class Integration(Protocol):
    """Minimal contract every native integration must satisfy.

    Implementations should declare an ``id`` class attribute that uniquely
    identifies the integration (e.g. ``"github"``).  The ``config`` parameter
    accepted by :meth:`sync` and :meth:`preview` is integration-specific —
    callers hold a concrete integration instance and know its config type.
    ``Any`` is used here so the protocol does not constrain config shapes.
    """

    id: str

    def preflight(self) -> list[PreflightCheckResult]:
        """Return health-check results for this integration's dependencies."""
        ...

    async def sync(
        self,
        client: KaganCore,
        config: Any,
        project_id: str,
    ) -> ImportResult:
        """Import items from the external service into *project_id*."""
        ...

    async def preview(
        self,
        client: KaganCore,
        config: Any,
        project_id: str,
    ) -> list[ExternalItem]:
        """Fetch items without importing — used for dry-run / UI preview."""
        ...

    async def push_task_change(
        self,
        client: KaganCore,
        task: Any,
        *,
        fields: set[str],
    ) -> None:
        """Push task field changes back to the external service."""
        ...


__all__ = [
    "ExternalItem",
    "ImportResult",
    "Integration",
]
