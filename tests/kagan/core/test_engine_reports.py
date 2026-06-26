"""The `.kagan/ask` file channel applies through the SAME single-writer methods
the MCP tools use — one apply path, both transports converge. These lock the two
bugs the prior divergent `_apply_report` carried: needs_you must NOT transition to
PR_OPEN, and agent-self-reported drift is an advisory DriftConcern, not a blocking
Finding (MCP-DRIFT-02)."""

from pathlib import Path

from kagan.core import Harness
from kagan.core.enums import TaskState
from kagan.core.models import ReportMessage


def _core_with_task(tmp_path: Path) -> tuple[Harness, str]:
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    core._tasks.transition(task.id, TaskState.RUNNING)
    return core, task.id


def test_file_needs_you_persists_without_pr_open_transition(tmp_path: Path):
    core, tid = _core_with_task(tmp_path)
    core._apply_report(
        tid, ReportMessage(type="needs_you", payload={"reason": "scope", "question": "which?"})
    )
    task = core.get_task(tid)
    assert task.needs_you is not None and task.needs_you.question == "which?"
    assert task.state is TaskState.RUNNING  # NOT PR_OPEN — a question is not an open PR
    core.close()


def test_file_drift_is_advisory_concern_not_blocking_finding(tmp_path: Path):
    core, tid = _core_with_task(tmp_path)
    core._apply_report(
        tid, ReportMessage(type="drift", payload={"reason": "edited api.py", "location": "api.py"})
    )
    task = core.get_task(tid)
    assert len(task.drift_concerns) == 1  # advisory (MCP-DRIFT-02)
    assert not any(f.severity == "blocking" for f in task.findings)  # not the harness's blocker
    core.close()


def test_file_intake_decisions_set_understanding(tmp_path: Path):
    core, tid = _core_with_task(tmp_path)
    core._apply_report(
        tid,
        ReportMessage(
            type="intake_decisions",
            payload={
                "understanding": "add dark mode",
                "decisions": [{"question": "which file?", "severity": "blocking"}],
            },
        ),
    )
    task = core.get_task(tid)
    assert task.understanding == "add dark mode"
    assert any(d.severity == "blocking" for d in task.decisions)
    core.close()


def test_file_smoke_tests_map_text_to_behaviour(tmp_path: Path):
    core, tid = _core_with_task(tmp_path)
    core._apply_report(
        tid, ReportMessage(type="smoke_tests", payload={"items": [{"text": "open /health"}]})
    )
    task = core.get_task(tid)
    assert [s.behaviour for s in task.smoke_tests] == ["open /health"]
    core.close()
