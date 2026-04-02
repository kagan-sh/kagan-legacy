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
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition from {from_status!r} to {to_status!r}")


class WorktreeError(KaganError):
    pass


class MultiRepoUnsupportedError(WorktreeError):
    code = "MULTI_REPO_UNSUPPORTED"
    hint = "Link exactly one repository to the project."

    def __init__(self, repo_count: int) -> None:
        self.repo_count = repo_count
        super().__init__(
            f"{self.code}: task execution currently supports exactly one linked repo; "
            f"found {repo_count}"
        )


class MergeConflictError(WorktreeError):
    def __init__(self, message: str, *, conflict_files: list[str] | None = None) -> None:
        self.conflict_files: list[str] = conflict_files or []
        if self.conflict_files:
            self.hint = f"Resolve conflicts in: {', '.join(self.conflict_files)}"
        super().__init__(message)


class AgentError(KaganError):
    pass


class AgentTimeoutError(AgentError):
    hint = "The agent took too long. Try a simpler prompt or check agent connectivity."


class AgentRepetitionError(AgentError):
    pass


class AgentRateLimitError(AgentError):
    hint = "Wait a moment and retry, or switch to a different agent backend."


class PreflightError(KaganError):
    hint = "Run 'kagan doctor' for details."


class ValidationError(KaganError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}" if field else message)


class ConfigurationError(KaganError):
    def __init__(self, context: str, detail: str) -> None:
        self.context = context
        self.detail = detail
        self.hint = "Run 'kagan doctor' to diagnose configuration issues."
        super().__init__(f"{context}: {detail}" if detail else context)


class SessionError(KaganError):
    def __init__(self, session_id: str | None, message: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id}: {message}" if session_id else message)


class CompactionError(SessionError):
    pass


class HookError(KaganError):
    def __init__(self, hook_name: str, message: str) -> None:
        self.hook_name = hook_name
        super().__init__(f"Hook {hook_name!r}: {message}")


class VerificationError(KaganError):
    def __init__(self, task_id: str, message: str) -> None:
        self.task_id = task_id
        super().__init__(f"Verification failed for task {task_id!r}: {message}")


class RewindError(WorktreeError):
    def __init__(self, task_id: str, message: str) -> None:
        self.task_id = task_id
        super().__init__(f"Rewind failed for task {task_id!r}: {message}")


class InsightError(KaganError):
    pass
