import yaml

from kagan.core.enums import TaskState
from kagan.core.models import (
    CheckResult,
    Decision,
    DriftConcern,
    Finding,
    NeedsYou,
    SmokeTest,
    Task,
)


def test_task_defaults():
    task = Task(id="t-1", title="Add feature")
    assert task.state == TaskState.INTAKE
    assert task.base_branch == "main"
    assert task.decisions == []
    assert task.findings == []
    assert task.smoke_tests == []
    assert task.ports == {}
    assert task.checks == []
    assert task.not_covered == []
    assert task.drift is False
    assert task.needs_you is None
    assert task.understanding is None
    assert task.last_viewed_at is None


def test_decision_defaults_to_unanswered():
    # can_run (test_tasks) treats `answer is None and not approved` as an open
    # blocking decision; pin those defaults so a model change that silently
    # unlocks the run gate fails here.
    d = Decision(id="d-1", question="Which base branch?", severity="blocking", options=["main"])
    assert d.answer is None
    assert d.approved is False


def test_finding_verdict_and_reply_default_none():
    # TUI-GATE-05: severity-tagged finding, verdict + reply.
    f = Finding(id="f-1", severity="nit", location="app.py:10", message="typo")
    assert f.verdict is None
    assert f.reply is None


def test_smoke_test_defaults_to_unverified():
    # TUI-GATE-08: verify_smoke_test (test_tasks) flips this; a model that
    # defaulted verified=True would pass the gate without a human check.
    assert SmokeTest(id="s-1", behaviour="login works", service="web").verified is False


def test_smoke_test_service_optional():
    # MCP-SMOKE-02: "where applicable" — service may be absent.
    assert SmokeTest(id="s-2", behaviour="config parses").service is None


def test_needs_you_and_check_result():
    # MCP-INTAKE-02 / TUI-GATE: structured mid-run question + a CI/check line.
    n = NeedsYou(reason="ambiguous scope", question="Which API?")
    assert n.context == ""
    c = CheckResult(name="pytest", passed=False)
    assert c.detail == ""


def test_task_model_dump_is_json_safe():
    # P1: model_dump(mode="json") converts enum/Path/datetime — must not raise.
    from pathlib import Path

    task = Task(id="t-1", title="x", worktree_path=Path("/tmp/wt"))
    dumped = task.model_dump(mode="json")
    assert dumped["state"] == "intake"
    assert dumped["worktree_path"] == "/tmp/wt"
    assert isinstance(dumped["created_at"], str)


def test_task_report_fields_default():
    # MCP-DRIFT-02 / MCP-DONE-01: report channels start empty so a fresh task
    # carries no phantom drift concern and no premature done hint.
    task = Task(id="t-1", title="Add feature")
    assert task.drift_concerns == []
    assert task.done_reported is False


def test_drift_concern_defaults():
    # MCP-DRIFT-02: a fresh agent-reported concern is unacknowledged until a human
    # clears it; an unlocated concern is allowed (the agent may not know the file).
    concern = DriftConcern(id="d-1", message="Edited out of scope")
    assert concern.location is None
    assert concern.acknowledged is False


def test_task_report_yaml_round_trip():
    # P1/TUI-LEDGER-02: report payloads survive the JSON persistence round-trip so
    # the stateless TUI renders intake/needs-you/drift/done straight from disk.
    task = Task(
        id="t-1",
        title="Add feature",
        understanding="Add dark mode",
        smoke_tests=[SmokeTest(id="st-1", behaviour="Check it")],
        needs_you=NeedsYou(reason="scope", question="Which?"),
        drift_concerns=[DriftConcern(id="d-1", message="Scope issue")],
        done_reported=True,
    )
    loaded = Task.model_validate(yaml.safe_load(yaml.safe_dump(task.model_dump(mode="json"))))
    assert loaded.understanding == "Add dark mode"
    assert len(loaded.smoke_tests) == 1
    assert loaded.needs_you is not None
    assert loaded.needs_you.reason == "scope"
    assert len(loaded.drift_concerns) == 1
    assert loaded.done_reported is True
