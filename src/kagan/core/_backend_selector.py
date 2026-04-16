"""Intelligent backend selection based on multi-dimensional analytics.

Selects the optimal backend for a task considering:
- Task type (code implementation, bug fix, etc.)
- Agent role (worker, orchestrator, reviewer)
- Historical performance metrics
- Available backends
- Minimum threshold for statistical confidence
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core._task_classification import classify_task

if TYPE_CHECKING:
    from kagan.core._analytics import Analytics
    from kagan.core.enums import TaskType


# Minimum number of sessions needed before a recommendation is considered valid
MIN_SESSIONS_FOR_CONFIDENCE = 5

# Success rate threshold - only recommend backends above this rate
MIN_SUCCESS_RATE = 0.5  # 50%


class BackendSelector:
    """Selects optimal backend using multi-dimensional analytics."""

    def __init__(self, analytics: Analytics, project_id: str) -> None:
        self._analytics = analytics
        self._project_id = project_id
        self._cached_stats: dict[str, Any] | None = None

    async def _load_stats(self) -> dict[str, Any]:
        """Load all analytics stats (cached)."""
        if self._cached_stats is None:
            # Load all dimensional stats
            backend_role_task = await self._analytics.backend_role_task_stats(self._project_id)
            backend_role = await self._analytics.backend_by_role_stats(self._project_id)
            backend_task = await self._analytics.backend_by_task_type_stats(self._project_id)
            backend_only = await self._analytics.backend_stats(self._project_id)

            self._cached_stats = {
                "backend_role_task": backend_role_task,
                "backend_role": backend_role,
                "backend_task": backend_task,
                "backend": backend_only,
            }

        return self._cached_stats

    async def select_backend(
        self,
        title: str,
        description: str = "",
        agent_role: str | None = None,
        available_backends: list[str] | None = None,
        fallback_backend: str = "claude-code",
    ) -> dict[str, Any]:
        """Select optimal backend for a task.

        Returns dict with:
        - backend: selected backend name
        - reason: why this backend was selected
        - confidence: statistical confidence (0-1)
        - alternatives: list of alternative good backends
        """
        # Classify the task
        task_type = classify_task(title, description)

        # Load analytics
        stats = await self._load_stats()

        # Filter to available backends
        available = available_backends or [b["agent_backend"] for b in stats["backend"]]
        if not available:
            return {
                "backend": fallback_backend,
                "reason": "no available backends",
                "confidence": 0,
                "alternatives": [],
            }

        # Try to find best match in this order:
        # 1. Backend + Role + TaskType (most specific)
        # 2. Backend + TaskType
        # 3. Backend + Role
        # 4. Backend only (least specific)

        result = await self._find_best_backend(
            available,
            task_type,
            agent_role,
            stats,
        )

        if result:
            return result

        # Fallback: use highest-performing available backend
        backend_stats = [b for b in stats["backend"] if b["agent_backend"] in available]
        if backend_stats:
            best = max(backend_stats, key=lambda b: b["success_rate"])
            return {
                "backend": best["agent_backend"],
                "reason": "best overall performer",
                "confidence": 0.5 if best["count"] >= MIN_SESSIONS_FOR_CONFIDENCE else 0,
                "alternatives": [
                    b["agent_backend"]
                    for b in sorted(backend_stats, key=lambda x: x["success_rate"], reverse=True)[
                        :2
                    ]
                ],
            }

        # Ultimate fallback
        return {
            "backend": fallback_backend,
            "reason": "no performance data available",
            "confidence": 0,
            "alternatives": available,
        }

    async def _find_best_backend(
        self,
        available: list[str],
        task_type: TaskType,
        agent_role: str | None,
        stats: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Find best backend with sufficient confidence."""
        candidates = []

        # Strategy 1: Backend + Role + TaskType
        if agent_role:
            for row in stats["backend_role_task"]:
                if (
                    row["agent_backend"] in available
                    and row["agent_role"] == agent_role
                    and row["task_type"] == task_type
                    and row["count"] >= MIN_SESSIONS_FOR_CONFIDENCE
                    and row["success_rate"] >= MIN_SUCCESS_RATE
                ):
                    candidates.append(
                        (
                            "backend_role_task",
                            row["agent_backend"],
                            row["success_rate"],
                            row["count"],
                        )
                    )

        # Strategy 2: Backend + TaskType
        if not candidates:
            for row in stats["backend_task"]:
                if (
                    row["agent_backend"] in available
                    and row["task_type"] == task_type
                    and row["count"] >= MIN_SESSIONS_FOR_CONFIDENCE
                    and row["success_rate"] >= MIN_SUCCESS_RATE
                ):
                    candidates.append(
                        (
                            "backend_task",
                            row["agent_backend"],
                            row["success_rate"],
                            row["count"],
                        )
                    )

        # Strategy 3: Backend + Role
        if not candidates and agent_role:
            for row in stats["backend_role"]:
                if (
                    row["agent_backend"] in available
                    and row["agent_role"] == agent_role
                    and row["count"] >= MIN_SESSIONS_FOR_CONFIDENCE
                    and row["success_rate"] >= MIN_SUCCESS_RATE
                ):
                    candidates.append(
                        (
                            "backend_role",
                            row["agent_backend"],
                            row["success_rate"],
                            row["count"],
                        )
                    )

        # Return best candidate if found
        if candidates:
            best_strategy, best_backend, _success_rate, count = max(
                candidates,
                key=lambda x: x[2],  # Sort by success rate
            )
            confidence = min(1.0, count / (MIN_SESSIONS_FOR_CONFIDENCE * 3))

            return {
                "backend": best_backend,
                "reason": f"optimal for {best_strategy}",
                "confidence": round(confidence, 2),
                "alternatives": [
                    c[1] for c in sorted(candidates, key=lambda x: x[2], reverse=True)[1:3]
                ],
            }

        return None
