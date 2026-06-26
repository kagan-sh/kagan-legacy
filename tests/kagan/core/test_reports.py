from pathlib import Path

from kagan.core.models import Task
from kagan.core.reports import append_ask, detect_drift, read_ask


def test_append_and_read(tmp_path: Path):
    append_ask(tmp_path, {"type": "needs_you", "payload": {"question": "which?"}})
    msgs = read_ask(tmp_path)
    assert len(msgs) == 1
    assert msgs[0].type == "needs_you"


def test_read_offset_skips_seen(tmp_path: Path):
    append_ask(tmp_path, {"type": "smoke_tests", "payload": {}})
    append_ask(tmp_path, {"type": "done", "payload": {}})
    assert [m.type for m in read_ask(tmp_path, offset=1)] == ["done"]


def test_malformed_line_is_raw(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "ask").write_text("not json\n")
    assert read_ask(tmp_path)[0].type == "raw"


def test_file_outside_scope_is_drift():
    task = Task(id="t-1", title="x", scope=["src/**"])
    diff = "diff --git a/README.md b/README.md\n+line\n"
    findings = detect_drift(task, diff)
    assert len(findings) == 1
    assert findings[0].severity == "blocking"


def test_file_inside_scope_is_ok():
    task = Task(id="t-1", title="x", scope=["src/**"])
    diff = "diff --git a/src/foo.py b/src/foo.py\n+line\n"
    assert detect_drift(task, diff) == []


def test_protected_path_is_drift_even_in_scope():
    # An agent edit to the review contract is tampering: PROTECTED paths flag as
    # drift even when the scope glob would otherwise admit them. detect_drift never
    # strips protected paths (only the harvest path strips run-artifacts), so the
    # protection cannot be swallowed.
    task = Task(id="t-1", title="x", scope=[".kagan/**"])
    diff = "diff --git a/.kagan/repo.yaml b/.kagan/repo.yaml\n+evil: true\n"
    findings = detect_drift(task, diff)
    assert any("repo.yaml" in f.location and f.severity == "blocking" for f in findings)


def test_run_artifact_in_diff_is_not_protected_drift():
    # .kagan/ask is kagan's own report channel — a run-artifact, NOT a protected
    # path. detect_drift must not flag it as protected tampering (the harvest path
    # strips it from the diff before this runs). This fails if the old _PROTECTED
    # set (which mislabelled .kagan/ask as protected) creeps back.
    task = Task(id="t-1", title="x", scope=[".kagan/**"])
    diff = "diff --git a/.kagan/ask b/.kagan/ask\n+line\n"
    assert detect_drift(task, diff) == []


def test_no_scope_means_no_scope_drift():
    task = Task(id="t-1", title="x", scope=[])
    diff = "diff --git a/anything.py b/anything.py\n+line\n"
    assert detect_drift(task, diff) == []
