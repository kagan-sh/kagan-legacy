"""Error hierarchy for kagan.core — all errors inherit from KaganError."""


class KaganError(Exception):
    pass


class NotFoundError(KaganError):
    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id!r} not found")


class InvalidTransitionError(KaganError):
    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition from {from_status!r} to {to_status!r}")


class WorktreeError(KaganError):
    pass


class MultiRepoUnsupportedError(WorktreeError):
    code = "MULTI_REPO_UNSUPPORTED"

    def __init__(self, repo_count: int) -> None:
        self.repo_count = repo_count
        super().__init__(
            f"{self.code}: task execution currently supports exactly one linked repo; "
            f"found {repo_count}"
        )


class MergeConflictError(WorktreeError):
    def __init__(self, message: str, *, conflict_files: list[str] | None = None) -> None:
        self.conflict_files: list[str] = conflict_files or []
        super().__init__(message)


class AgentError(KaganError):
    pass


class PreflightError(KaganError):
    pass


class ValidationError(KaganError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}" if field else message)


class ConfigurationError(KaganError):
    def __init__(self, context: str, detail: str) -> None:
        self.context = context
        self.detail = detail
        super().__init__(f"{context}: {detail}" if detail else context)


class SessionError(KaganError):
    def __init__(self, session_id: str | None, message: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id}: {message}" if session_id else message)
