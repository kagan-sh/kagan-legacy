"""Error hierarchy for kagan.core — all errors inherit from KaganError."""


class KaganError(Exception):
    hint: str = ""


class NotFoundError(KaganError):
    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id!r} not found")


class InvalidTransitionError(KaganError):
    def __init__(self, from_status: str, to_status: str) -> None:
        # to_status may be Trigger name from state machine (both are StrEnum/str).
        self.from_status = str(from_status)
        self.to_status = str(to_status)
        super().__init__(f"Cannot transition from {self.from_status!r} to {self.to_status!r}")


class WorktreeError(KaganError):
    pass


class MergeConflictError(WorktreeError):
    def __init__(self, message: str, *, conflict_files: list[str] | None = None) -> None:
        self.conflict_files: list[str] = conflict_files or []
        if self.conflict_files:
            self.hint = f"Resolve conflicts in: {', '.join(self.conflict_files)}"
        super().__init__(message)


class AgentError(KaganError):
    pass


class PreflightError(KaganError):
    hint = "Run 'kagan doctor' for details."


class ValidationError(KaganError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}" if field else message)


class AgentCapError(KaganError):
    """Lever 5: refused starting a run because the concurrent-agent cap is hit."""

    def __init__(self, running: int, cap: int) -> None:
        self.running = running
        self.cap = cap
        self.hint = "Finish a review first, then start the next one."
        super().__init__(f"{running} agents already working (cap {cap})")


class ConfigurationError(KaganError):
    def __init__(self, context: str, detail: str) -> None:
        self.context = context
        self.detail = detail
        self.hint = "Run 'kagan doctor' to diagnose configuration issues."
        super().__init__(f"{context}: {detail}" if detail else context)
