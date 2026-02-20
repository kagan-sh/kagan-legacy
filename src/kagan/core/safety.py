"""Deterministic content safety helpers for prompt and persistence boundaries."""

from __future__ import annotations

import hashlib
import re
from html import escape
from typing import Any

PROMPT_UNTRUSTED_MAX_CHARS = 20_000
QUEUE_MESSAGE_MAX_CHARS = 12_000
REDACTED_TOKEN = "[REDACTED]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_SSN = "[REDACTED_SSN]"

_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
_BEARER_HEADER_PATTERN = re.compile(r"(?i)\b(authorization\s*:\s*bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_TOKEN_PREFIX_PATTERN = re.compile(
    r"\b(?:"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"ASIA[0-9A-Z]{16}|"
    r"sk-[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}"
    r")\b"
)
_KEY_VALUE_SECRET_PATTERN = re.compile(
    r"""(?ix)
    \b(
      api[-_]?key|
      access[-_]?token|
      refresh[-_]?token|
      client[-_]?secret|
      private[-_]?key|
      secret|
      token|
      password|
      passwd|
      pwd
    )\b
    (\s*[:=]\s*|["'\s]+)
    ([^\s,"']{6,})
    """
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_NULL_BYTE_PATTERN = re.compile("\x00")


def normalize_untrusted_text(text: str, *, max_chars: int | None = None) -> str:
    """Normalize user-controlled text and cap size with deterministic truncation."""
    normalized = _NULL_BYTE_PATTERN.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    if max_chars is None:
        return normalized
    if max_chars <= 0:
        return ""
    if len(normalized) <= max_chars:
        return normalized
    omitted = len(normalized) - max_chars
    return f"{normalized[:max_chars]}\n\n[truncated {omitted} chars]"


def literalize_for_prompt(text: str, *, max_chars: int = PROMPT_UNTRUSTED_MAX_CHARS) -> str:
    """Escape text so it cannot break prompt delimiters or XML-like sections."""
    normalized = normalize_untrusted_text(text, max_chars=max_chars)
    return escape(normalized, quote=False)


def redact_sensitive_text(text: str, *, redact_pii: bool = False) -> str:
    """Redact high-confidence secrets from text deterministically."""
    redacted = _PRIVATE_KEY_PATTERN.sub(REDACTED_TOKEN, text)
    redacted = _BEARER_HEADER_PATTERN.sub(r"\1 " + REDACTED_TOKEN, redacted)
    redacted = _JWT_PATTERN.sub(REDACTED_TOKEN, redacted)
    redacted = _TOKEN_PREFIX_PATTERN.sub(REDACTED_TOKEN, redacted)
    redacted = _KEY_VALUE_SECRET_PATTERN.sub(_replace_secret_assignment, redacted)

    if redact_pii:
        redacted = _EMAIL_PATTERN.sub(REDACTED_EMAIL, redacted)
        redacted = _SSN_PATTERN.sub(REDACTED_SSN, redacted)
    return redacted


def redact_sensitive_payload(value: Any, *, redact_pii: bool = False) -> Any:
    """Recursively redact secrets in JSON-like payloads."""
    if isinstance(value, str):
        return redact_sensitive_text(value, redact_pii=redact_pii)
    if isinstance(value, list):
        return [redact_sensitive_payload(item, redact_pii=redact_pii) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_payload(item, redact_pii=redact_pii) for item in value)
    if isinstance(value, dict):
        return {
            key: redact_sensitive_payload(item, redact_pii=redact_pii)
            for key, item in value.items()
        }
    return value


def prompt_digest(text: str, *, length: int = 12) -> str:
    """Stable short digest for privacy-safe logging."""
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
    return digest[: max(length, 4)]


def _replace_secret_assignment(match: re.Match[str]) -> str:
    key = match.group(1)
    separator = match.group(2)
    return f"{key}{separator}{REDACTED_TOKEN}"


__all__ = [
    "PROMPT_UNTRUSTED_MAX_CHARS",
    "QUEUE_MESSAGE_MAX_CHARS",
    "REDACTED_EMAIL",
    "REDACTED_SSN",
    "REDACTED_TOKEN",
    "literalize_for_prompt",
    "normalize_untrusted_text",
    "prompt_digest",
    "redact_sensitive_payload",
    "redact_sensitive_text",
]
