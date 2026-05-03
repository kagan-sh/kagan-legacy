"""Single source of truth for kg chat REPL Rich styles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApprovalStyles:
    border: str = "yellow"
    focused: str = "cyan bold"
    cursor: str = "cyan"
    dim: str = "dim"
    hint: str = "dim"
    meta: str = "dim grey50"


APPROVAL = ApprovalStyles()
