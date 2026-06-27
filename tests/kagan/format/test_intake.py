"""Intake renderer — replaces the SVG snapshot tests."""

from kagan.core.enums import TaskState
from kagan.core.models import Decision, Task
from kagan.format import intake
from tests.kagan.format._render import to_str


def _task(**kw) -> Task:
    return Task(id="t", title=kw.pop("title", "migrate-billing"), state=TaskState.INTAKE, **kw)


def test_understanding_present():
    out = to_str(intake.render_intake(_task(understanding="move to usage-based"), can_run=False))
    assert "What the agent understood" in out
    assert "move to usage-based" in out


def test_empty_understanding_is_auditable():
    out = to_str(intake.render_intake(_task(), can_run=False))
    assert "no understanding recorded" in out


def test_blocking_question_and_options_present():
    task = _task(
        decisions=[
            Decision(
                id="d", question="rounding?", severity="blocking", options=["banker's", "half-up"]
            )
        ]
    )
    out = to_str(intake.render_intake(task, can_run=False))
    assert "rounding?" in out
    assert "banker's" in out and "half-up" in out


def test_lock_phrasing_flips_on_can_run():
    task = _task(decisions=[Decision(id="d", question="q", severity="blocking")])
    locked = to_str(intake.render_intake(task, can_run=False))
    assert "Run locked: 1 blocking decision" in locked
    unlocked = to_str(intake.render_intake(task, can_run=True))
    assert "Run unlocked" in unlocked


def test_resolved_decision_shows_answer_annotation():
    task = _task(
        decisions=[Decision(id="d", question="rounding?", severity="blocking", answer="half-up")]
    )
    out = to_str(intake.render_intake(task, can_run=True))
    assert "Resolved" in out  # sentence-case section header (DESIGN §5 tone)
    assert "rounding? → half-up" in out


def test_optional_decision_is_focusable_after_blocking_resolved():
    # F11: with blocking resolved, the optional row joins the focusable walk so the cursor
    # reaches it — it is adjudicable, not display-only. The cursor maps over
    # [*blocking, *optional], so the single open (optional) decision is focused at index 0.
    task = _task(
        decisions=[
            Decision(id="b", question="rounding?", severity="blocking", answer="half-up"),
            Decision(id="o", question="show errors?", severity="question", options=["yes", "no"]),
        ]
    )
    out = to_str(intake.render_intake(task, can_run=True, cursor=0))
    assert "› ○ show errors?" in out  # noqa: RUF001 — the cursor + optional glyph


def test_scope_footer_present():
    out = to_str(intake.render_intake(_task(scope=["src/billing/**"]), can_run=True))
    assert "Scope" in out
    assert "src/billing/**" in out
