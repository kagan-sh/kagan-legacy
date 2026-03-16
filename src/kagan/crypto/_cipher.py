"""AES-256-GCM authenticated encryption."""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LENGTH = 12


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    """Encrypt *plaintext* with AES-256-GCM.

    A random 12-byte nonce is prepended to the output.

    Returns:
        ``nonce || ciphertext || tag`` as a single bytes object.
    """
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt(key: bytes, ciphertext: bytes) -> bytes:
    """Decrypt *ciphertext* produced by :func:`encrypt`.

    Expects the first 12 bytes to be the nonce.

    Returns:
        The original plaintext.
    """
    nonce = ciphertext[:_NONCE_LENGTH]
    return AESGCM(key).decrypt(nonce, ciphertext[_NONCE_LENGTH:], None)
