"""Shared value types for native integrations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


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


__all__ = [
    "ExternalItem",
    "ImportResult",
]
