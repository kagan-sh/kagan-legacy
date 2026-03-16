"""Error hierarchy for kagan.core — all errors inherit from KaganError."""


class KaganError(Exception):
    """Base for all kagan errors."""


class NotFoundError(KaganError):
    """Raised when a target entity does not exist."""

    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id!r} not found")


class InvalidTransitionError(KaganError):
    """Raised when an illegal task status transition is attempted."""

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition from {from_status!r} to {to_status!r}")


class WorktreeError(KaganError):
    """Raised when a git worktree operation fails."""


class MultiRepoUnsupportedError(WorktreeError):
    """Raised when task execution is attempted against multiple linked repos."""

    code = "MULTI_REPO_UNSUPPORTED"

    def __init__(self, repo_count: int) -> None:
        self.repo_count = repo_count
        super().__init__(
            f"{self.code}: task execution currently supports exactly one linked repo; "
            f"found {repo_count}"
        )


class MergeConflictError(WorktreeError):
    """Raised when a merge produces conflicts; carries the list of conflicting files."""

    def __init__(self, message: str, *, conflict_files: list[str] | None = None) -> None:
        self.conflict_files: list[str] = conflict_files or []
        super().__init__(message)


class AgentError(KaganError):
    """Raised when an agent spawn or communication operation fails."""


class PreflightError(KaganError):
    """Raised when a blocking preflight check prevents an operation."""


class ValidationError(KaganError):
    """Raised when input validation fails."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}" if field else message)


class ConfigurationError(KaganError):
    """Raised when configuration or state is invalid."""

    def __init__(self, context: str, detail: str) -> None:
        self.context = context
        self.detail = detail
        super().__init__(f"{context}: {detail}" if detail else context)


class SessionError(KaganError):
    """Raised when session operations fail."""

    def __init__(self, session_id: str | None, message: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id}: {message}" if session_id else message)
