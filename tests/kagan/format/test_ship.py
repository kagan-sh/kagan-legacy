"""Ship renderer + receipt digest — replaces test_ship_screen.py render assertions."""

from kagan.core.enums import TaskState
from kagan.core.models import CheckResult, Finding, SmokeTest, Task
from kagan.format import ship
from kagan.format.receipt import render_receipt_digest
from tests.kagan.format._render import to_str


def _task(**kw) -> Task:
    return Task(
        id="t", title=kw.pop("title", "update-docs"), state=kw.pop("state", TaskState.READY), **kw
    )


def test_ship_leads_with_do_this_next_commands():
    task = _task(branch="kagan/task-3e9b")
    out = to_str(
        ship.render_ship(
            task,
            "git push -u origin kagan/task-3e9b",
            "gh pr create --fill",
            receipt="# receipt body",
        )
    )
    assert "Do this next" in out
    assert "git push -u origin kagan/task-3e9b" in out
    # The renderer prints whatever core returns for the pr command (no hardcode).
    assert "gh pr create --fill" in out
    assert "[c]" in out and "[p]" in out


def test_ship_header_shows_branch_arrow():
    out = to_str(ship.render_ship(_task(branch="b"), "push", "pr", ""))
    assert "update-docs · ready" in out  # lowercase state word (DESIGN §5 tone)
    assert "b → main" in out


def test_ship_no_branch_renders_placeholder_without_crashing():
    out = to_str(ship.render_ship(_task(), "(no branch set)", "(no branch set)", ""))
    assert "(no branch set)" in out


def test_digest_ai_review_reflects_validator_outcome_not_any_verdict():
    # B20: the ai-review digest counts ONLY real validator findings and admits when the
    # validator did not run. The old line bucketed any adjudicated finding as "ai-review",
    # so a send-back / machine finding falsely read as "an AI reviewed this".
    disabled = _task(  # medium, no validator_outcome -> disabled
        risk="medium",
        findings=[
            Finding(
                id="f",
                severity="question",
                location="x",
                message="m",
                source="machine",
                verdict="agree",
            )
        ],
    )
    out = to_str(render_receipt_digest(disabled))
    assert "ai-review (none — validator disabled)" in out
    assert "ai-review (1)" not in out

    ran = _task(
        risk="medium",
        validator_outcome="ran",
        findings=[
            Finding(
                id="f",
                severity="blocking",
                location="x",
                message="m",
                source="ai-review",
                verdict="agree",
            )
        ],
    )
    out2 = to_str(render_receipt_digest(ran))
    assert "ai-review (1)" in out2


def test_receipt_digest_honesty_failing_check_shows_blocker():
    task = _task(
        checks=[CheckResult(name="a", passed=True), CheckResult(name="b", passed=False)],
        not_covered=["screenshots"],
    )
    out = to_str(render_receipt_digest(task))
    assert "✗ checks (1/2)" in out
    assert "⚠ not covered: screenshots" in out


def test_ship_renders_retro_affordance_when_present():
    # Phase 12c ship §1: the lever-8 learning gets an `l` affordance on the ship
    # screen (where the loop closes) — absent when there is no candidate.
    task = _task(branch="b")
    with_retro = to_str(
        ship.render_ship(task, "push", "pr", "", retro="docs are generated — never hand-edit")
    )
    assert "One learning for next time?" in with_retro
    assert "docs are generated — never hand-edit" in with_retro
    assert "l learning" in with_retro  # the affordance is in the footer

    without = to_str(ship.render_ship(task, "push", "pr", ""))
    assert "One learning for next time?" not in without
    assert "l learning" not in without


def test_ship_thin_receipt_gets_a_dim_honesty_line():
    # Phase 12c ship §3: a hollow digest (nothing machine-verified or adjudicated)
    # is flagged so it is not read as a confident receipt under the bold header.
    thin = to_str(ship.render_ship(_task(branch="b"), "push", "pr", ""))
    assert "This receipt is thin — nothing was machine-verified or adjudicated." in thin

    # A receipt with a passing check is NOT thin.
    solid = to_str(
        ship.render_ship(
            _task(branch="b", checks=[CheckResult(name="tests", passed=True)]), "push", "pr", ""
        )
    )
    assert "This receipt is thin" not in solid


def test_ship_receipt_with_failed_executed_check_is_not_thin():
    # Executed checks are machine verification even when they fail; the digest is
    # red, but not hollow.
    out = to_str(
        ship.render_ship(
            _task(branch="b", checks=[CheckResult(name="cargo fmt", passed=False)]),
            "push",
            "pr",
            "",
        )
    )
    assert "✗ checks (0/1)" in out
    assert "This receipt is thin" not in out


def test_ship_copy_feedback_persists_in_rendered_state():
    # Phase 12c ship §4: a successful copy shows "[c ✓ copied]" in the rendered frame
    # (persisted), not a print scrolled off by the next redraw.
    out = to_str(ship.render_ship(_task(branch="b"), "git push", "gh pr", "", copied="c"))
    assert "[c ✓ copied]" in out
    assert "[p]" in out  # the other keys keep their plain badge


def test_ship_never_pushes_is_a_dim_trailing_clause_not_the_action_header():
    # Phase 12c ship §5: "kagan never pushes" is demoted to a dim trailing clause; the
    # action header is the clean "Do this next", not an anxious disclaimer.
    out = to_str(ship.render_ship(_task(branch="b"), "push", "pr", ""))
    assert "Do this next" in out
    assert "Do this next (kagan never pushes)" not in out
    assert "kagan never pushes" in out  # still present, just demoted into the footer
    footer_line = next(line for line in out.splitlines() if "kagan never pushes" in line)
    assert "q quit" in footer_line  # it trails the key line, not a header


def test_receipt_digest_all_checks_pass():
    task = _task(
        checks=[CheckResult(name="a", passed=True)],
        smoke_tests=[SmokeTest(id="s", behaviour="x", verified=True)],
    )
    out = to_str(render_receipt_digest(task))
    assert "✓ checks (1/1)" in out
    assert "✓ smoke (1/1)" in out  # the palette ✓, not a sixth ☑ glyph (DESIGN §3.1)
