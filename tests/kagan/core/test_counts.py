from kagan.core.counts import attention_counts
from kagan.core.enums import TaskState
from kagan.core.models import NeedsYou, Task


def _task(**kw) -> Task:
    return Task(id=kw.pop("id"), title=kw.pop("title", "t"), **kw)


def test_attention_counts_buckets_a_mixed_list():
    # TUI-SHELL-01: the header counts mirror the Inbox urgency buckets exactly, so
    # the operator sees the same "who needs me" totals the list is sorted by.
    tasks = [
        _task(id="d", state=TaskState.RUNNING, drift=True),
        _task(id="i", state=TaskState.INTAKE),  # intake counts as needs_you
        _task(
            id="ny",
            state=TaskState.RUNNING,
            needs_you=NeedsYou(reason="x", question="y"),
        ),
        _task(id="rv", state=TaskState.REVIEW),
        _task(id="rd", state=TaskState.READY),
        _task(id="run", state=TaskState.RUNNING),  # live
        _task(id="val", state=TaskState.VALIDATING),  # live
        _task(id="pr", state=TaskState.PR_OPEN),  # live
        _task(id="done", state=TaskState.DONE),  # in no bucket
    ]
    assert attention_counts(tasks) == {
        "drift": 1,
        "needs_you": 2,
        "review": 1,
        "ready": 1,
        "live": 3,
    }


def test_drift_task_is_not_double_counted_as_live():
    # A RUNNING task with drift is a drift task, not a live one — drift outranks the
    # raw state so the header's loudest bucket wins (mirrors the inbox _signal).
    counts = attention_counts([_task(id="d", state=TaskState.RUNNING, drift=True)])
    assert counts["drift"] == 1
    assert counts["live"] == 0
