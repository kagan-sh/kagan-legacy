from pathlib import Path

import pytest

from kagan.core.enums import TaskState
from kagan.core.errors import ValidationError
from kagan.core.ledger import Ledger
from kagan.core.models import Task


def test_save_and_load_task(tmp_path: Path):
    ledger = Ledger(tmp_path)
    ledger.save_task(Task(id="t-1", title="Add feature", state=TaskState.RUNNING))

    loaded = ledger.load_task("t-1")
    assert loaded is not None
    assert loaded.title == "Add feature"
    assert loaded.state == TaskState.RUNNING


def test_state_file_is_json(tmp_path: Path):
    # P1: state is state.json, not yaml.
    ledger = Ledger(tmp_path)
    ledger.save_task(Task(id="t-1", title="One"))
    assert (tmp_path / "t-1" / "state.json").exists()
    assert not (tmp_path / "t-1" / "state.yaml").exists()


def test_list_task_ids_requires_marker(tmp_path: Path):
    # P3: a dir without state.json (e.g. a crashed .tmp) is not a phantom task.
    ledger = Ledger(tmp_path)
    ledger.save_task(Task(id="t-1", title="One"))
    ledger.save_task(Task(id="t-2", title="Two"))
    (tmp_path / "orphan").mkdir()
    assert sorted(ledger.list_task_ids()) == ["t-1", "t-2"]


def test_append_event_is_jsonl(tmp_path: Path):
    ledger = Ledger(tmp_path)
    ledger.append_event("t-1", {"type": "created"})
    ledger.append_event("t-1", {"type": "transition"})
    events = ledger.read_events("t-1")
    assert [e["type"] for e in events] == ["created", "transition"]


def test_read_events_tolerates_torn_last_line(tmp_path: Path):
    # P2: a crash mid-append leaves a partial line; replay must not crash.
    ledger = Ledger(tmp_path)
    ledger.append_event("t-1", {"type": "created"})
    (tmp_path / "t-1" / "events.jsonl").open("a").write('{"type": "tor')
    assert [e["type"] for e in ledger.read_events("t-1")] == ["created"]


def test_load_missing_task_returns_none(tmp_path: Path):
    assert Ledger(tmp_path).load_task("missing") is None


def test_save_is_atomic_no_temp_left(tmp_path: Path):
    ledger = Ledger(tmp_path)
    ledger.save_task(Task(id="t-1", title="One"))
    # mkstemp-then-replace must leave no partial file behind (P1).
    assert not list((tmp_path / "t-1").glob("*.tmp"))


def test_bad_id_rejected_before_path_join(tmp_path: Path):
    # P3: regex blocks ../ traversal.
    ledger = Ledger(tmp_path)
    with pytest.raises(ValidationError):
        ledger.load_task("../etc")
    with pytest.raises(ValidationError):
        ledger.save_task(Task(id="../evil", title="x"))
