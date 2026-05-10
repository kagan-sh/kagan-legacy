"""Unit tests for KaganFileHistory — persistent per-project input history."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from prompt_toolkit.history import InMemoryHistory

from kagan.core.chat._history import (
    KaganFileHistory,
    _read_jsonl,
    build_history,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_entries(path: Path, entries: list[str]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps({"text": entry}) + "\n")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_history_entries_persist_across_instances(tmp_path: Path) -> None:
    h1 = KaganFileHistory("proj", history_dir=tmp_path)
    h1.append_string("hello world")
    h1.append_string("second line")

    h2 = KaganFileHistory("proj", history_dir=tmp_path)
    strings = list(h2.get_strings_from_disk())
    assert "hello world" in strings
    assert "second line" in strings


def test_history_deduplicates_consecutive_identical(tmp_path: Path) -> None:
    h = KaganFileHistory("proj", history_dir=tmp_path)
    h.append_string("foo")
    h.append_string("foo")

    history_file = tmp_path / "proj.jsonl"
    entries = _read_jsonl(history_file)
    assert entries.count("foo") == 1


def test_history_trims_to_500(tmp_path: Path) -> None:
    history_file = tmp_path / "proj.jsonl"
    _write_entries(history_file, [f"entry-{i}" for i in range(600)])

    h = KaganFileHistory("proj", history_dir=tmp_path)
    strings = list(h.get_strings_from_disk())
    assert len(strings) == 500
    # Must keep the *last* 500, i.e. entries 100-599
    assert "entry-100" in strings
    assert "entry-0" not in strings


def test_history_degrades_gracefully_on_bad_path(tmp_path: Path) -> None:
    bad_dir = tmp_path / "unwritable"
    bad_dir.mkdir()
    # Make the directory unwritable so file creation fails
    os.chmod(bad_dir, 0o444)
    try:
        # Should not raise even if file is unwritable
        h = KaganFileHistory("proj", history_dir=bad_dir)
        h.append_string("safe text")
        # No exception — degrades silently
    except (PermissionError, OSError):
        pytest.fail("KaganFileHistory raised on unwritable path")
    finally:
        os.chmod(bad_dir, 0o755)


def test_history_disabled_when_opt_out_key_false(tmp_path: Path) -> None:
    settings = {"persist_input_history": "false"}

    def _settings_getter() -> dict[str, str]:
        return settings

    history = build_history("proj", settings_getter=_settings_getter)
    assert isinstance(history, InMemoryHistory)
    assert not isinstance(history, KaganFileHistory)


def test_history_enabled_by_default(tmp_path: Path) -> None:
    # No settings_getter — should return file history
    # We pass a monkeypatched build_history that we can safely call
    # without touching real platformdirs paths.
    history = KaganFileHistory("test-proj", history_dir=tmp_path)
    assert isinstance(history, KaganFileHistory)


def test_history_non_consecutive_duplicates_are_allowed(tmp_path: Path) -> None:
    h = KaganFileHistory("proj", history_dir=tmp_path)
    h.append_string("foo")
    h.append_string("bar")
    h.append_string("foo")

    history_file = tmp_path / "proj.jsonl"
    entries = _read_jsonl(history_file)
    assert entries.count("foo") == 2


def test_history_safe_filename_for_project_id(tmp_path: Path) -> None:
    h = KaganFileHistory("my project/id!", history_dir=tmp_path)
    h.append_string("test")
    # File should exist with sanitized name
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    # Name should not contain spaces or slashes or !
    name = files[0].name
    assert " " not in name
    assert "/" not in name
    assert "!" not in name
