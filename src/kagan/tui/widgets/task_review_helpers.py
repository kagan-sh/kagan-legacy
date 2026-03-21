from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from textual.css.query import NoMatches
from textual.widgets import Checkbox, Static

from kagan.core.enums import TaskStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.containers import Vertical

    from kagan.core.models import ReviewVerdict, Task


def review_verdicts_by_index(task: Task, total_criteria: int) -> dict[int, ReviewVerdict]:
    verdicts_by_index: dict[int, ReviewVerdict] = {}
    for raw in task.review_verdicts or []:
        if not isinstance(raw, dict):
            continue
        index = raw.get("criterion_index")
        verdict = str(raw.get("verdict", "")).upper()
        reason_raw = raw.get("reason")
        reason = str(reason_raw).strip() if reason_raw is not None else ""
        if isinstance(index, int) and 0 <= index < total_criteria and verdict in {"PASS", "FAIL"}:
            verdicts_by_index[index] = {
                "criterion_index": index,
                "verdict": cast("Literal['PASS', 'FAIL']", verdict),
                "reason": reason,
            }
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
    reason_text = verdict["reason"].strip() if verdict is not None else ""
    if reason_text:
        reason_text = "\n".join(f"    {line}" for line in reason_text.splitlines())
    reason_widget.update(reason_text)
    if verdict is not None and verdict["verdict"] == "PASS":
        verdict_widget.update("  ✓ AI: PASS")
        verdict_widget.add_class("ts-criteria-complete")
        return
    if verdict is not None and verdict["verdict"] == "FAIL":
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
        pass_count = sum(1 for verdict in verdicts.values() if verdict["verdict"] == "PASS")
        fail_count = sum(1 for verdict in verdicts.values() if verdict["verdict"] == "FAIL")
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
    criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
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


def build_merge_readiness_text(task: Task | None, *, last_merge_blocker: str | None) -> str:
    if task is None:
        return ""
    if task.status is TaskStatus.DONE and task.review_verdicts:
        criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
        verdicts = review_verdicts_by_index(task, len(criteria))
        pass_count = sum(1 for verdict in verdicts.values() if verdict["verdict"] == "PASS")
        total = len(criteria)
        return f"Review Summary (merged)\n  ✓ {pass_count}/{total} criteria passed"
    if task.status is not TaskStatus.REVIEW:
        return ""

    lines: list[str] = []
    if task.review_approved:
        lines.append("  ✓ Approved")
    else:
        criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
        if criteria:
            lines.append("  ✗ Not approved  →  a to approve")
        else:
            lines.append("  ✗ Not approved (no criteria)  →  a for options")

    if last_merge_blocker:
        lines.append(f"  ✗ {last_merge_blocker}")
    else:
        lines.append("  ✓ No merge blockers")

    criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
    verdicts = review_verdicts_by_index(task, len(criteria))
    if verdicts:
        pass_count = sum(1 for verdict in verdicts.values() if verdict["verdict"] == "PASS")
        fail_count = sum(1 for verdict in verdicts.values() if verdict["verdict"] == "FAIL")
        total = len(criteria)
        if fail_count == 0 and pass_count == total:
            lines.append(f"  ✓ AI review: all {total} criteria passed")
        elif fail_count:
            lines.append(f"  ✗ AI review: {fail_count}/{total} criteria failed")
        else:
            lines.append(f"  ⋯ AI review: {pass_count}/{total} criteria processed")
    else:
        lines.append("  ⋯ AI review: not run yet")

    return "Merge Readiness\n" + "\n".join(lines)
