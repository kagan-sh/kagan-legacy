"""Lever 8 retro: append_learning is the ONLY AGENTS.md writer and must never
write on its own — the surface gates it behind an explicit human confirm. These
prove the file IS created/appended on confirm and is a no-op on an empty line,
and that summarize_learnings distills a candidate purely from the Task model.
"""

import pytest

from kagan.core.models import Decision, DriftConcern, Finding, Task
from kagan.core.reports import summarize_learnings
from kagan.core.retro import append_learning


def test_append_creates_agents_md_with_heading_and_dated_bullet(tmp_path):
    path = append_learning(tmp_path, "docs are generated — never hand-edit api.md")
    assert path == tmp_path / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    assert "## kagan learnings" in text
    assert "never hand-edit api.md" in text
    assert text.rstrip().endswith("never hand-edit api.md")


def test_append_does_not_clobber_existing_human_content(tmp_path):
    # A repo with a hand-written AGENTS.md must keep its content; the learning is
    # appended under the stable heading, never a rewrite.
    path = tmp_path / "AGENTS.md"
    path.write_text("# House rules\n\nUse tabs.\n", encoding="utf-8")
    append_learning(tmp_path, "first learning")
    append_learning(tmp_path, "second learning")
    text = path.read_text(encoding="utf-8")
    assert "Use tabs." in text  # human content survived
    assert text.count("## kagan learnings") == 1  # heading written once, not per-append
    assert "first learning" in text and "second learning" in text


def test_append_uses_local_date_not_utc(tmp_path, monkeypatch):
    # B23: the dated bullet is a human-facing stamp in the committed decision log, so
    # it must be the LOCAL date — a dev east of UTC after local midnight saw yesterday.
    from datetime import datetime as real_datetime

    import kagan.core.retro as retro

    class _Clock:
        @staticmethod
        def now(tz=None):
            # Local midnight+ is already the next day; the UTC instant is still yesterday.
            return real_datetime(2026, 6, 26, 22, 30) if tz else real_datetime(2026, 6, 27, 0, 30)

    monkeypatch.setattr(retro, "datetime", _Clock)
    text = append_learning(tmp_path, "openapi.json is the source of truth").read_text()
    assert "2026-06-27" in text  # local date
    assert "2026-06-26" not in text  # not the UTC date


def test_append_refuses_empty_line(tmp_path):
    # Guards the surface contract: an empty/whitespace edit must never reach a
    # silent write — it raises so the no-op stays a no-op upstream.
    with pytest.raises(ValueError):
        append_learning(tmp_path, "   ")


def test_summarize_learnings_distills_decisions_and_drift():
    task = Task(
        id="t",
        title="t",
        decisions=[Decision(id="d", question="precedence?", severity="blocking", answer="proper")],
        drift_concerns=[DriftConcern(id="c", message="f64 overflow -> inf")],
        findings=[
            Finding(id="f1", severity="blocking", location="eval.rs", message="x"),
            Finding(id="f2", severity="question", location="eval.rs", message="y"),
        ],
    )
    line = summarize_learnings(task)
    assert line is not None
    assert "precedence -> proper" in line
    assert "f64 overflow -> inf" in line
    assert "eval.rs" not in line  # raw finding locations are not learnings


def test_summarize_learnings_ignores_location_only_patterns():
    # #31: repeated rubric/repo finding locations are not substantive enough for
    # an AGENTS.md suggestion, and must not leak absolute local paths.
    task = Task(
        id="t",
        title="t",
        findings=[
            Finding(
                id="f1",
                severity="question",
                location=".",
                message="x",
            ),
            Finding(
                id="f2",
                severity="question",
                location="/Users/dev/yoyoyo/.kagan/review.md",
                message="y",
            ),
            Finding(
                id="f3",
                severity="question",
                location="/Users/dev/yoyoyo/.kagan/review.md",
                message="z",
            ),
        ],
    )

    assert summarize_learnings(task) is None


def test_summarize_learnings_returns_none_when_nothing_worth_recording():
    # Nothing resolved, no drift, no recurring finding -> no offer (opt-in, never
    # an empty bullet).
    assert summarize_learnings(Task(id="t", title="t")) is None
