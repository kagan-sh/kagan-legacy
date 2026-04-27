"""Insight distillation — post-session knowledge extraction and project memory."""

from __future__ import annotations

from enum import StrEnum


class InsightCategory(StrEnum):
    """Categories for distilled project insights."""

    PATTERN = "pattern"  # Recurring code/architecture patterns
    ERROR = "error"  # Error patterns and their solutions
    ARCHITECTURE = "architecture"  # Structural decisions and constraints
    PREFERENCE = "preference"  # User/project preferences discovered
    DEPENDENCY = "dependency"  # External dependency gotchas


__all__ = [
    "InsightCategory",
]
