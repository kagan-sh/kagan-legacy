"""Context compaction — summarize conversation history to free context space."""

from dataclasses import dataclass

from loguru import logger

COMPACTION_THRESHOLD = 0.80


@dataclass(slots=True)
class CompactionResult:
    """Result of a compaction operation."""

    triggered: bool
    context_before: int
    context_after: int | None = None
    summary_length: int | None = None
    error: str | None = None


class ContextCompactor:
    """Monitors context usage and triggers compaction when threshold is exceeded.

    Compaction works by:
    1. Detecting when context_window_used / context_window_size > threshold
    2. Emitting a COMPACTION_TRIGGERED event
    3. Recording the compaction in session metadata

    Note: Actual summarization is delegated to the agent backend (via ACP).
    Kagan's role is detection, signaling, and bookkeeping.
    """

    threshold: float
    _last_used: int
    _last_size: int
    _compaction_count: int
    _enabled: bool

    def __init__(self, *, threshold: float = COMPACTION_THRESHOLD, enabled: bool = True) -> None:
        self.threshold = threshold
        self._last_used = 0
        self._last_size = 0
        self._compaction_count = 0
        self._enabled = enabled

    def update_usage(self, used: int, size: int) -> bool:
        """Update context usage metrics. Returns True if compaction should trigger."""
        self._last_used = used
        self._last_size = size
        if not self._enabled or size <= 0:
            return False
        ratio = used / size
        if ratio >= self.threshold:
            logger.warning(
                "Context usage {:.0%} exceeds threshold {:.0%} — compaction recommended",
                ratio,
                self.threshold,
            )
            return True
        return False

    def record_compaction(self) -> None:
        """Record that a compaction was performed."""
        self._compaction_count += 1

    @property
    def usage_ratio(self) -> float:
        if self._last_size <= 0:
            return 0.0
        return self._last_used / self._last_size

    @property
    def compaction_count(self) -> int:
        return self._compaction_count

    @property
    def needs_compaction(self) -> bool:
        return self._enabled and self.usage_ratio >= self.threshold

    def reset(self) -> None:
        self._last_used = 0
        self._last_size = 0
        self._compaction_count = 0
