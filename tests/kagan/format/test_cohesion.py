"""Phase 12b cohesion gates — the DESIGN §5 calm aesthetic, enforced structurally.

Each test fails without its 12b fix (Rule 9): one selection cursor, ✓/○ smoke (not
☑), a single meaning for ●, no heavy box chars in any renderer, width-aware right
alignment, the semantic Theme + the one Console factory, lowercase state words.
"""

from datetime import UTC, datetime
from pathlib import Path

from kagan.core.enums import TaskState
from kagan.core.models import CheckResult, Decision, Finding, SmokeTest, Task
from kagan.format import _symbols as sym
from kagan.format import gate, inbox, intake, new_task, receipt, ship, stats, workspaces
from kagan.format._console import KAGAN_THEME, make_console, render_to_str
from kagan.format.doctor import render_preflight
from tests.kagan.format._render import to_str

# Heavy box-drawing characters a Table(box=...) / Panel would emit (corners, edges,
# heavy lines, double lines). No calm renderer may produce these (DESIGN §5: no
# boxes). The bare hairline ``─`` (a Rule) is intentionally allowed — §5 keeps
# "hairline rules + whitespace"; a Rule is one horizontal line, not a box.
_HEAVY_BOX = set("┏┓┗┛┃━┡┩│┌┐└┘├┤┬┴┼╭╮╰╯═║╔╗╚╝╞╡╤╧╪▏▕")


def _task(**kw) -> Task:
    return Task(id=kw.pop("id", "t"), title=kw.pop("title", "task"), **kw)


# -- §3.1 glyph audit ---------------------------------------------------------


def test_one_selection_cursor_glyph_everywhere():
    # CURSOR is the single focus marker; IN_REVIEW must never double as the cursor
    # (a focused in-review row would otherwise render the in-review glyph twice).
    assert sym.CURSOR == "›"  # noqa: RUF001 — the single-right-angle-quote cursor
    assert sym.CURSOR != sym.IN_REVIEW

    from kagan.core.inbox import build_item, sort_items

    rows = sort_items([build_item(_task(id="r", title="r", state=TaskState.REVIEW))])
    out = to_str(inbox.render_inbox(rows, {}, "repo", coach="c", cursor=0))
    assert f"{sym.CURSOR} " in out  # the focused inbox row uses the cursor, not in-review

    dline = intake._decision_line(
        Decision(id="d", question="q?", severity="blocking"), focused=True
    )
    assert sym.CURSOR in to_str(dline)
    assert to_str(dline).count(sym.IN_REVIEW) == 0  # in-review glyph never in the cursor slot

    form = new_task.render_new_task_form(
        title="t", scope=[], clis=["codex"], selected="codex", recipe_command=["codex"]
    )
    assert sym.CURSOR in to_str(form)


def test_smoke_uses_palette_check_not_a_sixth_glyph():
    # gate + receipt: verified smoke is ✓ / unverified ○, never ☑ (a sixth glyph).
    gate_out = to_str(gate.render_smoke([SmokeTest(id="s", behaviour="login", verified=True)], {}))
    assert "✓ login" in gate_out
    assert "☑" not in gate_out

    rec_out = to_str(
        receipt.render_receipt_digest(
            _task(smoke_tests=[SmokeTest(id="s", behaviour="x", verified=True)])
        )
    )
    assert "✓ smoke" in rec_out
    assert "☑" not in rec_out


def test_needs_you_dot_has_a_single_meaning():
    # ● is needs-you only. The inbox header live bucket uses ◷ (working), and the
    # workspace service-health line uses plain text — neither reuses ●.
    header = to_str(inbox.render_header({"live": 3}, "repo"))
    assert sym.NEEDS_YOU not in header  # live is ◷, not ●
    assert sym.WORKING in header

    detail = to_str(
        workspaces.render_workspace_detail(
            _task(state=TaskState.RUNNING, ports={"api": 51802}, worktree_path=Path("/wt"))
        )
    )
    assert sym.NEEDS_YOU not in detail  # health is plain text, not the reserved dot


# -- §3.2 no heavy boxes ------------------------------------------------------


def test_no_renderer_emits_a_heavy_box_character():
    card = __import__("kagan.core.api", fromlist=["Scorecard"]).Scorecard(
        shipped=14,
        cycle_seconds_by_risk={"low": 2400.0, "medium": 10800.0, "high": 86400.0},
        cfr_failed=2,
        cfr_total=14,
        comprehension_first_try=9,
        comprehension_asked=14,
        review_caught=2,
        debt_by_scope={"src/auth/**": 4},
    )
    from kagan.core.doctor_checks import DoctorCheck

    checks = [
        DoctorCheck(name="git", status="pass", message="found"),
        DoctorCheck(name="gh", status="warn", message="not found", fix_hint="brew install gh"),
    ]
    renders = [
        stats.render_scorecard(card, "repo", durability=(11, 14)),
        render_preflight(checks),
        workspaces.render_workspaces(
            [
                _task(
                    id="w",
                    title="w",
                    state=TaskState.RUNNING,
                    ports={"api": 1},
                    created_at=datetime.now(UTC),
                )
            ],
            repo_name="repo",
            now=datetime.now(UTC),
        ),
    ]
    for renderable in renders:
        out = to_str(renderable, width=80)
        assert not (_HEAVY_BOX & set(out)), f"heavy box char in: {out!r}"


# -- §3.3 width-aware alignment ----------------------------------------------


def test_scorecard_right_rail_is_flush_at_60_and_120_no_space_literal():
    card = __import__("kagan.core.api", fromlist=["Scorecard"]).Scorecard(
        shipped=14,
        cycle_seconds_by_risk={"medium": 10800.0},
        cfr_failed=None,
        cfr_total=None,
        comprehension_first_try=1,
        comprehension_asked=1,
        review_caught=0,
    )
    for width in (60, 120):
        out = to_str(stats.render_scorecard(card, "repo", durability=None), width=width)
        header_line = next(line for line in out.splitlines() if "just for you" in line)
        # The rail is flush-right at the real width — its end sits within one cell of
        # the column edge at BOTH widths (a 54-space literal would only work near 100).
        assert header_line.rstrip().endswith("just for you")
        assert len(header_line.rstrip()) >= width - 2


# -- §3.4 theme + console factory --------------------------------------------


def test_semantic_theme_style_names_resolve():
    for name in (
        "blocker",
        "advisory",
        "done",
        "needs-you",
        "note",
        "secondary",
        "risk.low",
        "risk.med",
        "risk.high",
    ):
        assert name in KAGAN_THEME.styles


def test_make_console_factory_serves_both_paths():
    # The same factory builds the prod (color) and test (no_color) consoles — only
    # the no_color flag differs, and both resolve the theme styles.
    prod = make_console(80, no_color=False)
    test = make_console(80, no_color=True)
    assert prod.no_color is False
    assert test.no_color is True
    from rich.text import Text

    colored = render_to_str(Text("x", style="blocker"), width=40, no_color=False)
    plain = render_to_str(Text("x", style="blocker"), width=40, no_color=True)
    assert "\x1b[" in colored  # the prod path carries ANSI color
    assert "\x1b[" not in plain  # the test path is plain


# -- §3.6 tone ---------------------------------------------------------------


def test_state_words_are_lowercase_not_shouting():
    ship_out = to_str(ship.render_ship(_task(branch="b"), "push", "pr", ""))
    assert "ready" in ship_out
    assert "READY" not in ship_out

    findings = to_str(
        gate.render_findings([Finding(id="f", severity="blocking", location="a", message="m")])
    )
    assert "blocking" in findings
    assert "BLOCKING" not in findings

    resolved = to_str(
        intake.render_intake(
            _task(decisions=[Decision(id="d", question="q?", severity="blocking", approved=True)]),
            can_run=True,
        )
    )
    assert "Resolved" in resolved
    assert "RESOLVED" not in resolved
    assert "accepted as-is" in resolved  # the surface word, not internal "blessed"
    assert "blessed" not in resolved


def test_check_passing_rows_carry_meaning_with_glyph_not_only_color():
    # A passing receipt row is not green-washed; the ✓ glyph carries it (no color tag
    # in the no-color render, the glyph still reads).
    out = to_str(
        receipt.render_receipt_digest(_task(checks=[CheckResult(name="tests", passed=True)]))
    )
    assert "✓ checks (1/1)" in out


def test_renderer_style_literals_resolve():
    # Rule 8 / §3.4: Rich silently renders an UNKNOWN style name as unstyled (never
    # raises), so a typo'd style="blocekr" or a raw-color literal that bypassed the theme
    # would ship invisibly with no failing test. Enforce: every literal style="..." across
    # format/ + cli/ resolves — a KAGAN_THEME name OR a Rich-parseable attr/color.
    import re

    from rich.style import Style

    theme_names = set(KAGAN_THEME.styles)
    base = Path(__file__).resolve().parents[3] / "src" / "kagan"
    bad: list[str] = []
    for sub in ("format", "cli"):
        for py in (base / sub).glob("*.py"):
            for m in re.finditer(r"""style=["']([^"']+)["']""", py.read_text(encoding="utf-8")):
                literal = m.group(1)
                for tok in literal.split():
                    if tok in theme_names:
                        continue
                    try:
                        Style.parse(tok)
                    except Exception:  # any parse failure here means an invalid style name
                        bad.append(f"{py.name}: {literal!r} (token {tok!r})")
    assert not bad, f"unresolvable style names (typo or raw-color bypass): {bad}"
