"""Chat prompt composition and request classification utilities."""

from kagan.core import DEFAULT_ORCHESTRATOR_PROMPT

_ORCHESTRATOR_SYSTEM_PROMPT = DEFAULT_ORCHESTRATOR_PROMPT

_STATUS_REQUEST_HINTS: tuple[str, ...] = (
    "whats latest",
    "what's latest",
    "latest status",
    "status update",
    "current status",
    "progress update",
)

_LOG_REQUEST_HINTS: tuple[str, ...] = (
    " log",
    " logs",
    "traceback",
    "stack trace",
    "stderr",
    "stdout",
    "error output",
)


def _normalize_user_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _looks_like_log_request(text: str) -> bool:
    normalized = f" {_normalize_user_text(text)} "
    return any(hint in normalized for hint in _LOG_REQUEST_HINTS)


def _looks_like_status_request(text: str) -> bool:
    normalized = _normalize_user_text(text)
    if any(hint in normalized for hint in _STATUS_REQUEST_HINTS):
        return True
    if _looks_like_log_request(text):
        return False
    return any(token in normalized for token in ("status", "progress", "latest"))


def _runtime_guidance_for_request(text: str) -> str | None:
    if _looks_like_status_request(text):
        return (
            "Runtime guidance: answer status-first. Call run_summary before any log tool. "
            "Use task_wait for lifecycle transitions and summarize by state changes."
        )
    if _looks_like_log_request(text):
        return (
            "Runtime guidance: if logs are needed, request bounded logs first "
            "(small limit, bounded payload preview), then summarize key failures."
        )
    return None


def _format_user_request_block(text: str) -> str:
    guidance = _runtime_guidance_for_request(text)
    if guidance is None:
        return f"User request:\n{text}"
    return f"User request:\n{text}\n\n{guidance}"


def build_orchestrator_prompt(
    history: list[tuple[str, str]],
    user_text: str,
    *,
    history_limit: int = 10,
) -> str:
    history_lines = [
        f"{role.title()}: {content}"
        for role, content in history[-history_limit:]
        if content.strip()
    ]
    return "\n".join([*history_lines, f"User: {user_text}"])


def build_chat_status_line(*, mode: str, session_label: str, message_count: int) -> str:
    mode_label = mode.upper()
    noun = "msg" if message_count == 1 else "msgs"
    return f"{mode_label} · {session_label} · {message_count} {noun}"


def format_session_payload(
    *,
    session_label: str,
    session_key: str,
    runtime_session_id: str | None,
) -> tuple[str, str]:
    descriptor = f"Session: {session_label} ({session_key})"
    runtime = f"Runtime session id: {runtime_session_id or 'unavailable'}"
    return descriptor, runtime


def normalize_chat_input(text: str) -> str:
    return text.strip()


def merge_task_follow_up_description(current_description: str, follow_up_message: str) -> str:
    merged_description = current_description.strip()
    follow_up = f"User follow-up:\n{follow_up_message.strip()}".strip()
    return f"{merged_description}\n\n{follow_up}" if merged_description else follow_up
