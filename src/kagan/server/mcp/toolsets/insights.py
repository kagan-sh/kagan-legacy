"""kagan.server.mcp.toolsets.insights — Insight distillation MCP tools."""

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from kagan.core._insights import InsightCategory
from kagan.core.enums import SessionEventType
from kagan.core.errors import InsightError, ValidationError
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary

# Prefix used when persisting insights as TaskNote entries.
_INSIGHT_PREFIX = "[INSIGHT:"
_INSIGHT_PREFIX_END = "]"


def _make_note_content(category: InsightCategory, content: str) -> str:
    """Encode an insight as a TaskNote content string."""
    return f"{_INSIGHT_PREFIX}{category.value.upper()}{_INSIGHT_PREFIX_END} {content}"


def _parse_note_content(raw: str) -> tuple[InsightCategory, str] | None:
    """Decode a TaskNote content string into (category, content).

    Returns None if the note is not an insight note.
    """
    if not raw.startswith(_INSIGHT_PREFIX):
        return None
    end = raw.find(_INSIGHT_PREFIX_END, len(_INSIGHT_PREFIX))
    if end == -1:
        return None
    cat_str = raw[len(_INSIGHT_PREFIX) : end].lower()
    try:
        category = InsightCategory(cat_str)
    except ValueError:
        return None
    content = raw[end + 1 :].strip()
    return category, content


def _validate_category(category: str) -> InsightCategory:
    """Validate and return an InsightCategory from a raw string."""
    normalized = category.strip().lower()
    try:
        return InsightCategory(normalized)
    except ValueError:
        allowed = ", ".join(c.value for c in InsightCategory)
        raise ValidationError(
            "category",
            f"Unknown category {category!r}. Allowed values: {allowed}",
        ) from None


@mcp_error_boundary
async def _insight_add(
    ctx: Context,
    task_id: str,
    category: str,
    content: str,
) -> dict[str, Any]:
    """Add a project insight for a task.

    Insights are categorized observations extracted from agent sessions.
    Valid categories: pattern, error, architecture, preference, dependency.
    The insight is persisted as a TaskNote and will be surfaced in future
    task prompts alongside [LEARNING] notes.
    """
    app = get_context(ctx)
    cat = _validate_category(category)
    content = content.strip()
    if not content:
        raise ValidationError("content", "content must not be empty")

    note_content = _make_note_content(cat, content)
    await app.client.tasks.add_note(task_id, note_content)

    session_id = app.bound_session_id or app.opts.session_id
    await app.client.tasks.events.emit(
        task_id,
        SessionEventType.INSIGHT_EXTRACTED,
        {"category": cat.value, "content": content},
        session_id=session_id,
    )

    return {
        "task_id": task_id,
        "category": cat.value,
        "content": content,
        "persisted": True,
    }


@mcp_error_boundary
async def _insight_list(ctx: Context, task_id: str) -> dict[str, Any]:
    """List all insights recorded for a task.

    Returns insights grouped by category with their content.
    """
    app = get_context(ctx)
    notes = await app.client.tasks.list_notes(task_id)

    insights: list[dict[str, Any]] = []
    for note in notes:
        parsed = _parse_note_content(note.content)
        if parsed is None:
            continue
        cat, content = parsed
        insights.append(
            {
                "category": cat.value,
                "content": content,
                "created_at": note.created_at.isoformat(),
            }
        )

    by_category: dict[str, int] = {}
    for item in insights:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1

    return {
        "task_id": task_id,
        "insights": insights,
        "total": len(insights),
        "by_category": by_category,
    }


@mcp_error_boundary
async def _insight_remove(
    ctx: Context,
    task_id: str,
    content: str,
) -> dict[str, Any]:
    """Remove an insight from a task by matching its content text.

    Performs a case-insensitive exact content match. Returns removed=True if
    a matching insight was found and deleted, removed=False otherwise.
    """
    app = get_context(ctx)
    content = content.strip()
    if not content:
        raise InsightError("content must not be empty")

    notes = await app.client.tasks.list_notes(task_id)
    target_lower = content.lower()

    removed = False
    for note in notes:
        parsed = _parse_note_content(note.content)
        if parsed is None:
            continue
        _, note_content = parsed
        if note_content.strip().lower() == target_lower:
            await app.client.tasks.delete_note(task_id, note.id)
            removed = True
            break

    return {
        "task_id": task_id,
        "content": content,
        "removed": removed,
    }


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register insight distillation tools on mcp, filtered by opts."""
    _tools = [
        ("insight_add", _insight_add),
        ("insight_list", _insight_list),
        ("insight_remove", _insight_remove),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
