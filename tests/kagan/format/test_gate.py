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


def test_readiness_header_and_rows_agree_on_one_predicate():
    # B13: the reassuring summary line and the per-item rows must read ONE predicate for
    # "is this blocking finding adjudicated" (a verdict — agree OR disagree — adjudicates
    # it). The old split (header read `verdict`, the row read `verdict != "agree"`) showed
    # "All blocking findings adjudicated." ABOVE "● Adjudicate 1 blocking finding".
    overruled = _task(
        findings=[
            Finding(
                id="f",
                severity="blocking",
                location="src/a.py:1",
                message="x",
                verdict="disagree",
                reply="bounded upstream",
            )
        ],
    )
    out = to_str(gate.render_readiness(overruled, locked=False))
    assert "All blocking findings adjudicated." in out
    assert "Adjudicate" not in out  # an overruled finding is adjudicated, not still open

    still_open = _task(
        findings=[Finding(id="f", severity="blocking", location="src/a.py:1", message="x")]
    )
    out_open = to_str(gate.render_readiness(still_open, locked=True))
    assert "Adjudicate 1 blocking finding(s)" in out_open
    assert "All blocking findings adjudicated." not in out_open


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


def test_findings_render_repo_safe_locations():
    # #19: legacy/agent-supplied absolute locations must not leak into the review UI.
    out = to_str(
        gate.render_findings(
            [
                Finding(
                    id="f",
                    severity="question",
                    location="/Users/dev/work/app/.kagan/review.md",
                    message="rubric note",
                    source="rubric",
                ),
                Finding(
                    id="g",
                    severity="blocking",
                    location=".",
                    message="repo-wide issue",
                ),
            ]
        )
    )
    assert "/Users/dev/work/app" not in out
    assert ".kagan/review.md" in out
    assert "[repo]" in out


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


def test_readiness_failed_checks_are_blocking_not_passed():
    # Same check data as ship/receipt: a failed required check must render as a
    # blocker, not as a green partial "passed" row.
    task = _task(
        risk="low",
        checks=[
            CheckResult(name="cargo test", passed=True),
            CheckResult(name="cargo fmt", passed=False),
        ],
    )
    out = to_str(gate.render_readiness(task, locked=True))
    assert "✗ Checks failing · 1 of 2 passed — 1 failing" in out
    assert "✓ Checks passed" not in out


def test_lock_block_names_failed_required_checks():
    task = _task(risk="low", checks=[CheckResult(name="cargo clippy", passed=False)])
    out = to_str(gate.render_lock_block(task, locked=True))
    assert "Approve is locked: fix failing required check(s) first: cargo clippy" in out


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


def test_render_comprehension_uses_generated_prompts_at_floor():
    generated = [
        ("postcondition", "How does billing retry after this diff?"),
        ("what_breaks", "What race could still lose a charge?"),
    ]
    out = to_str(gate.render_comprehension(_task(risk="medium", comprehension_prompts=generated)))
    assert "How does billing retry after this diff?" in out
    assert "What race could still lose a charge?" in out
    assert "What does this change do, end to end?" not in out


def _style_of(group, plain: str) -> str:
    """The whole-text style of the comprehension/findings row whose text is ``plain``."""
    row = next(r for r in group.renderables if getattr(r, "plain", None) == plain)
    return str(row.style)


def test_render_comprehension_question_answer_context_carry_distinct_styles():
    # The diff-comprehension surface must not read as one flat grey: question at
    # default weight, recorded answer emphasised, pending dim — three distinct styles.
    group = gate.render_comprehension(
        _task(
            risk="medium",
            comprehension_prompts=[
                ("postcondition", "How does billing retry after this diff?"),
                ("what_breaks", "What race could still lose a charge?"),
            ],
            comprehension={"postcondition": "Retries idempotently keyed on the charge id."},
        )
    )
    question = _style_of(group, "How does billing retry after this diff?")
    answer = _style_of(group, "Retries idempotently keyed on the charge id.")
    pending = _style_of(group, "pending")
    assert question == ""  # default weight, no longer dim
    assert answer == "bold"  # the recorded answer is emphasised
    assert pending == "secondary"  # unanswered stays quiet
    assert question != answer != pending


def test_render_comprehension_marks_generated_vs_static_prompts():
    generated = to_str(
        gate.render_comprehension(
            _task(
                risk="medium",
                comprehension_prompts=[
                    ("postcondition", "How does billing retry after this diff?"),
                    ("what_breaks", "What race could still lose a charge?"),
                ],
            )
        )
    )
    static = to_str(gate.render_comprehension(_task(risk="medium")))
    assert "generated for this diff" in generated
    assert "generated for this diff" not in static
    assert "standard prompts for the tier" in static


def test_render_comprehension_too_short_generated_set_reads_as_static():
    # A generated set below the tier floor falls back to static prompts, so the
    # marker must say static — the human is reading the static set.
    out = to_str(
        gate.render_comprehension(
            _task(risk="high", comprehension_prompts=[("postcondition", "one only?")])
        )
    )
    assert "standard prompts for the tier" in out
    assert "generated for this diff" not in out


def test_findings_message_reads_above_dim_metadata():
    # The unfocused finding row: metadata (severity/location/source) dim, the message
    # itself at default weight (no span emitted) so it carries the eye against the
    # dim tag. The focused row (f1) stays bold and is not asserted here.
    group = gate.render_findings(
        [
            Finding(id="f1", severity="blocking", location="a.py:1", message="first"),
            Finding(id="f2", severity="nit", location="parser.py:88", message="no depth bound"),
        ],
        cursor=0,
    )
    line = next(r for r in group.renderables if "no depth bound" in getattr(r, "plain", ""))
    spans = {line.plain[s.start : s.end]: str(s.style) for s in line.spans}
    tag_span = next(text for text in spans if "parser.py:88" in text)
    assert spans[tag_span] == "secondary"  # metadata dim
    # The message carries the default weight: Rich emits no span for an empty style,
    # so the message text is distinct from the dim tag.
    assert not any("no depth bound" in text for text in spans)


def test_readiness_counts_generated_prompts_at_floor():
    generated = [
        ("postcondition", "How does billing retry after this diff?"),
        ("what_breaks", "What race could still lose a charge?"),
    ]
    pending = to_str(
        gate.render_readiness(
            _task(risk="medium", comprehension_prompts=generated),
            locked=True,
        )
    )
    assert "● Answer 2 comprehension prompt(s)" in pending


def test_readiness_falls_back_when_generated_set_too_short():
    short = [("postcondition", "Only one generated prompt?")]
    pending = to_str(
        gate.render_readiness(
            _task(risk="high", comprehension_prompts=short),
            locked=True,
        )
    )
    assert "● Answer 5 comprehension prompt(s)" in pending


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
