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
from typing import TYPE_CHECKING, Final

from loguru import logger
from platformdirs import user_data_dir
from prompt_toolkit.history import History as _PromptToolkitHistory

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_ENTRIES: Final[int] = 500
_KAGAN_HISTORY_DIR_ENV: Final[str] = "KAGAN_DATA_DIR"


def _history_dir() -> Path:
    data_root = os.environ.get(_KAGAN_HISTORY_DIR_ENV)
    if data_root:
        return Path(data_root) / "history"
    return Path(user_data_dir("kagan", "kagan")) / "history"


def _safe_filename(project_id: str) -> str:
    """Sanitize a project ID for use as a filename component."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in project_id)


def _history_path(project_id: str, *, history_dir: Path | None = None) -> Path:
    base = history_dir if history_dir is not None else _history_dir()
    return base / f"{_safe_filename(project_id)}.jsonl"


def _read_jsonl(path: Path) -> list[str]:
    """Read all valid history entries from a JSONL file.

    Returns up to ``_MAX_ENTRIES`` entries, newest at the end.
    Returns ``[]`` if the file does not exist or cannot be read.
    """
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


def load_history(project_id: str, *, history_dir: Path | None = None) -> list[str]:
    """Load history entries for *project_id* from disk.

    When *history_dir* is provided, it overrides the default platformdirs path.
    Useful for tests that need isolated history files.
    """
    return _read_jsonl(_history_path(project_id, history_dir=history_dir))


def save_entry(project_id: str, text: str, *, history_dir: Path | None = None) -> None:
    if not text:
        return
    path = _history_path(project_id, history_dir=history_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = _read_jsonl(path)
        if existing and existing[-1] == text:
            return
        existing.append(text)
        if len(existing) > _MAX_ENTRIES:
            existing = existing[-_MAX_ENTRIES:]
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
    _history: list[str] = field(default_factory=list)
    _index: int | None = None
    _working_draft: str = ""

    def replace_history(self, entries: list[str]) -> None:
        self._history = list(entries)
        self._index = None
        self._working_draft = ""

    def append(self, text: str) -> None:
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
        self._index = None

    def cycle_up(self, current_input: str) -> str | None:
        if not self._history:
            return None
        if self._index is None:
            self._working_draft = current_input
            self._index = len(self._history) - 1
        else:
            self._index = max(0, self._index - 1)
        return self._history[self._index]

    def cycle_down(self, current_input: str) -> str | None:
        if self._index is None:
            return None
        if self._index >= len(self._history) - 1:
            self._index = None
            return self._working_draft
        self._index += 1
        return self._history[self._index]

    def is_navigating(self) -> bool:
        return self._index is not None

    @property
    def entries(self) -> list[str]:
        return list(self._history)


class KaganFileHistory(_PromptToolkitHistory):
    """File-backed history shared between TUI and CLI chat for a project.

    Subclasses prompt_toolkit's ``History`` so the modern ``Buffer.load_history``
    coroutine path works.  ``store_string`` and ``load_history_strings`` carry
    the file IO; the in-memory cursor still backs ``cycle_up`` / ``cycle_down``
    for the TUI.

    ``persist`` maps to the ``persist_input_history`` settings flag.
    ``history_dir`` overrides the default platformdirs location (useful for tests).
    """

    def __init__(
        self,
        project_id: str,
        *,
        persist: bool = True,
        history_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._project_id = project_id
        self._persist = persist
        self._history_dir = history_dir
        self._cursor = _HistoryCursor()
        if persist:
            self._cursor.replace_history(load_history(project_id, history_dir=history_dir))

    # --- shared write path ---------------------------------------------------

    def push(self, text: str) -> None:
        """Record *text* and persist to disk when enabled."""
        self._cursor.append(text)
        if self._persist:
            save_entry(self._project_id, text, history_dir=self._history_dir)

    # --- prompt_toolkit History protocol -------------------------------------

    def load_history_strings(self):
        # prompt_toolkit expects newest first.
        yield from reversed(self._cursor.entries)

    def store_string(self, string: str) -> None:
        if self._persist:
            save_entry(self._project_id, string, history_dir=self._history_dir)

    def append_string(self, string: str) -> None:
        # Mirror push so cursor + on-disk + parent's cache all stay in sync.
        self.push(string)
        if hasattr(self, "_loaded_strings"):
            self._loaded_strings.insert(0, string)

    def get_strings(self) -> list[str]:
        return self._cursor.entries

    def get_strings_from_disk(self) -> list[str]:
        """Return entries read fresh from disk (bypasses the in-memory cursor).

        Useful in tests to assert what was actually persisted without
        relying on the in-memory cursor state.
        """
        return load_history(self._project_id, history_dir=self._history_dir)

    # --- TUI cursor navigation -----------------------------------------------

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


def build_history(
    project_id: str,
    *,
    settings_getter: Callable[[], dict[str, object]] | None = None,
) -> KaganFileHistory | object:
    """Return a ``KaganFileHistory`` or an in-memory fallback per settings.

    Args:
        project_id: Identifier for the current project.
        settings_getter: Zero-arg callable returning the current settings dict.
            When ``None`` or the call fails, file-backed history is used.
    """
    from prompt_toolkit.history import InMemoryHistory

    if settings_getter is not None:
        try:
            settings = settings_getter()
            raw = settings.get("persist_input_history", "true")
            if isinstance(raw, str) and raw.strip().lower() in {"0", "false", "no", "off"}:
                return InMemoryHistory()
        except Exception as exc:
            logger.warning("Could not read persist_input_history setting: {}", exc)

    return KaganFileHistory(project_id)
