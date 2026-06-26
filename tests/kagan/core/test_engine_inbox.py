from datetime import UTC, datetime, timedelta

from kagan.core import Harness
from kagan.core.enums import TaskState


def test_inbox_tasks_sorted_by_urgency(tmp_path):
    # TUI-INBOX-01: inbox_tasks composes list_tasks + ranking, intake outranks running.
    core = Harness(data_dir=tmp_path)
    core.create_task("Intake task")  # stays INTAKE
    running = core.create_task("Running task")
    core.transition_task(running.id, TaskState.RUNNING)

    items = core.inbox_tasks()
    # intake (rank 3) sorts above running (rank 8) per TUI-INBOX-01
    assert items[0].state is TaskState.INTAKE
    assert items[-1].state is TaskState.RUNNING
    core.close()


def test_touch_viewed_stamps_last_viewed(tmp_path):
    # TUI-INBOX-04: the one ledger write the Inbox triggers — stamps the delta boundary.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Task")
    assert task.last_viewed_at is None
    viewed = core.touch_viewed(task.id)
    assert viewed.last_viewed_at is not None
    core.close()


def test_running_task_gets_eta_from_history_and_resume_point(tmp_path):
    # TUI-INBOX-03/05: a running task shows a heartbeat ETA derived from finished-task
    # history and a one-line resume point from its last event. Fails if eta_seconds /
    # resume_point have no writer (both stay None and render empty).
    core = Harness(data_dir=tmp_path)

    # A finished task that ran ~10 minutes establishes the median.
    done = core.create_task("Done one")
    d = core.get_task(done.id)
    d.created_at = datetime.now(UTC) - timedelta(minutes=10)
    core._ledger.save_task(d)
    core.transition_task(done.id, TaskState.DONE)

    # A running task started ~2 minutes ago: ETA = median(~10m) - elapsed(~2m).
    run = core.create_task("Running")
    r = core.get_task(run.id)
    r.created_at = datetime.now(UTC) - timedelta(minutes=2)
    core._ledger.save_task(r)
    core.transition_task(run.id, TaskState.RUNNING)

    item = next(i for i in core.inbox_tasks() if i.task_id == run.id)
    assert item.eta is not None and item.eta != "running"  # a real estimate, not the fallback
    assert item.resume_point  # last event summary, one line
    assert "\n" not in item.resume_point
    core.close()


def test_running_task_without_history_has_no_fake_eta(tmp_path):
    # TUI-INBOX-03 (ponytail): no finished tasks => no median => show "running", never
    # an invented number. Fails if the deriver fabricates an ETA from thin air.
    core = Harness(data_dir=tmp_path)
    run = core.create_task("Running")
    core.transition_task(run.id, TaskState.RUNNING)
    item = next(i for i in core.inbox_tasks() if i.task_id == run.id)
    assert item.eta == "running"
    core.close()


def test_since_you_left_counts_real_ledger_events_after_view(tmp_path):
    # TUI-INBOX-04: delta is derived from real ledger events stamped after the view —
    # would silently read 0 if ledger events carried no `ts`.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Task")
    core.touch_viewed(task.id)  # boundary
    core.update_task(task.id, description="step 2")  # one real event after the view
    core.update_task(task.id, base_commit="abc123")  # another
    item = next(i for i in core.inbox_tasks() if i.task_id == task.id)
    assert item.since_you_left == "2 updates since you left"
    core.close()
