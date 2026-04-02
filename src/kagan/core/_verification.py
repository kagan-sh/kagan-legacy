"""Plan step verification — mid-execution validation for agent tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from loguru import logger


class StepVerdict(StrEnum):
    """Outcome of verifying a plan step."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(slots=True)
class StepVerification:
    """Result of verifying a single plan step."""

    step_index: int
    step_description: str
    verdict: StepVerdict
    reason: str
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "step_description": self.step_description,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "verified_at": self.verified_at.isoformat(),
        }


@dataclass(slots=True)
class VerificationSummary:
    """Aggregated verification results for a session."""

    task_id: str
    session_id: str
    steps: list[StepVerification] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def passed(self) -> int:
        return sum(1 for s in self.steps if s.verdict == StepVerdict.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for s in self.steps if s.verdict == StepVerdict.FAIL)

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0

    def add(self, step: StepVerification) -> None:
        self.steps.append(step)
        if step.verdict == StepVerdict.FAIL:
            logger.warning(
                "Step {} failed verification for task={}: {}",
                step.step_index,
                self.task_id,
                step.reason,
            )
        else:
            logger.info(
                "Step {} verified for task={}: verdict={}",
                step.step_index,
                self.task_id,
                step.verdict.value,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "all_passed": self.all_passed,
            "steps": [s.to_dict() for s in self.steps],
        }


def build_verification_prompt_section(criteria: list[str]) -> str:
    """Build a prompt section instructing the agent to verify steps.

    Injected into task prompts when planning_depth is 'always'.
    """
    if not criteria:
        return ""

    lines = [
        "<verification>",
        "After completing each major step, pause and verify your work:",
        "",
    ]
    for i, criterion in enumerate(criteria, 1):
        lines.append(f"  {i}. {criterion}")
    lines.extend(
        [
            "",
            "If a step fails verification, fix the issue before proceeding.",
            "Do not skip verification — catching errors early saves significant rework.",
            "</verification>",
        ]
    )
    return "\n".join(lines)
