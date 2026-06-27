"""new_task / stats / help / preflight renderers."""

from kagan.format import new_task, stats
from kagan.format.doctor import render_preflight
from kagan.format.help import KeyHint, render_footer_hint, render_keymap
from tests.kagan.format._render import to_str


def test_new_task_lists_clis_and_marks_selected():
    out = to_str(
        new_task.render_new_task_form(
            title="add-oauth",
            scope=["src/auth/**"],
            clis=["codex", "claude"],
            selected="codex",
            recipe_command=["codex"],
        )
    )
    assert "add-oauth" in out
    assert "src/auth/**" in out
    assert "codex" in out and "claude" in out
    assert "✋ I'll drive" in out
    assert "launch: codex …" in out


def test_new_task_no_agent_launch_line():
    out = to_str(
        new_task.render_new_task_form(
            title="t", scope=[], clis=["codex"], selected=None, recipe_command=None
        )
    )
    assert "you drive — no agent CLI" in out


def test_new_task_risk_line_reflects_effective_validator_config():
    # B10: the ceremony line derives from EFFECTIVE config, not the tier label. With no
    # reviewer configured it must say the validator is disabled, never promise it runs.
    no_reviewer = to_str(
        new_task.render_new_task_form(
            title="t",
            scope=["src/**"],
            clis=["claude"],
            selected="claude",
            recipe_command=["claude"],
            risk="medium",
            reviewer_configured=False,
        )
    )
    assert "validator disabled — no reviewer configured" in no_reviewer
    assert "validator + comprehension" not in no_reviewer

    with_reviewer = to_str(
        new_task.render_new_task_form(
            title="t",
            scope=["src/**"],
            clis=["claude"],
            selected="claude",
            recipe_command=["claude"],
            risk="medium",
            reviewer_configured=True,
        )
    )
    assert "validator + comprehension" in with_reviewer
    assert "disabled" not in with_reviewer


def test_new_task_confirm_names_the_effective_reviewer_model():
    # F9: the new-task confirm names WHICH model will review (the effective reviewer), so a
    # supervisor sees it at create time — not a presumed "(a different model)" it can't honor.
    out = to_str(
        new_task.render_new_task_form(
            title="t",
            scope=["src/**"],
            clis=["kimi"],
            selected="kimi",
            recipe_command=["kimi"],
            risk="medium",
            reviewer_configured=True,
            reviewer_note="kimi-code/kimi-for-coding",
        )
    )
    assert "reviewed by kimi-code/kimi-for-coding" in out
    assert "(a different model)" not in out


def test_new_task_risk_and_reviewer_lines_absent_when_none():
    out = to_str(
        new_task.render_new_task_form(
            title="t", scope=[], clis=[], selected=None, recipe_command=None
        )
    )
    assert "risk" not in out
    assert "reviewed by" not in out


def test_scorecard_renders_calm_sentences_and_na_for_empty_signals():
    from kagan.core.api import Scorecard

    # A fresh repo: shipped once, comprehension first-try, two bugs caught, no CI
    # verdict yet, cycle time at medium. N/A (not 0%) when there is no CFR signal.
    card = Scorecard(
        shipped=1,
        cycle_seconds_by_risk={"medium": 10800.0},
        cfr_failed=None,
        cfr_total=None,
        comprehension_first_try=1,
        comprehension_asked=1,
        review_caught=2,
    )
    out = to_str(stats.render_scorecard(card, "rcalc", durability=None))
    assert "just for you" in out  # the private-mirror framing, never a team metric
    assert "1 shipped" in out
    assert "N/A" in out  # no PR CI yet -> N/A, not a fabricated 0%
    assert "1 of 1 answered first try" in out
    assert "2 real bugs surfaced and upheld" in out
    assert "med 3h" in out
    assert "best-effort" in out  # durability is framed as best-effort, never hard
    assert "no scope rewritten enough" in out  # lever 9: empty debt trend renders "—"


def test_scorecard_renders_debt_trend_as_an_observational_private_line():
    from kagan.core.api import Scorecard

    # Lever 9: when scopes have been rewritten across tasks the trend names them so
    # the human sees WHICH area is rotting. It is observational and "just for you" —
    # never a block, never written to the committable .kagan/ (the renderer only
    # ever produces a terminal string; the receipt has no debt coupling).
    card = Scorecard(
        shipped=1,
        cycle_seconds_by_risk={},
        cfr_failed=None,
        cfr_total=None,
        comprehension_first_try=0,
        comprehension_asked=0,
        review_caught=0,
        debt_by_scope={"src/auth/**": 4, "docs/**": 2},
    )
    out = to_str(stats.render_scorecard(card, "rcalc", durability=None))
    assert "just for you" in out  # private mirror framing
    assert "src/auth/** x4" in out  # the hottest scope, named
    assert "observational" in out  # never a hard signal


def test_scorecard_shipped_has_a_30_day_window_and_closing_durable_line():
    # Phase 12c stats §3 + §2: shipped carries its window; the mirror always closes
    # with the read-before-approve line and shows the reflection when passed.
    from kagan.core.api import Scorecard

    card = Scorecard(
        shipped=14,
        cycle_seconds_by_risk={"medium": 10800.0},
        cfr_failed=None,
        cfr_total=None,
        comprehension_first_try=1,
        comprehension_asked=1,
        review_caught=0,
    )
    out = to_str(
        stats.render_scorecard(
            card,
            "myrepo",
            durability=None,
            reflection="You're supervising after hours — the queue keeps.",
        )
    )
    assert "14 shipped in 30 days" in out
    assert "You're supervising after hours — the queue keeps." in out
    assert "it was the read-before-approve" in out


def test_scorecard_too_new_repo_shows_one_calm_line_not_five_dashes():
    # Phase 12c stats §4: a brand-new repo (nothing shipped, no signals) gets one calm
    # whole-screen line instead of five "—" rows reading as 0/vanity.
    from kagan.core.api import Scorecard

    card = Scorecard(
        shipped=0,
        cycle_seconds_by_risk={},
        cfr_failed=None,
        cfr_total=None,
        comprehension_first_try=0,
        comprehension_asked=0,
        review_caught=0,
    )
    out = to_str(stats.render_scorecard(card, "fresh-repo", durability=None))
    assert "Too new to mirror yet — ship a few tasks and this fills in." in out
    assert "durability" not in out  # the five metric rows are not rendered
    assert "clean merges" not in out
    assert "cycle time" not in out


def test_keymap_is_complete_includes_move_new_and_help():
    groups = (("Inbox", (KeyHint("↑↓", "move"), KeyHint("n", "new task"), KeyHint("?", "help"))),)
    out = to_str(render_keymap(groups))
    assert "move" in out
    assert "new task" in out
    assert "help" in out


def test_footer_hint_joins_segments():
    out = to_str(render_footer_hint([KeyHint("n", "new"), KeyHint("q", "quit")]))
    assert "n new   q quit" in out


def test_keymap_scopes_to_active_view_then_other_views():
    # Phase 12c help §2: the active groups lead; the rest are demoted under a dim
    # "Other views" divider (the screen is scoped, not a flat dump of all groups).
    groups = (
        ("Inbox", (KeyHint("n", "new"),)),
        ("Review", (KeyHint("a", "approve"),)),
        ("Ship", (KeyHint("c", "copy"),)),
    )
    out = to_str(render_keymap(groups, primary_count=1))
    assert "Other views" in out
    # the divider sits after the primary group and before the demoted ones
    assert out.index("Inbox") < out.index("Other views") < out.index("Review")


def test_preflight_marks_symbols_and_verdict():
    from kagan.core.doctor_checks import DoctorCheck

    checks = [
        DoctorCheck(name="git", status="pass", message="found"),
        DoctorCheck(name="repo manifest", status="fail", message="no manifest"),
    ]
    out = to_str(render_preflight(checks))
    assert "✓ git repository" in out  # calm sentence label, not the raw check name
    assert "✗ repo config" in out
    assert "Needs attention — 1 must be fixed." in out


def test_preflight_shows_fix_hint_under_fail_and_warn_only():
    # DESIGN §5 doctor: the dimmed fix_hint sits under each fail/warn line — at the
    # one moment the user needs it — but never under a passing check.
    from kagan.core.doctor_checks import DoctorCheck

    checks = [
        DoctorCheck(name="git", status="pass", message="found", fix_hint="should-not-show"),
        DoctorCheck(
            name="gh",
            status="warn",
            message="not found",
            fix_hint="Install gh: https://cli.github.com",
        ),
        DoctorCheck(
            name="repo manifest",
            status="fail",
            message="no manifest",
            fix_hint="Create .kagan/repo.yaml",
        ),
    ]
    out = to_str(render_preflight(checks))
    assert "Install gh: https://cli.github.com" in out  # warn fix shown
    assert "Create .kagan/repo.yaml" in out  # fail fix shown
    assert "should-not-show" not in out  # never under a passing check
