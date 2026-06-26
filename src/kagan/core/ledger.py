"""Per-task file ledger: atomic state.json + append-only events.jsonl.

Stdlib only (json, os, pathlib, re, tempfile). No database (TUI-LEDGER-04).
Harness is the single writer (ADR-0001), so no per-task lock is needed.
Implements _patterns.md P1 (atomic write), P2 (append-only log), P3 (per-task
dir + id validation).
"""

import contextlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kagan.core.errors import ValidationError
from kagan.core.models import Task

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,24}$")  # P3: blocks ../ traversal


def _fsync_dir(directory: Path) -> None:
    """fsync a directory so a rename/create inside it is durable on crash (P1).

    Without this the file is fsynced but its directory entry may not be, so a
    "succeeded" state.json can vanish on power-loss — the one unrecoverable loss
    for a single-source-of-truth ledger. Best-effort: some filesystems reject a
    directory fsync, which must never become a new crash."""
    with contextlib.suppress(OSError):
        fd = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Ledger:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, task_id: str) -> Path:
        if not _ID_RE.match(task_id):
            raise ValidationError("task_id", f"invalid task id: {task_id!r}")
        return self.root / task_id

    def list_task_ids(self) -> list[str]:
        return sorted(
            p.name for p in self.root.iterdir() if p.is_dir() and (p / "state.json").exists()
        )

    def load_task(self, task_id: str) -> Task | None:
        path = self._dir(task_id) / "state.json"
        if not path.exists():
            return None
        return Task.model_validate_json(path.read_text())

    def save_task(self, task: Task) -> None:
        directory = self._dir(task.id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "state.json"
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")  # same FS => atomic replace
        try:
            with os.fdopen(fd, "w") as f:
                f.write(task.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            _fsync_dir(directory)  # make the rename durable, not just the file (P1)
        except BaseException:  # clean orphan on Ctrl-C (P1)
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def append_event(self, task_id: str, event: dict[str, Any]) -> None:
        directory = self._dir(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        event.setdefault("ts", datetime.now(UTC).isoformat())  # delta boundary for the Inbox
        path = directory / "events.jsonl"
        created = not path.exists()
        with path.open("a") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        # Only fsync the dir when the log file is newly created — an append to an
        # existing file changes no directory entry, so fsyncing per-append would
        # slow the hot path for nothing.
        if created:
            _fsync_dir(directory)

    def read_events(self, task_id: str) -> list[dict[str, Any]]:
        path = self._dir(task_id) / "events.jsonl"
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a torn last line from a crash mid-append (P2)
        return out
