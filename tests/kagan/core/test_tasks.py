import asyncio
from pathlib import Path

import pytest

from kagan.core import Harness
from kagan.core.enums import TaskState
from kagan.core.errors import NotFoundError, ValidationError
from kagan.core.ledger import Ledger
from kagan.core.models import CheckResult
from kagan.core.tasks import TaskService, _is_substantive


def _service(tmp_path: Path) -> TaskService:
    return TaskService(Ledger(tmp_path / "tasks"))


_SUBSTANTIVE = "Rounds half-up so totals never drift; could break on negative inputs."


def _answer_all(core: Harness, task_id: str) -> None:
    # Answer every required comprehension prompt for the task's tier substantively.
    from kagan.core.comprehension import required_keys

    task = core.get_task(task_id)
    assert task is not None
    for key in required_keys(task.risk):
        core.record_comprehension(task_id, key, _SUBSTANTIVE)


def test_blocking_decision_locks_run_until_answered(tmp_path: Path):
    # TUI-INTAKE-03/04: run locked while a blocking decision is open; answer pins it.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    task = core.add_decision(
        task.id, question="Base branch?", severity="blocking", options=["main", "dev"]
    )
    assert not core.can_run(task.id)

    task = core.answer_decision(task.id, task.decisions[0].id, answer="main")
    assert task.decisions[0].answer == "main"
    assert core.can_run(task.id)
    core.close()


def test_approving_a_blocking_decision_unlocks_run(tmp_path: Path):
    # approved (took the agent's assumption) counts as explicitly resolved.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    task = core.add_decision(task.id, question="?", severity="blocking")
    task = core.answer_decision(task.id, task.decisions[0].id, answer="", approved=True)
    assert core.can_run(task.id)
    core.close()


def test_disagree_finding_requires_reply_and_blocks_approve(tmp_path: Path):
    # TUI-GATE-05: open blocking finding locks approve; disagree needs a reply.
    # The comprehension note is pre-recorded here so this test isolates the
    # findings lock; the comprehension lock itself is covered separately (lever 1).
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    _answer_all(core, task.id)
    task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    assert not core.can_approve(task.id)

    with pytest.raises(ValueError):
        core.set_verdict(task.id, task.findings[0].id, verdict="disagree", reply=None)

    task = core.set_verdict(task.id, task.findings[0].id, verdict="disagree", reply="not a bug")
    assert core.can_approve(task.id)
    core.close()


def test_comprehension_gate_blocks_approve_until_substantive_note(tmp_path: Path):
    # Lever 1 (the load-bearing test): even with every blocking finding adjudicated,
    # approve stays locked until the human records a real own-words rationale. The
    # gate must be ABLE to fail — empty/trivial notes keep it locked.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    core.set_verdict(task.id, task.findings[0].id, verdict="agree")
    # Findings cleared, but no note yet -> still locked.
    assert not core.can_approve(task.id)

    # A trivial / placeholder answer does not clear the gate.
    core.record_comprehension(task.id, "postcondition", "ok")
    assert not core.can_approve(task.id)

    # One substantive answer of the two medium prompts is still not enough.
    core.record_comprehension(task.id, "postcondition", _SUBSTANTIVE)
    assert not core.can_approve(task.id)
    # A thin second answer keeps it locked.
    core.record_comprehension(task.id, "what_breaks", "n/a")
    assert not core.can_approve(task.id)

    # Both prompts substantively answered flips it true.
    core.record_comprehension(task.id, "what_breaks", _SUBSTANTIVE)
    assert core.can_approve(task.id)
    core.close()


def test_low_risk_approves_without_a_comprehension_note(tmp_path: Path):
    # Lever 4 x lever 1: low risk is fast-approve — with blocking findings cleared,
    # approve unlocks WITHOUT a comprehension note (DESIGN L175). This is the
    # ceremony-scaling the spine exists for; it fails if low still demands the note.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Tweak docs")
    core.update_task(task.id, risk="low")
    task = core.add_finding(task.id, severity="blocking", location="docs/x.md", message="typo")
    assert not core.can_approve(task.id)  # the findings lock still holds for every tier
    core.set_verdict(task.id, task.findings[0].id, verdict="agree")
    # No comprehension note recorded, yet low risk unlocks.
    assert core.can_approve(task.id)
    core.close()


def test_failed_required_check_blocks_approve_even_at_low_risk(tmp_path: Path):
    # Machine checks are still a low-risk gate: "fast approve" cannot certify a
    # failed declared check as accepted.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Tweak docs")
    core.update_task(
        task.id,
        risk="low",
        checks=[CheckResult(name="fmt", passed=False, detail="rc=1")],
    )
    assert not core.can_approve(task.id)
    core.update_task(task.id, checks=[CheckResult(name="fmt", passed=True)])
    assert core.can_approve(task.id)
    core.close()


def test_medium_and_high_risk_still_require_the_comprehension_note(tmp_path: Path):
    # The comprehension lock is RELAXED only for low risk; medium and high keep it,
    # so making it tier-conditional does not silently weaken the existing gate for
    # the default (medium) tier the Phase-1 tests encode.
    for tier in ("medium", "high"):
        core = Harness(data_dir=tmp_path / tier)
        task = core.create_task("Touch auth")
        core.update_task(task.id, risk=tier)
        task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
        core.set_verdict(task.id, task.findings[0].id, verdict="agree")
        assert not core.can_approve(task.id), tier  # findings cleared but answers missing
        _answer_all(core, task.id)
        assert core.can_approve(task.id), tier
        core.close()


def test_high_risk_locked_until_all_five_prompts_answered(tmp_path: Path):
    # High risk demands the full 5-prompt set; approve stays locked until the LAST
    # required key carries a substantive answer (each partial step keeps it locked).
    from kagan.core.comprehension import required_keys

    core = Harness(data_dir=tmp_path)
    task = core.create_task("Touch auth")
    core.update_task(task.id, risk="high")
    task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    core.set_verdict(task.id, task.findings[0].id, verdict="agree")
    keys = required_keys("high")
    assert len(keys) == 5
    for key in keys[:-1]:
        core.record_comprehension(task.id, key, _SUBSTANTIVE)
        assert not core.can_approve(task.id)  # still missing the last prompt
    core.record_comprehension(task.id, keys[-1], _SUBSTANTIVE)
    assert core.can_approve(task.id)
    core.close()


def test_short_generated_prompts_fall_back_to_static_floor(tmp_path: Path):
    # Rule 8: a high-risk task with a too-short generated set still demands every
    # static prompt answered — the floor check must not let approve unlock early.
    from kagan.core.comprehension import required_keys

    core = Harness(data_dir=tmp_path)
    task = core.create_task("Touch auth")
    core.update_task(
        task.id,
        risk="high",
        comprehension_prompts=[("postcondition", "Only one generated prompt?")],
    )
    task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    core.set_verdict(task.id, task.findings[0].id, verdict="agree")
    core.record_comprehension(task.id, "postcondition", _SUBSTANTIVE)
    assert not core.can_approve(task.id)
    for key in required_keys("high")[1:]:
        core.record_comprehension(task.id, key, _SUBSTANTIVE)
    assert core.can_approve(task.id)
    core.close()


def test_empty_generated_prompts_on_high_risk_still_demand_static_set(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Touch auth")
    core.update_task(task.id, risk="high", comprehension_prompts=[])
    task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    core.set_verdict(task.id, task.findings[0].id, verdict="agree")
    assert not core.can_approve(task.id)
    _answer_all(core, task.id)
    assert core.can_approve(task.id)
    core.close()


def test_can_approve_uses_generated_prompts_when_at_floor(tmp_path: Path):
    generated = [
        ("postcondition", "How does billing retry after this diff?"),
        ("what_breaks", "What race could still lose a charge?"),
    ]
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Billing retry")
    core.update_task(task.id, comprehension_prompts=generated)
    task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    core.set_verdict(task.id, task.findings[0].id, verdict="agree")
    core.record_comprehension(task.id, "postcondition", _SUBSTANTIVE)
    assert not core.can_approve(task.id)
    core.record_comprehension(task.id, "what_breaks", _SUBSTANTIVE)
    assert core.can_approve(task.id)
    core.close()


_MEDIUM_GENERATED = [
    ("postcondition", "How does billing retry after this diff?"),
    ("what_breaks", "What race could still lose a charge?"),
]


def test_record_comprehension_prompts_populates_task(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Billing retry")
    task = core.record_comprehension_prompts(task.id, _MEDIUM_GENERATED)
    assert task.comprehension_prompts == _MEDIUM_GENERATED
    from kagan.core.comprehension import prompts_for_task

    assert prompts_for_task(task) == _MEDIUM_GENERATED
    core.close()


def test_record_comprehension_prompts_caps_extras(tmp_path: Path):
    from kagan.core.comprehension import required_keys

    core = Harness(data_dir=tmp_path)
    task = core.create_task("Touch auth")
    core.update_task(task.id, risk="high")
    extras = [
        ("postcondition", "q1"),
        ("delta", "q2"),
        ("dependencies", "q3"),
        ("security", "q4"),
        ("gotchas", "q5"),
        ("extra", "q6"),
    ]
    task = core.record_comprehension_prompts(task.id, extras)
    assert len(task.comprehension_prompts) == len(required_keys("high"))
    assert task.comprehension_prompts == extras[:5]
    core.close()


def test_record_comprehension_prompts_short_leaves_empty_and_gate_demands_static(
    tmp_path: Path,
):
    from kagan.core.comprehension import required_keys

    core = Harness(data_dir=tmp_path)
    task = core.create_task("Touch auth")
    core.update_task(task.id, risk="high")
    task = core.record_comprehension_prompts(
        task.id, [("postcondition", "Only one generated prompt?")]
    )
    assert task.comprehension_prompts == []
    task = core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    core.set_verdict(task.id, task.findings[0].id, verdict="agree")
    core.record_comprehension(task.id, "postcondition", _SUBSTANTIVE)
    assert not core.can_approve(task.id)
    for key in required_keys("high")[1:]:
        core.record_comprehension(task.id, key, _SUBSTANTIVE)
    assert core.can_approve(task.id)
    core.close()


def test_record_comprehension_prompts_skips_malformed_and_stores_rest(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Billing retry")
    mixed = [
        {"key": "postcondition", "question": "How does retry behave in src/billing.py?"},
        {"question": "missing key"},
        ("what_breaks", "What race could still lose a charge?"),
    ]
    task = core.record_comprehension_prompts(task.id, mixed)
    assert task.comprehension_prompts == [
        ("postcondition", "How does retry behave in src/billing.py?"),
        ("what_breaks", "What race could still lose a charge?"),
    ]
    core.close()


def test_record_comprehension_prompts_emits_event(tmp_path: Path):
    svc = _service(tmp_path)
    task = svc.create("Billing retry")
    svc.record_comprehension_prompts(task.id, _MEDIUM_GENERATED)
    events = Ledger(tmp_path / "tasks").read_events(task.id)
    assert any(
        e.get("type") == "comprehension_prompts_recorded" and e.get("count") == 2 for e in events
    )
    reloaded = Ledger(tmp_path / "tasks").load_task(task.id)
    assert reloaded is not None
    assert reloaded.comprehension_prompts == _MEDIUM_GENERATED


def test_record_comprehension_emits_event(tmp_path: Path):
    # The gate measures substance, not just length: repeated single tokens and
    # multi-word placeholders are trivial and must stay locked (else it is theater).
    for trivial in ("", "   ", "ok", "n/a", "looks good to me", "a a a a a", ". . . . ."):
        assert not _is_substantive(trivial), trivial
    assert _is_substantive("Rounds half-up so totals never drift on retries.")


def test_substantive_note_alone_does_not_clear_open_blocking_finding(tmp_path: Path):
    # Both locks must hold: a real note cannot approve past an unadjudicated blocking
    # finding (so the comprehension gate is additive, not a bypass of TUI-GATE-05).
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    core.add_finding(task.id, severity="blocking", location="a.py:1", message="bug")
    _answer_all(core, task.id)
    assert not core.can_approve(task.id)
    core.close()


def test_record_comprehension_emits_event(tmp_path: Path):
    # The note routes through the same _commit chokepoint as the other record_*
    # methods, so it lands in the event log and is auditable.
    svc = _service(tmp_path)
    task = svc.create("Add feature")
    svc.record_comprehension(task.id, "postcondition", _SUBSTANTIVE)
    events = Ledger(tmp_path / "tasks").read_events(task.id)
    assert any(
        e.get("type") == "comprehension_recorded" and e.get("key") == "postcondition"
        for e in events
    )
    reloaded = Ledger(tmp_path / "tasks").load_task(task.id)
    assert reloaded is not None
    assert reloaded.comprehension == {"postcondition": _SUBSTANTIVE}


def test_smoke_test_added_and_verified(tmp_path: Path):
    # TUI-GATE-08 / MCP-SMOKE-02.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    task = core.add_smoke_test(task.id, behaviour="login works", service="web")
    assert task.smoke_tests[0].verified is False
    task = core.verify_smoke_test(task.id, task.smoke_tests[0].id)
    assert task.smoke_tests[0].verified is True
    core.close()


def test_unknown_task_raises_not_found(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    with pytest.raises(NotFoundError):
        core.transition_task("missing", TaskState.RUNNING)
    core.close()


def test_update_task_persists_and_reloads(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    core.update_task(task.id, understanding="use OAuth", branch="kg/x")
    reloaded = core.get_task(task.id)
    assert reloaded is not None
    assert reloaded.understanding == "use OAuth"
    assert reloaded.branch == "kg/x"
    core.close()


def test_update_task_rejects_bad_value_without_corrupting_disk(tmp_path: Path):
    # A bad value must fail in update_task, not silently persist and brick reload.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    with pytest.raises(ValueError):  # pydantic ValidationError is a ValueError
        core.update_task(task.id, state="NOT_A_STATE")
    # task still loads — nothing invalid reached disk.
    assert core.get_task(task.id).state == TaskState.INTAKE
    core.close()


def test_update_task_rejects_unknown_field(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    with pytest.raises(ValidationError):
        core.update_task(task.id, titel="typo")
    core.close()


def test_record_intake_decisions_replaces_existing(tmp_path: Path):
    # MCP-INTAKE-02: re-reporting intake overwrites the prior set, so a corrected
    # understanding never leaves stale decisions behind.
    svc = _service(tmp_path)
    task = svc.create("Add feature")
    task = svc.record_intake_decisions(
        task.id,
        understanding="Add a dark mode toggle",
        decisions=[
            {"question": "Which CSS file?", "severity": "blocking", "options": ["a.css", "b.css"]},
            {"question": "Use CSS variables?", "severity": "question"},
        ],
    )
    assert task.understanding == "Add a dark mode toggle"
    assert len(task.decisions) == 2
    assert task.decisions[0].severity == "blocking"
    assert task.decisions[0].options == ["a.css", "b.css"]

    task = svc.record_intake_decisions(
        task.id,
        understanding="Add light mode too",
        decisions=[{"question": "Both modes?", "severity": "blocking"}],
    )
    assert task.understanding == "Add light mode too"
    assert len(task.decisions) == 1


def test_record_smoke_tests_replaces(tmp_path: Path):
    # MCP-SMOKE-01/02: reported behaviours replace the set and carry the optional
    # service reference through verbatim.
    svc = _service(tmp_path)
    task = svc.create("Add feature")
    task = svc.record_smoke_tests(
        task.id,
        tests=[
            {"behaviour": "Toggle dark mode", "service": "web"},
            {"behaviour": "Refresh persists choice"},
        ],
    )
    assert len(task.smoke_tests) == 2
    assert task.smoke_tests[0].behaviour == "Toggle dark mode"
    assert task.smoke_tests[0].service == "web"
    assert task.smoke_tests[1].service is None


def test_record_drift_appends(tmp_path: Path):
    # MCP-DRIFT-02: each self-reported concern accumulates; one report never
    # clobbers an earlier one (the human triages the whole list).
    svc = _service(tmp_path)
    task = svc.create("Add feature")
    svc.record_drift(task.id, message="Edited api.py without blessing")
    task = svc.record_drift(task.id, message="Added new dependency")
    assert len(task.drift_concerns) == 2
    assert task.drift_concerns[0].message == "Edited api.py without blessing"


def test_record_done(tmp_path: Path):
    # MCP-DONE-01: the completion hint flips a persisted flag the TUI reads.
    svc = _service(tmp_path)
    task = svc.create("Add feature")
    task = svc.record_done(task.id)
    assert task.done_reported is True


async def test_needs_you_persists_then_blocks_until_answered(tmp_path: Path):
    # MCP-NEEDS-02/04 + P9: the pending question is on disk BEFORE the await blocks,
    # so a crash mid-question is reconstructable; answering unblocks and clears it.
    svc = _service(tmp_path)
    task = svc.create("Add feature")

    waiter = asyncio.ensure_future(
        svc.record_needs_you(
            task.id, reason="missing-context", question="Which API key?", context="env unclear"
        )
    )
    await asyncio.sleep(0)
    reloaded = Ledger(tmp_path / "tasks").load_task(task.id)
    assert reloaded is not None
    assert reloaded.needs_you is not None
    assert reloaded.needs_you.reason == "missing-context"
    assert not waiter.done()  # still blocked

    svc.answer_needs_you(task.id, "Use KAGAN_API_KEY")
    assert await waiter == "Use KAGAN_API_KEY"
    # Answering clears the pending question.
    loaded = Ledger(tmp_path / "tasks").load_task(task.id)
    assert loaded is not None
    assert loaded.needs_you is None
