"""Key generation and derivation primitives."""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_SALT = b"kagan-v1"
_KEY_LENGTH = 32


def generate_key() -> bytes:
    """Generate a random 32-byte AES-256 key."""
    return os.urandom(_KEY_LENGTH)


def derive_key(master: bytes, info: str) -> bytes:
    """Derive a 32-byte key from *master* using HKDF-SHA256.

    Args:
        master: The master key material.
        info: Context string for key separation.

    Returns:
        A 32-byte derived key.
    """
    hkdf = HKDF(
        algorithm=SHA256(),
        length=_KEY_LENGTH,
        salt=_SALT,
        info=info.encode(),
    )
    return hkdf.derive(master)
