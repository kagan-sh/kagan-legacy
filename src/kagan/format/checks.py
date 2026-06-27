"""Shared check-result rendering decisions."""

from typing import TYPE_CHECKING

from rich.text import Text

from kagan.core.checks import summarize_checks
from kagan.format import _symbols as sym

if TYPE_CHECKING:
    from kagan.core.api import CheckResult


def receipt_check_row(checks: list[CheckResult]) -> Text:
    summary = summarize_checks(checks)
    if summary.all_passed:
        return Text(f"{sym.DONE} checks ({summary.passed}/{summary.total})")
    if summary.total:
        return Text(f"{sym.BLOCKER} checks ({summary.passed}/{summary.total})", style="blocker")
    return Text(f"{sym.OPTIONAL} checks (none recorded)", style="secondary")


def readiness_check_parts(checks: list[CheckResult]) -> tuple[str, str, str]:
    summary = summarize_checks(checks)
    if summary.all_passed:
        return sym.DONE, "done", f"Checks passed · {summary.passed} of {summary.total}"
    if summary.total:
        return (
            sym.BLOCKER,
            "blocker",
            f"Checks failing · {summary.passed} of {summary.total} passed — "
            f"{summary.failed} failing",
        )
    return sym.OPTIONAL, "secondary", "Checks · none recorded"


__all__ = ["readiness_check_parts", "receipt_check_row"]
