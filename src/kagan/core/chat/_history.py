"""Persistent chat input history for both the TUI and CLI chat surfaces.

History is stored in JSONL format — one ``{"text": "..."}`` per line — under
``platformdirs.user_data_dir("kagan") / "history" / "<project_id>.jsonl"``.

The last 500 unique consecutive entries are kept.  If
``persist_input_history=False`` is set in the kagan settings the file is
never written and a purely in-memory list is used instead.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from platformdirs import user_data_dir

_MAX_ENTRIES: Final[int] = 500
_KAGAN_HISTORY_DIR_ENV: Final[str] = "KAGAN_DATA_DIR"


def _history_dir() -> Path:
    """Return the base directory for history files, respecting KAGAN_DATA_DIR."""
    data_root = os.environ.get(_KAGAN_HISTORY_DIR_ENV)
    if data_root:
        return Path(data_root) / "history"
    return Path(user_data_dir("kagan", "kagan")) / "history"


def _history_path(project_id: str) -> Path:
    return _history_dir() / f"{project_id}.jsonl"


def load_history(project_id: str) -> list[str]:
    """Load history entries from disk for *project_id*.

    Returns an empty list if the file does not exist or cannot be read.
    Only the last ``_MAX_ENTRIES`` entries are kept in memory.
    """
    path = _history_path(project_id)
    if not path.exists():
        return []
    entries: list[str] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    text = obj.get("text", "") if isinstance(obj, dict) else ""
                    if isinstance(text, str) and text:
                        entries.append(text)
                except (json.JSONDecodeError, AttributeError):
                    continue
    except OSError:
        return []
    return entries[-_MAX_ENTRIES:]


def save_entry(project_id: str, text: str) -> None:
    """Append *text* to the history file for *project_id*.

    Consecutive duplicate entries are skipped.  The file is capped at
    ``_MAX_ENTRIES`` lines by rewriting when it grows beyond the limit.
    """
    if not text:
        return
    path = _history_path(project_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = load_history(project_id)
        if existing and existing[-1] == text:
            return
        existing.append(text)
        if len(existing) > _MAX_ENTRIES:
            existing = existing[-_MAX_ENTRIES:]
            # Rewrite the whole file when trimming
            with path.open("w", encoding="utf-8") as fh:
                for entry in existing:
                    fh.write(json.dumps({"text": entry}) + "\n")
        else:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"text": text}) + "\n")
    except OSError:
        pass


@dataclass(slots=True)
class _HistoryCursor:
    """Track cursor position inside a history list plus an unsaved working draft.

    Usage pattern:
    - Call :meth:`cycle_up` / :meth:`cycle_down` to walk through history.
    - When the user types new text between navigation calls :meth:`reset` is
      used to clear the cursor so the next Up starts from the most-recent end.
    - A *working draft* (text the user had started typing before pressing Up)
      is saved the first time :meth:`cycle_up` is called and restored when
      :meth:`cycle_down` reaches the end of the history list.
    """

    _history: list[str] = field(default_factory=list)
    _index: int | None = None
    _working_draft: str = ""

    def replace_history(self, entries: list[str]) -> None:
        """Replace the underlying list (e.g. after loading from disk)."""
        self._history = list(entries)
        self._index = None
        self._working_draft = ""

    def append(self, text: str) -> None:
        """Append *text* skipping consecutive duplicates; resets cursor."""
        if not text:
            return
        if self._history and self._history[-1] == text:
            self._index = None
            return
        self._history.append(text)
        if len(self._history) > _MAX_ENTRIES:
            self._history = self._history[-_MAX_ENTRIES:]
        self._index = None
        self._working_draft = ""

    def reset(self) -> None:
        """Reset cursor to end-of-history (no active navigation)."""
        self._index = None

    def cycle_up(self, current_input: str) -> str | None:
        """Navigate to the previous (older) history entry.

        Returns the entry text or ``None`` when history is empty.
        Saves *current_input* as the working draft on the first call.
        """
        if not self._history:
            return None
        if self._index is None:
            # Save current input as draft before we start navigating
            self._working_draft = current_input
            self._index = len(self._history) - 1
        else:
            self._index = max(0, self._index - 1)
        return self._history[self._index]

    def cycle_down(self, current_input: str) -> str | None:
        """Navigate to the next (more-recent) history entry.

        Returns the entry text, or the saved working draft when the cursor
        moves past the end of the history list.  Returns ``None`` when not
        actively navigating.
        """
        if self._index is None:
            return None
        if self._index >= len(self._history) - 1:
            # Restore the working draft and exit navigation mode
            self._index = None
            return self._working_draft
        self._index += 1
        return self._history[self._index]

    def is_navigating(self) -> bool:
        return self._index is not None

    @property
    def entries(self) -> list[str]:
        return list(self._history)


class KaganFileHistory:
    """File-backed history store shared between TUI and CLI chat for a project.

    ``persist`` maps to the ``persist_input_history`` settings flag.  When
    ``False`` the history is kept in-memory only (no disk I/O).
    """

    def __init__(self, project_id: str, *, persist: bool = True) -> None:
        self._project_id = project_id
        self._persist = persist
        self._cursor = _HistoryCursor()
        if persist:
            loaded = load_history(project_id)
            self._cursor.replace_history(loaded)

    def push(self, text: str) -> None:
        """Record *text* into history and persist to disk when enabled."""
        self._cursor.append(text)
        if self._persist:
            save_entry(self._project_id, text)

    def cycle_up(self, current_input: str) -> str | None:
        return self._cursor.cycle_up(current_input)

    def cycle_down(self, current_input: str) -> str | None:
        return self._cursor.cycle_down(current_input)

    def reset_cursor(self) -> None:
        self._cursor.reset()

    def is_navigating(self) -> bool:
        return self._cursor.is_navigating()

    @property
    def entries(self) -> list[str]:
        return self._cursor.entries
