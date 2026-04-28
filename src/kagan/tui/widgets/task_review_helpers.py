from __future__ import annotations

from typing import TYPE_CHECKING

from textual.css.query import NoMatches
from textual.widgets import Checkbox, Static

from kagan.core.enums import TaskStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.containers import Vertical

    from kagan.core.models import ReviewVerdict, Task


def _latest_verdict(verdicts: list[ReviewVerdict]) -> ReviewVerdict | None:
    """Return the latest non-skip verdict from a list, or None."""
    # Verdicts are ordered by id (insertion order). Last one wins.
    for v in reversed(verdicts):
        if v.verdict.lower() in {"pass", "fail"}:
            return v
    return None


def review_verdicts_by_index(task: Task, total_criteria: int) -> dict[int, ReviewVerdict]:
    """Return a mapping of criterion ordinal → latest non-skip ReviewVerdict ORM object."""
    verdicts_by_index: dict[int, ReviewVerdict] = {}
    for criterion in task.criteria:
        if criterion.ordinal < 0 or criterion.ordinal >= total_criteria:
            continue
        verdict = _latest_verdict(criterion.verdicts)
        if verdict is not None:
            verdicts_by_index[criterion.ordinal] = verdict
    return verdicts_by_index


def set_criterion_verdict_widget(
    verdict_widget: Static,
    reason_widget: Static,
    verdict: ReviewVerdict | None,
    *,
    review_running: bool,
) -> None:
    verdict_widget.remove_class(
        "ts-criteria-complete",
        "ts-criteria-fail",
        "ts-criteria-pending",
    )
    reason_text = verdict.reason.strip() if verdict is not None else ""
    if reason_text:
        reason_text = "\n".join(f"    {line}" for line in reason_text.splitlines())
    reason_widget.update(reason_text)
    if verdict is not None and verdict.verdict.lower() == "pass":
        verdict_widget.update("  ✓ AI: PASS")
        verdict_widget.add_class("ts-criteria-complete")
        return
    if verdict is not None and verdict.verdict.lower() == "fail":
        verdict_widget.update("  ✗ AI: FAIL")
        verdict_widget.add_class("ts-criteria-fail")
        return
    if review_running:
        verdict_widget.update("  ⋯ AI: pending")
        verdict_widget.add_class("ts-criteria-pending")
        reason_widget.update("")
        return
    verdict_widget.update("")
    reason_widget.update("")


def render_ai_verdict_summary(task: Task, total_criteria: int, *, running: bool) -> tuple[str, str]:
    verdicts = review_verdicts_by_index(task, total_criteria)
    if verdicts:
        pass_count = sum(1 for v in verdicts.values() if v.verdict.lower() == "pass")
        fail_count = sum(1 for v in verdicts.values() if v.verdict.lower() == "fail")
        if fail_count:
            return f"AI: {pass_count}/{total_criteria} passed ({fail_count} failed)", "fail"
        return f"AI: {pass_count}/{total_criteria} passed", "pass"
    if task.status is TaskStatus.REVIEW and running:
        return "AI Reviewing...", "pending"
    return "", ""


async def render_criteria_checkboxes(
    *,
    task: Task,
    criteria_container: Vertical,
    criteria_status: Static,
    previous_signature: tuple[str, ...] | None,
    running: bool,
    get_static: Callable[[str], Static],
    sync_criteria_status: Callable[[Static], None],
) -> tuple[str, ...] | None:
    sorted_criteria = sorted(task.criteria, key=lambda c: c.ordinal)
    criteria = [c.text.strip() for c in sorted_criteria if c.text.strip()]
    signature = tuple(criteria)
    verdicts_by_index = review_verdicts_by_index(task, len(criteria))
    review_running = task.status is TaskStatus.REVIEW and running

    if not criteria:
        if previous_signature != signature:
            await criteria_container.remove_children()
        criteria_status.update("")
        return signature

    if signature != previous_signature:
        await _mount_criteria_widgets(
            criteria_container, criteria, verdicts_by_index, review_running
        )
        sync_criteria_status(criteria_status)
        return signature

    missing_widgets = False
    for i, _criterion in enumerate(criteria):
        try:
            verdict_widget = get_static(f"#ts-detail-criterion-verdict-{i}")
            reason_widget = get_static(f"#ts-detail-criterion-reason-{i}")
        except NoMatches:
            missing_widgets = True
            break
        set_criterion_verdict_widget(
            verdict_widget,
            reason_widget,
            verdicts_by_index.get(i),
            review_running=review_running,
        )

    if missing_widgets:
        await _mount_criteria_widgets(
            criteria_container, criteria, verdicts_by_index, review_running
        )

    sync_criteria_status(criteria_status)
    return signature


async def _mount_criteria_widgets(
    criteria_container: Vertical,
    criteria: list[str],
    verdicts_by_index: dict[int, ReviewVerdict],
    review_running: bool,
) -> None:
    await criteria_container.remove_children()
    for i, criterion in enumerate(criteria):
        checkbox = Checkbox(
            criterion,
            id=f"ts-detail-criterion-{i}",
            classes="ts-detail-criterion",
        )
        await criteria_container.mount(checkbox)
        verdict_widget = Static(
            id=f"ts-detail-criterion-verdict-{i}",
            classes="ts-detail-criterion-verdict",
        )
        await criteria_container.mount(verdict_widget)
        reason_widget = Static(
            id=f"ts-detail-criterion-reason-{i}",
            classes="ts-detail-criterion-reason",
        )
        await criteria_container.mount(reason_widget)
        set_criterion_verdict_widget(
            verdict_widget,
            reason_widget,
            verdicts_by_index.get(i),
            review_running=review_running,
        )


def _has_any_verdicts(task: Task) -> bool:
    """Return True if any criterion has at least one verdict."""
    return any(c.verdicts for c in task.criteria)


def build_merge_readiness_text(
    task: Task | None,
    *,
    human_approved: bool = False,
    last_merge_blocker: str | None,
) -> str:
    if task is None:
        return ""
    if task.status is TaskStatus.DONE and _has_any_verdicts(task):
        criteria_count = len(task.criteria)
        verdicts = review_verdicts_by_index(task, criteria_count)
        pass_count = sum(1 for v in verdicts.values() if v.verdict.lower() == "pass")
        return f"Review Summary (merged)\n  ✓ {pass_count}/{criteria_count} criteria passed"
    if task.status is not TaskStatus.REVIEW:
        return ""

    lines: list[str] = []
    ai_passed_all = all(
        c.verdicts
        and _latest_verdict(c.verdicts) is not None
        and _latest_verdict(c.verdicts).verdict.lower() == "pass"  # type: ignore[union-attr]
        for c in task.criteria
    ) and bool(task.criteria)
    if human_approved:
        lines.append("  ✓ Human approved")
    else:
        if task.criteria:
            lines.append("  ✗ Human approval pending  →  a to approve")
        else:
            lines.append("  ✗ Human approval pending (no criteria)  →  a for options")

    if last_merge_blocker:
        lines.append(f"  ✗ {last_merge_blocker}")
    else:
        lines.append("  ✓ No merge blockers")

    criteria_count = len(task.criteria)
    verdicts = review_verdicts_by_index(task, criteria_count)
    if verdicts:
        pass_count = sum(1 for v in verdicts.values() if v.verdict.lower() == "pass")
        fail_count = sum(1 for v in verdicts.values() if v.verdict.lower() == "fail")
        total = criteria_count
        if ai_passed_all and fail_count == 0 and pass_count == total:
            lines.append(f"  ✓ AI review: all {total} criteria passed")
        elif fail_count:
            lines.append(f"  ✗ AI review: {fail_count}/{total} criteria failed")
        else:
            lines.append(f"  ⋯ AI review: {pass_count}/{total} criteria processed")
    else:
        lines.append("  ⋯ AI review: not run yet")

    return "Merge Readiness\n" + "\n".join(lines)
