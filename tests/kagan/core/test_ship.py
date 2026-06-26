from pathlib import Path

import pytest

from kagan.core.enums import TaskState
from kagan.core.errors import InvalidTransitionError, NotFoundError
from kagan.core.ledger import Ledger
from kagan.core.models import Task
from kagan.core.ship import ShipService


def _svc(tmp_path: Path) -> tuple[ShipService, Ledger]:
    ledger = Ledger(tmp_path)
    return ShipService(ledger), ledger


def test_approve_from_review_marks_ready(tmp_path: Path):
    svc, ledger = _svc(tmp_path)
    ledger.save_task(Task(id="t-1", title="Add feature", state=TaskState.REVIEW))
    assert svc.approve("t-1").state == TaskState.READY


def test_approve_from_done_marks_ready(tmp_path: Path):
    svc, ledger = _svc(tmp_path)
    ledger.save_task(Task(id="t-1", title="Add feature", state=TaskState.DONE))
    assert svc.approve("t-1").state == TaskState.READY


def test_approve_from_intake_raises(tmp_path: Path):
    svc, ledger = _svc(tmp_path)
    ledger.save_task(Task(id="t-1", title="Add feature", state=TaskState.INTAKE))
    with pytest.raises(InvalidTransitionError):
        svc.approve("t-1")


def test_mark_pushed_from_ready_marks_pr_open(tmp_path: Path):
    svc, ledger = _svc(tmp_path)
    ledger.save_task(Task(id="t-1", title="Add feature", state=TaskState.READY, branch="kagan/t-1"))
    assert svc.mark_pushed("t-1").state == TaskState.PR_OPEN


def test_mark_pushed_appends_pushed_event(tmp_path: Path):
    # TUI-SHIP-04: the local-mirror plan's watcher subscribes to the `pushed` event,
    # so mark_pushed must record it on the ledger, not just flip in-memory state.
    svc, ledger = _svc(tmp_path)
    ledger.save_task(Task(id="t-1", title="Add feature", state=TaskState.READY, branch="kagan/t-1"))
    svc.mark_pushed("t-1")
    events = ledger.read_events("t-1")
    assert any(e["type"] == "pushed" and e["to"] == TaskState.PR_OPEN.value for e in events)


def test_mark_pushed_from_intake_raises(tmp_path: Path):
    svc, ledger = _svc(tmp_path)
    ledger.save_task(Task(id="t-1", title="Add feature", state=TaskState.INTAKE))
    with pytest.raises(InvalidTransitionError):
        svc.mark_pushed("t-1")


def test_missing_task_raises_not_found(tmp_path: Path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(NotFoundError):
        svc.approve("missing")


def test_push_command_names_kagan_branch_and_has_no_force(tmp_path: Path):
    # Q1: the push command names the branch kagan/<task-id>. Q2/TUI-SHIP-03: never force.
    svc, _ = _svc(tmp_path)
    task = Task(id="t-1", title="Add feature", branch="kagan/t-1")
    cmd = svc.push_command(task)
    assert cmd == "git push -u origin kagan/t-1"
    assert "--force" not in cmd
    assert "-f" not in cmd.split()


def test_pr_command(tmp_path: Path):
    svc, _ = _svc(tmp_path)
    task = Task(id="t-1", title="Add feature", branch="kagan/t-1", base_branch="main")
    assert svc.pr_command(task) == 'gh pr create --base main --head kagan/t-1 --title "Add feature"'


def test_command_without_branch_raises(tmp_path: Path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.push_command(Task(id="t-1", title="Add feature"))
