"""Surface-agnostic turn-phase timing for CLI and TUI renderers."""
from __future__ import annotations

import time


class TurnPhaseTracker:
    """Tracks elapsed time and estimated tokens for the current turn phase."""

    def __init__(self) -> None:
        self._phase = "composing"
        self._start = time.monotonic()
        self._tokens = 0.0

    def set_phase(self, phase: str) -> None:
        if phase == self._phase:
            return
        self._phase = phase
        self._start = time.monotonic()
        self._tokens = 0.0

    def add_text(self, text: str) -> None:
        self._tokens += len(text) / 4.0

    def thinking_label(self) -> str:
        e = time.monotonic() - self._start
        t = int(self._tokens)
        rate = f" · {int(t / e)} tok/s" if e > 0.5 and t > 0 else ""
        return f"Thinking  {e:.1f}s · {t} tokens{rate}"

    def composing_label(self) -> str:
        e = time.monotonic() - self._start
        return f"Composing  {e:.1f}s · {int(self._tokens)} tokens"
