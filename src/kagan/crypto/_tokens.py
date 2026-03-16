"""Bearer token generation and verification."""

from __future__ import annotations

import hmac
import os

_TOKEN_BYTES = 32


def generate_token() -> str:
    """Generate a 64-character hex bearer token (32 random bytes)."""
    return os.urandom(_TOKEN_BYTES).hex()


def verify_token(token: str, expected: str) -> bool:
    """Compare *token* against *expected* in constant time.

    Returns:
        ``True`` if the tokens match, ``False`` otherwise.
    """
    return hmac.compare_digest(token, expected)
