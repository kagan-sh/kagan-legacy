from __future__ import annotations

DEFAULT_AUDIT_FIELD_CHAR_LIMIT = 4_000


def truncate_for_transport(content: str, *, limit: int) -> tuple[str, bool]:
    """Truncate transport payload text and report whether truncation occurred."""
    if limit <= 0:
        return "", bool(content)
    if len(content) <= limit:
        return content, False
    omitted_chars = len(content) - limit
    return f"{content[:limit]}\n\n[truncated {omitted_chars} chars for transport]", True


__all__ = ["DEFAULT_AUDIT_FIELD_CHAR_LIMIT", "truncate_for_transport"]
