"""X25519 ephemeral key exchange for secure device pairing.

Protocol overview:
1. Server generates an ephemeral X25519 keypair.
2. QR code contains the server's **public key** (not a secret).
3. Client generates its own ephemeral keypair and sends its public key
   to ``POST /auth/pair``.
4. Both sides compute the same shared secret via ECDH.
5. A bearer token is derived from the shared secret using HKDF-SHA256.

This ensures that intercepting the QR code is useless without the
server's private key.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from kagan.crypto._keys import derive_key

_TOKEN_INFO = "kagan-pairing-token-v1"


class X25519Keypair:
    """An ephemeral X25519 keypair for ECDH key exchange.

    Attributes:
        private_key: The X25519 private key object.
    """

    __slots__ = ("private_key",)

    def __init__(self) -> None:
        self.private_key = X25519PrivateKey.generate()

    @property
    def public_key_bytes(self) -> bytes:
        """Raw 32-byte public key suitable for wire transfer."""
        return self.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    @property
    def public_key_b64(self) -> str:
        """URL-safe base64-encoded public key (no padding) for QR codes."""
        return base64.urlsafe_b64encode(self.public_key_bytes).rstrip(b"=").decode()

    def compute_shared_secret(self, peer_public_key_bytes: bytes) -> bytes:
        """Compute the ECDH shared secret from a peer's raw 32-byte public key.

        Args:
            peer_public_key_bytes: The peer's raw 32-byte X25519 public key.

        Returns:
            The 32-byte shared secret.
        """
        peer_key = X25519PublicKey.from_public_bytes(peer_public_key_bytes)
        return self.private_key.exchange(peer_key)

    def derive_token(self, peer_public_key_bytes: bytes) -> str:
        """Derive a hex bearer token from the ECDH shared secret.

        Uses HKDF-SHA256 with the info string ``kagan-pairing-token-v1``.

        Args:
            peer_public_key_bytes: The peer's raw 32-byte X25519 public key.

        Returns:
            A 64-character hex string suitable as a bearer token.
        """
        shared = self.compute_shared_secret(peer_public_key_bytes)
        return derive_key(shared, _TOKEN_INFO).hex()


def generate_keypair() -> X25519Keypair:
    """Generate a fresh ephemeral X25519 keypair."""
    return X25519Keypair()


def public_key_from_b64(encoded: str) -> bytes:
    """Decode a URL-safe base64 public key (with or without padding).

    Args:
        encoded: URL-safe base64-encoded public key string.

    Returns:
        Raw 32-byte public key.
    """
    # Add padding if needed
    padded = encoded + "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(padded)
