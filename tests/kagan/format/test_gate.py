"""Gate (review) renderer — replaces test_gate_screen.py render assertions."""

from kagan.core.enums import TaskState
from kagan.core.models import CheckResult, Decision, Finding, SmokeTest, Task
from kagan.format import _symbols as sym
from kagan.format import gate
from tests.kagan.format._render import to_str


def _task(**kw) -> Task:
    return Task(
        id="t", title=kw.pop("title", "task"), state=kw.pop("state", TaskState.REVIEW), **kw
    )


def test_checks_strip_marks_pass_and_fail():
    out = to_str(
        gate.render_checks_strip(
            [CheckResult(name="tests", passed=True), CheckResult(name="lint", passed=False)]
        )
    )
    assert "✓ tests" in out
    assert "✗ lint" in out


def test_checks_strip_empty():
    assert "No checks recorded." in to_str(gate.render_checks_strip([]))


def test_decisions_keep_pinned_heading_and_resolved_value():
    out = to_str(
        gate.render_decisions(
            [Decision(id="d", question="rounding?", severity="blocking", answer="half-up")]
        )
    )
    assert "Pinned at intake" in out
    assert "half-up" in out


def test_findings_card_tags_and_verdict():
    out = to_str(
        gate.render_findings(
            [
                Finding(
                    id="f",
                    severity="blocking",
                    location="parser.py:88",
                    message="no depth bound",
                    verdict="disagree",
                    reply="acceptable",
                )
            ]
        )
    )
    assert "blocking" in out  # lowercase tag (DESIGN §5 tone — no shouting)
    assert "parser.py:88" in out
    assert "no depth bound" in out
    assert "disagree — acceptable" in out


def test_findings_none_hunk_does_not_leak_the_word_none():
    out = to_str(gate.render_findings([Finding(id="f", severity="nit", location="a", message="m")]))
    assert "None" not in out
    assert "(open)" in out  # default verdict


def test_findings_show_source_provenance_tag():
    # Lever 2: a finding's source (machine / ai-review / rubric / security) is rendered
    # so the human can tell who raised it — the validator's findings read distinctly.
    out = to_str(
        gate.render_findings(
            [
                Finding(
                    id="f",
                    severity="blocking",
                    location="src/eval.rs:80",
                    message="precedence ignored",
                    source="ai-review",
                )
            ]
        )
    )
    assert "[ai-review]" in out


def test_smoke_marks_verified_and_optional():
    out = to_str(
        gate.render_smoke(
            [
                SmokeTest(id="s1", behaviour="login works", verified=True),
                SmokeTest(id="s2", behaviour="api up", service="api", verified=False),
            ],
            {"api": 51802},
        )
    )
    assert "✓ login works" in out  # the palette ✓, not a sixth ☑ glyph (DESIGN §3.1)
    assert "○ api up  (:51802)" in out


def test_readiness_counts_open_blocking_findings_when_locked():
    task = _task(
        findings=[
            Finding(id="f1", severity="blocking", location="a", message="m"),
            Finding(id="f2", severity="blocking", location="b", message="m", verdict="agree"),
        ],
        checks=[CheckResult(name="t", passed=True)],
    )
    out = to_str(gate.render_readiness(task, locked=True))
    assert "Adjudicate 1 blocking finding" in out
    # The lock reason lives in the persistent lock block, not the checklist.
    assert "Approve is locked" not in out


def test_review_shows_stale_banner_when_stale():
    out = to_str(gate.render_review(_task(branch="kagan/t-1"), stale=True, locked=False))
    assert "stale" in out
    assert "kagan/t-1 → main" in out


def test_readiness_shows_comprehension_pending_then_done():
    # Lever 1: the checklist surfaces the unanswered prompt count as a blocking ●
    # until every required prompt is answered, then ✓ — so the human sees what is
    # still owed before approve. Default (medium) tier has two prompts.
    pending = to_str(gate.render_readiness(_task(), locked=True))
    assert "● Answer 2 comprehension prompt(s)" in pending

    done = to_str(
        gate.render_readiness(
            _task(
                comprehension={
                    "postcondition": "Rounds half-up so the total never drifts on retries.",
                    "what_breaks": "Could break on overflow with very large totals.",
                }
            ),
            locked=False,
        )
    )
    assert "✓ Comprehension recorded" in done


def test_high_risk_readiness_shows_second_approver_waiting():
    # Lever 6: a high-risk task with one approver shows the waiting-for-second row.
    task = _task(risk="high", approvers=["alice <a@x.io>"])
    out = to_str(gate.render_readiness(task, locked=True, high_risk_approvers=2), width=200)
    assert "Second approver" in out
    assert "alice <a@x.io>" in out
    assert "waiting for one more" in out


def test_high_risk_readiness_marks_second_approver_met():
    task = _task(risk="high", approvers=["alice <a@x.io>", "bob <b@x.io>"])
    out = to_str(gate.render_readiness(task, locked=False, high_risk_approvers=2))
    assert "✓ Second approver" in out
    assert "waiting for one more" not in out


def test_non_high_risk_has_no_approver_row():
    # Below high risk a single approver is enough, so no second-approver row appears.
    task = _task(risk="medium", approvers=["alice <a@x.io>"])
    assert gate.render_approvers(task, 2) is None
    out = to_str(gate.render_readiness(task, locked=True, high_risk_approvers=2))
    assert "Second approver" not in out


def test_review_is_readiness_first_and_does_not_dump_comprehension_inline():
    # Phase 12d-2: the main review view is a readiness checklist; comprehension is a
    # step-into sub-view, not dumped inline. Fails if render_review still renders the
    # full prompt set.
    out = to_str(
        gate.render_review(
            _task(comprehension={"postcondition": "Rounds half-up; could break on overflow."}),
            stale=False,
            locked=True,
        )
    )
    assert "Almost ready" in out
    assert "What does this change do, end to end?" not in out
    assert "Rounds half-up; could break on overflow." not in out


def test_render_comprehension_not_required_at_low_risk():
    out = to_str(gate.render_comprehension(_task(risk="low")))
    assert "Not required at low risk." in out


# -- Phase 12d-2: review-screen density + focused-walk sub-frames ---------------


def test_findings_cursor_marks_focused_open_finding():
    findings = [
        Finding(id="f1", severity="blocking", location="a.py:1", message="m1"),
        Finding(id="f2", severity="blocking", location="b.py:2", message="m2"),
    ]
    out = to_str(gate.render_findings(findings, cursor=1))
    # Only the focused open finding carries the cursor glyph.
    lines = [line for line in out.splitlines() if sym.CURSOR in line]
    assert len(lines) == 1
    assert "b.py:2" in lines[0]


def test_smoke_cursor_marks_focused_unverified_test():
    smoke = [
        SmokeTest(id="s1", behaviour="login works"),
        SmokeTest(id="s2", behaviour="api up", service="api"),
    ]
    out = to_str(gate.render_smoke(smoke, {"api": 51802}, cursor=0))
    lines = [line for line in out.splitlines() if sym.CURSOR in line]
    assert len(lines) == 1
    assert "login works" in lines[0]


def test_readiness_cursor_moves_over_focusable_rows():
    # Findings + comprehension + smoke are focusable; checks/approver are not.
    task = _task(
        findings=[Finding(id="f", severity="blocking", location="a", message="m")],
        smoke_tests=[SmokeTest(id="s", behaviour="x")],
        checks=[CheckResult(name="t", passed=True)],
    )
    out = to_str(gate.render_readiness(task, locked=True, cursor=2))
    lines = out.splitlines()
    # Cursor on the smoke row (third focusable row).
    smoke_line = next(line for line in lines if "Smoke tests" in line)
    assert sym.CURSOR in smoke_line
    # Other focusable rows are not focused.
    findings_line = next(line for line in lines if "Adjudicate" in line)
    comprehension_line = next(line for line in lines if "Answer" in line)
    assert sym.CURSOR not in findings_line
    assert sym.CURSOR not in comprehension_line


def test_lock_block_surfaces_cooldown_and_lock_reasons():
    task = _task(
        findings=[Finding(id="f", severity="blocking", location="a", message="m")],
        comprehension={"postcondition": "x"},  # thin -> still pending both medium prompts
    )
    out = to_str(gate.render_lock_block(task, locked=True, cooldown_remaining=90))
    assert "Give it a read before approving" in out
    assert "unlocks in 1:30" in out
    assert "adjudicate the open blocking finding(s)" in out
    assert "answer 2 comprehension prompt(s)" in out


def test_review_main_view_has_no_inline_findings_or_smoke():
    task = _task(
        findings=[Finding(id="f", severity="blocking", location="a.py:1", message="m")],
        smoke_tests=[SmokeTest(id="s", behaviour="submit form")],
    )
    out = to_str(gate.render_review(task, stale=False, locked=True))
    # The readiness checklist is present; the detailed finding/smoke cards are not.
    assert "Almost ready" in out
    assert "a.py:1" not in out
    # The smoke row is in the checklist, but the per-test detail is not.
    assert "submit form" not in out
