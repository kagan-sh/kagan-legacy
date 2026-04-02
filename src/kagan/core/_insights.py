"""Insight distillation — post-session knowledge extraction and project memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from loguru import logger


class InsightCategory(StrEnum):
    """Categories for distilled project insights."""

    PATTERN = "pattern"  # Recurring code/architecture patterns
    ERROR = "error"  # Error patterns and their solutions
    ARCHITECTURE = "architecture"  # Structural decisions and constraints
    PREFERENCE = "preference"  # User/project preferences discovered
    DEPENDENCY = "dependency"  # External dependency gotchas


@dataclass(slots=True)
class ProjectInsight:
    """A single distilled insight from session history."""

    category: InsightCategory
    content: str
    source_task_id: str
    source_session_id: str | None = None
    relevance_score: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "content": self.content,
            "source_task_id": self.source_task_id,
            "source_session_id": self.source_session_id,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectInsight:
        return cls(
            category=InsightCategory(data["category"]),
            content=data["content"],
            source_task_id=data["source_task_id"],
            source_session_id=data.get("source_session_id"),
            relevance_score=data.get("relevance_score", 1.0),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now(UTC)
            ),
        )


@dataclass(slots=True)
class InsightStore:
    """In-memory store for project insights with deduplication and decay.

    Insights are persisted via TaskNote entries with [INSIGHT:{category}] prefix.
    This class provides structured access and management over raw notes.
    """

    max_insights: int = 50
    decay_factor: float = 0.95  # Relevance decays by 5% each session
    _insights: list[ProjectInsight] = field(default_factory=list)

    def add(self, insight: ProjectInsight) -> bool:
        """Add an insight, deduplicating by content similarity. Returns True if added."""
        # Simple dedup: exact content match
        for existing in self._insights:
            if existing.content.strip().lower() == insight.content.strip().lower():
                # Refresh the relevance of existing duplicates
                existing.relevance_score = min(1.0, existing.relevance_score + 0.1)
                return False

        self._insights.append(insight)

        # Evict lowest-relevance insights if over capacity
        if len(self._insights) > self.max_insights:
            self._insights.sort(key=lambda i: i.relevance_score, reverse=True)
            self._insights = self._insights[: self.max_insights]

        logger.info(
            "Insight added: category={} task={} ({} total)",
            insight.category.value,
            insight.source_task_id,
            len(self._insights),
        )
        return True

    def decay_all(self) -> None:
        """Apply decay to all insight relevance scores."""
        for insight in self._insights:
            insight.relevance_score *= self.decay_factor
        # Remove insights that have decayed below threshold
        self._insights = [i for i in self._insights if i.relevance_score >= 0.1]

    def get_relevant(
        self,
        *,
        limit: int = 20,
        category: InsightCategory | None = None,
    ) -> list[ProjectInsight]:
        """Get the most relevant insights, optionally filtered by category."""
        candidates = self._insights
        if category is not None:
            candidates = [i for i in candidates if i.category == category]
        candidates = sorted(candidates, key=lambda i: i.relevance_score, reverse=True)
        return candidates[:limit]

    def remove(self, content: str) -> bool:
        """Remove an insight by content. Returns True if found and removed."""
        before = len(self._insights)
        self._insights = [
            i for i in self._insights if i.content.strip().lower() != content.strip().lower()
        ]
        removed = len(self._insights) < before
        if removed:
            logger.info("Insight removed: {:.60}...", content)
        return removed

    def to_prompt_lines(self, *, limit: int = 20) -> list[str]:
        """Format insights for injection into task prompts.

        Returns lines in a format compatible with the existing learnings system.
        """
        relevant = self.get_relevant(limit=limit)
        lines: list[str] = []
        for insight in relevant:
            lines.append(f"[{insight.category.value.upper()}] {insight.content}")
        return lines

    @property
    def count(self) -> int:
        return len(self._insights)

    def summary(self) -> dict[str, Any]:
        """Return a summary of the insight store state."""
        by_category: dict[str, int] = {}
        for insight in self._insights:
            by_category[insight.category.value] = by_category.get(insight.category.value, 0) + 1
        return {
            "total": self.count,
            "max": self.max_insights,
            "by_category": by_category,
            "avg_relevance": (
                sum(i.relevance_score for i in self._insights) / len(self._insights)
                if self._insights
                else 0.0
            ),
        }


def extract_insights_from_notes(
    notes: list[str],
    task_id: str,
) -> list[ProjectInsight]:
    """Parse existing [LEARNING] notes into structured ProjectInsight objects.

    Provides backward compatibility with the existing learning system.
    """
    insights: list[ProjectInsight] = []
    for note in notes:
        # Try to parse category from [INSIGHT:category] format first
        content = note
        category = InsightCategory.PATTERN  # default

        for cat in InsightCategory:
            prefix = f"[{cat.value.upper()}]"
            if content.startswith(prefix):
                category = cat
                content = content.removeprefix(prefix).strip()
                break

        if content:
            insights.append(
                ProjectInsight(
                    category=category,
                    content=content,
                    source_task_id=task_id,
                )
            )
    return insights


__all__ = [
    "InsightCategory",
    "InsightStore",
    "ProjectInsight",
    "extract_insights_from_notes",
]
