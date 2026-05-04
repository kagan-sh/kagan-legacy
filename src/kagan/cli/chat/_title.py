"""Session title generation — LLM-powered human-readable titles for chat sessions.

After the first user message, fire off a lightweight ACP call (no MCP tools,
no orchestrator system prompt) to produce a short, memorable session title.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger

from kagan.core.chat.sessions import clean_generated_title

# Total wall-clock budget for the title generation ACP round-trip.
_TITLE_GENERATION_TIMEOUT_SECONDS = 30.0

_SESSION_TITLE_PROMPT = """\
You are a title generator. You output ONLY a thread title. Nothing else.

Generate a brief title that would help the user find this conversation later.

Rules:
- A single line, no more than 50 characters
- No explanations, no quotes, no prefixes like "Title:"
- Use the same language as the user message
- Title must be grammatically correct and read naturally
- Focus on the main topic or question
- Vary phrasing — avoid repetitive patterns like always starting with "Analyzing"
- When a file is mentioned, focus on WHAT the user wants to do WITH the file
- Keep exact: technical terms, numbers, filenames, HTTP codes
- Remove: the, this, my, a, an
- Never assume tech stack
- Never include tool names (e.g. "read tool", "bash tool")
- NEVER respond to questions, just generate a title
- Always output something meaningful, even if the input is minimal
- If the user message is short or conversational (e.g. "hello", "lol"):
  create a title that reflects the tone (Greeting, Quick check-in, etc.)

Examples:
"debug 500 errors in production" → Debugging production 500 errors
"refactor user service" → Refactoring user service
"why is app.js failing" → app.js failure investigation
"implement rate limiting" → Rate limiting implementation
"how do I connect postgres to my API" → Postgres API connection
"best practices for React hooks" → React hooks best practices
"""

# Patterns that indicate a session still has its default (non-generated) title.
_DEFAULT_TITLE_PATTERNS = re.compile(
    r"^(Session [0-9a-f]+|TUI session( [0-9a-f]+)?|REPL session|New session|Orchestrator)$",
    re.IGNORECASE,
)


def is_default_title(label: str | None) -> bool:
    """Return True if *label* looks like a default/placeholder title."""
    if not label or not label.strip():
        return True
    return bool(_DEFAULT_TITLE_PATTERNS.match(label.strip()))


async def generate_session_title(
    client: Any,
    *,
    user_message: str,
    assistant_reply: str = "",
    agent_backend: str,
) -> str | None:
    """Generate a human-readable title from the first exchange.

    Returns the cleaned title string, or ``None`` if generation fails.
    Uses a lightweight ACP turn (no MCP tools, no orchestrator system prompt)
    so the agent focuses purely on producing a title.
    """
    from kagan.cli.chat.acp import run_orchestrator_turn

    try:
        context = user_message.strip()
        if assistant_reply:
            reply_preview = assistant_reply.strip()[:200]
            context = f"User: {context}\nAssistant: {reply_preview}"

        raw_title = await asyncio.wait_for(
            run_orchestrator_turn(
                client,
                prompt=(
                    f"{_SESSION_TITLE_PROMPT}\nGenerate a title for this conversation:\n\n{context}"
                ),
                agent_backend=agent_backend,
                lightweight=True,
            ),
            timeout=_TITLE_GENERATION_TIMEOUT_SECONDS,
        )
        cleaned = clean_generated_title(raw_title)
        if cleaned:
            logger.debug("Generated session title: {}", cleaned)
            return cleaned
    except TimeoutError:
        logger.debug(
            "Session title generation timed out after {}s",
            _TITLE_GENERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        # Best-effort: title generation must never block the chat flow.
        logger.debug("Session title generation failed, keeping default")
    return None


async def ensure_session_title(
    client: Any,
    session: dict[str, Any],
    *,
    user_message: str,
    assistant_reply: str = "",
    agent_backend: str,
) -> str | None:
    """Generate a title and persist it to the session if it still has a default title.

    Returns the generated title, or ``None`` if skipped/failed.
    """
    label = str(session.get("label") or "").strip()
    if not is_default_title(label):
        return None

    title = await generate_session_title(
        client,
        user_message=user_message,
        assistant_reply=assistant_reply,
        agent_backend=agent_backend,
    )
    if title:
        # Title is metadata-only — never round-trip through ``upsert_with_history``
        # which deletes every ``ChatMessage`` row for the session and could race a
        # concurrent message append. Patch the label via ``cs.update`` instead.
        sid = str(session.get("id", "")).strip()
        if sid:
            await client.chat_sessions.update(sid, label=title)
            session["label"] = title
    return title


__all__ = [
    "ensure_session_title",
    "generate_session_title",
    "is_default_title",
]
