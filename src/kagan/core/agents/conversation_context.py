"""Shared helpers for rendering agent persona and conversation prompt sections."""

from __future__ import annotations

from kagan.core.domain.enums import ChatRole
from kagan.core.safety import literalize_for_prompt

ASSISTANT_HISTORY_PREVIEW_MAX_CHARS = 2_000


def build_persona_section(persona: str | None) -> str:
    """Render the optional persona preset section."""
    if not isinstance(persona, str):
        return ""
    cleaned = persona.strip()
    if not cleaned:
        return ""
    return f"## Persona Preset\n\n{literalize_for_prompt(cleaned)}"


def build_conversation_context_lines(
    conversation_history: list[tuple[str, str]] | None,
) -> list[str]:
    """Render conversation history lines with bounded assistant message previews."""
    if not conversation_history:
        return []

    lines: list[str] = []
    for role, content in conversation_history:
        safe_content = literalize_for_prompt(content)
        if role == ChatRole.USER:
            lines.append(f"User: {safe_content}")
            continue
        preview = _truncate_assistant_history(
            safe_content,
            limit=ASSISTANT_HISTORY_PREVIEW_MAX_CHARS,
        )
        lines.append(f"Assistant: {preview}")
    return lines


def _truncate_assistant_history(content: str, *, limit: int) -> str:
    if len(content) <= limit:
        return content
    return f"{content[:limit]}..."


__all__ = [
    "ASSISTANT_HISTORY_PREVIEW_MAX_CHARS",
    "build_conversation_context_lines",
    "build_persona_section",
]
