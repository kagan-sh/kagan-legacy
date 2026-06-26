"""needs-you renderer — the mid-run question chrome added in Phase 12c."""

from kagan.core.enums import TaskState
from kagan.core.models import NeedsYou, Task
from kagan.format import _symbols as sym
from kagan.format import needs_you
from tests.kagan.format._render import to_str


def _task(**kw) -> Task:
    return Task(id="t", title=kw.pop("title", "migrate-billing"), state=TaskState.RUNNING, **kw)


def test_needs_you_has_glyph_header_risk_and_question():
    # Phase 12c needs-you: the ● glyph, the title header with risk context, and the
    # question — the standard chrome the other views have, previously absent.
    task = _task(
        risk="high",
        needs_you=NeedsYou(
            reason="ambiguous", question="Which currency rounding?", context="src/billing"
        ),
    )
    out = to_str(needs_you.render_needs_you(task))
    assert sym.NEEDS_YOU in out  # the ● needs-you glyph
    assert "migrate-billing" in out  # the title header
    assert "high risk" in out  # risk context in the header
    assert "Which currency rounding?" in out
    assert "src/billing" in out  # the context line


def test_needs_you_without_question_is_calm_not_a_crash():
    out = to_str(needs_you.render_needs_you(_task()))
    assert "Nothing is waiting on you." in out
