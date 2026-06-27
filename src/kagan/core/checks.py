"""Shared truth for declared check results."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kagan.core.models import CheckResult


@dataclass(frozen=True)
class CheckSummary:
    total: int
    passed: int

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0

    @property
    def has_failures(self) -> bool:
        return self.failed > 0


def summarize_checks(checks: list[CheckResult]) -> CheckSummary:
    return CheckSummary(total=len(checks), passed=sum(1 for c in checks if c.passed))


def has_failed_checks(checks: list[CheckResult]) -> bool:
    return summarize_checks(checks).has_failures


__all__ = ["CheckSummary", "has_failed_checks", "summarize_checks"]
