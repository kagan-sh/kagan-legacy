"""Single source of truth for kg chat REPL Rich styles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApprovalStyles:
    border: str = "#d4a84b"
    focused: str = "#d4a84b bold"
    cursor: str = "#d4a84b"
    dim: str = "dim"
    hint: str = "dim"
    meta: str = "dim grey50"


APPROVAL = ApprovalStyles()
