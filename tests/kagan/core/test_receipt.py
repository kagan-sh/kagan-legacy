from kagan.core.enums import TaskState
from kagan.core.models import CheckResult, Decision, Finding, SmokeTest, Task
from kagan.core.receipt import render_pr_body, render_receipt


def _full_task() -> Task:
    return Task(
        id="t-1",
        title="Add feature",
        branch="kagan/t-1",
        base_branch="main",
        understanding="Move billing to usage-based; touches the Stripe webhook.",
        scope=["src/billing/**"],
        checks=[
            CheckResult(name="lint", passed=True, detail="ruff clean"),
            CheckResult(name="types", passed=False, detail="1 error"),
        ],
        decisions=[
            Decision(id="d1", question="Base branch?", severity="blocking", answer="main"),
            Decision(id="d2", question="Color?", severity="question"),  # unresolved
        ],
        findings=[
            Finding(
                id="f1", severity="nit", location="src/a.py:1", message="typo", verdict="agree"
            ),
            Finding(id="f2", severity="question", location="src/b.py:2", message="unclear"),  # open
        ],
        smoke_tests=[
            SmokeTest(id="s1", behaviour="Open /health", service="api", verified=True),
            SmokeTest(id="s2", behaviour="Login flow", verified=False),
        ],
        not_covered=["e2e checkout flow"],
    )


def test_receipt_has_adr_spine_sections_and_title():
    md = render_receipt(_full_task())
    assert "# Reviewed-before-push receipt: Add feature" in md
    # ADR spine: Context / Decision / Consequences / Status (§3.7).
    for header in (
        "## Context",
        "## Decision · pinned at intake",
        "## Decision · author comprehension",
        "## Decision · adjudicated findings",
        "## Consequences · machine-verified checks",
        "## Consequences · hand-verified smoke tests",
        "## Consequences · not covered",
        "## Status",
    ):
        assert header in md, header
    assert "e2e checkout flow" in md
    # Context carries the intake WHY + scope.
    assert "Move billing to usage-based" in md
    assert "src/billing/**" in md


def test_receipt_states_ceremony_banner_from_risk():
    md = render_receipt(_full_task())  # medium by default
    assert "reviewed at: medium-risk" in md


def test_receipt_marks_failures_and_unverified_honestly():
    md = render_receipt(_full_task())
    # A failing check is never shown as passed.
    assert "types" in md and "fail" in md.lower()
    # An unverified smoke test is shown unchecked, not as done.
    assert "- [ ] Login flow" in md
    assert "- [x] Open /health" in md


def test_receipt_skips_unresolved_decisions_and_open_findings():
    md = render_receipt(_full_task())
    assert "Color?" not in md  # unresolved decision skipped
    assert "src/b.py:2" not in md  # finding with no verdict skipped


def test_receipt_is_honest_when_empty():
    # CLI-RECEIPT-02: every section keeps an empty placeholder so absent != done.
    md = render_receipt(Task(id="t-1", title="Add feature"))
    assert "## Consequences · not covered" in md
    assert "_No checks recorded._" in md
    assert "_Nothing explicitly marked as not covered._" in md
    assert "_No intake understanding recorded._" in md


def test_receipt_renders_generated_comprehension_questions():
    task = Task(
        id="t-1",
        title="Add feature",
        risk="medium",
        comprehension_prompts=[
            ("postcondition", "How does the billing retry path behave after this diff?"),
            ("what_breaks", "What race could still lose a charge?"),
        ],
        comprehension={
            "postcondition": "Retries three times with exponential backoff.",
            "what_breaks": "Concurrent charges could double-bill.",
        },
    )
    md = render_receipt(task)
    assert "## Decision · author comprehension" in md
    assert "**How does the billing retry path behave after this diff?**" in md
    assert "Retries three times with exponential backoff." in md
    assert "**What race could still lose a charge?**" in md
    assert "**What does this change do, end to end?**" not in md


def test_receipt_renders_author_comprehension_section():
    # Lever 1: the author's own-words rationale travels in the receipt as provenance,
    # plus any per-finding resolution note.
    task = Task(
        id="t-1",
        title="Add feature",
        comprehension={
            "postcondition": "Rounds half-up so the total never drifts on retries.",
            "what_breaks": "Could break on overflow with very large invoice totals.",
        },
        findings=[
            Finding(
                id="f1",
                severity="blocking",
                location="src/a.py:1",
                message="no bound",
                verdict="agree",
                resolution_note="bounded by caller; safe",
            )
        ],
    )
    md = render_receipt(task)
    assert "## Decision · author comprehension" in md
    # Q/A pairs: each prompt's question precedes its recorded answer.
    assert "**What does this change do, end to end?**" in md
    assert "Rounds half-up so the total never drifts" in md
    assert "**What could still break it?**" in md
    assert "Could break on overflow" in md
    assert "bounded by caller; safe" in md


def test_receipt_comprehension_section_honest_when_absent():
    # CLI-RECEIPT: an unwritten note is not dressed up as done.
    md = render_receipt(Task(id="t-1", title="Add feature"))
    assert "## Decision · author comprehension" in md
    assert "_No comprehension note recorded._" in md


def test_receipt_shows_finding_provenance_and_low_confidence():
    # Lever 2/6 provenance: source + confidence + status appear literally next to a
    # finding, so a verifier's own low confidence is never hidden.
    task = Task(
        id="t-1",
        title="Add feature",
        findings=[
            Finding(
                id="f1",
                severity="blocking",
                location="src/eval.rs:80",
                message="precedence ignored",
                verdict="agree",
                source="ai-review",
                confidence=3,
                status="TENTATIVE",
            )
        ],
    )
    md = render_receipt(task)
    assert "source: ai-review" in md
    assert "confidence 3/10" in md
    assert "TENTATIVE" in md


def test_receipt_always_renders_pushback_even_when_empty():
    # §3.8: a missing Pushback section is indistinguishable from "no dissent".
    md = render_receipt(Task(id="t-1", title="Add feature"))
    assert "## Pushback · findings disputed" in md
    assert "_No findings disputed._" in md


def test_receipt_pushback_lists_disagreed_findings_with_reason():
    task = Task(
        id="t-1",
        title="Add feature",
        findings=[
            Finding(
                id="f1",
                severity="blocking",
                location="parser.py:88",
                message="recursion has no bound",
                verdict="disagree",
                reply="bounded by the tokenizer upstream",
            )
        ],
    )
    md = render_receipt(task)
    assert "parser.py:88" in md
    assert "bounded by the tokenizer upstream" in md


def test_receipt_status_carries_approvers_and_lifecycle():
    task = Task(
        id="t-1",
        title="Add feature",
        state=TaskState.READY,
        approvers=["alice <a@x.io>", "bob <b@x.io>"],
    )
    md = render_receipt(task)
    assert "## Status" in md
    assert "Accepted" in md  # READY maps to Accepted
    assert "alice <a@x.io>" in md
    assert "bob <b@x.io>" in md


def test_pr_body_carries_provenance_sections_and_no_title_marker():
    task = _full_task()
    body = render_pr_body(task)
    # It is a paste block, not the receipt file.
    assert "<!-- kagan reviewed-before-push receipt" in body
    assert "# Reviewed-before-push receipt:" not in body  # no h1 receipt title
    # The same provenance/comprehension/pushback sections travel.
    assert "## Context" in body
    assert "## Decision · author comprehension" in body
    assert "## Pushback · findings disputed" in body
    assert "## Consequences · not covered" in body


def test_pr_body_stays_honest_about_unverified_smoke():
    # Same honesty filters as the receipt — never present unverified smoke as done.
    body = render_pr_body(_full_task())
    assert "- [ ] Login flow" in body
    assert "src/b.py:2" not in body  # open finding still omitted
