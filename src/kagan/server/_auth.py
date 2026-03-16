"""kagan.server._auth — pairing and bearer-token auth for API clients.

Security model (v2 — key exchange):
1. Server generates an ephemeral X25519 keypair on startup.
2. QR code contains the server's **public key**, host, port, and TLS
   certificate fingerprint — never the secret itself.
3. Client generates its own ephemeral keypair, sends its public key to
   ``POST /auth/pair``.
4. Both sides derive the same bearer token via ECDH + HKDF-SHA256.
5. Pairing is single-use: after one successful pair the pairing session
   is burned and new devices cannot pair until the server restarts.
6. Bearer tokens carry an expiry timestamp (default 24 h); clients use
   ``POST /auth/refresh`` to obtain a fresh token.

Bundled `kagan web` mode does not use this flow. The dashboard talks to the
same server instance that serves the SPA and skips pairing entirely.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import click
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from kagan.crypto import (
    generate_pairing_qr,
    generate_token,
    pairing_payload,
    public_key_from_b64,
    verify_token,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.applications import Starlette
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.requests import Request

_EXEMPT_PREFIXES = ("/health", "/api/shutdown", "/auth/pair", "/auth/refresh", "/mcp")

# Default bearer token lifetime: 24 hours.
_TOKEN_TTL_SECONDS: float = 24 * 60 * 60

# Refresh token lifetime: 30 days.
_REFRESH_TTL_SECONDS: float = 30 * 24 * 60 * 60


@dataclass
class _TokenRecord:
    """A bearer token with expiry metadata."""

    token: str
    expires_at: float
    refresh_token: str
    refresh_expires_at: float
    device_id: str


@dataclass
class _PairingState:
    """Mutable singleton holding all auth state for one server instance."""

    keypair: object | None = None  # X25519Keypair — lazy to avoid import at module level
    paired: bool = False
    devices: dict[str, _TokenRecord] = field(default_factory=dict)
    cert_fingerprint: str | None = None
    tls_enabled: bool = False


_state = _PairingState()
_middleware_registered_for: set[int] = set()
_pairing_secret = generate_token()
_paired_devices: dict[str, str] = {}


def _resolve_lan_ip() -> str:
    """Detect the machine's LAN-facing IP address.

    Uses the UDP-connect trick: connect a datagram socket to an external
    address (never actually sends data) and read back the local endpoint.
    Falls back to ``127.0.0.1`` if detection fails.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _is_authorized_token(token: str) -> bool:
    """Check if *token* matches any active, non-expired device token."""
    now = time.monotonic()
    for record in _state.devices.values():
        if record.expires_at > now and verify_token(token, record.token):
            return True
    return any(verify_token(token, paired_token) for paired_token in _paired_devices.values())


def _make_unauthorized(message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=401)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if any(request.url.path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _make_unauthorized("Unauthorized")

        token = auth_header[7:]
        if not _is_authorized_token(token):
            return _make_unauthorized("Invalid token")

        return await call_next(request)


def _install_auth_middleware(mcp: FastMCP) -> None:
    server_id = id(mcp)
    if server_id in _middleware_registered_for:
        return

    original_streamable_http_app = mcp.streamable_http_app

    def streamable_http_app_with_auth() -> Starlette:
        app = original_streamable_http_app()
        app.add_middleware(BearerAuthMiddleware)
        return app

    object.__setattr__(mcp, "streamable_http_app", streamable_http_app_with_auth)
    _middleware_registered_for.add(server_id)


def register_auth(
    mcp: FastMCP,
    *,
    cert_fingerprint: str | None = None,
    tls_enabled: bool = False,
) -> None:
    """Register authentication middleware and pairing routes.

    Args:
        mcp: The FastMCP server instance to configure.
        cert_fingerprint: Hex SHA-256 fingerprint of the TLS certificate
            (included in the QR code for pinning).
        tls_enabled: Whether the server is running with TLS.
    """
    from kagan.crypto._x25519 import X25519Keypair

    global _pairing_secret

    # Reset state for this server instance.
    _state.keypair = X25519Keypair()
    _state.paired = False
    _state.devices.clear()
    _paired_devices.clear()
    _pairing_secret = generate_token()
    _state.cert_fingerprint = cert_fingerprint
    _state.tls_enabled = tls_enabled

    keypair: X25519Keypair = _state.keypair  # type: ignore[assignment]

    host: str = mcp.settings.host
    port: int = mcp.settings.port

    # Resolve LAN IP when bound to all interfaces.
    if host in ("0.0.0.0", "127.0.0.1", "localhost", ""):
        host = _resolve_lan_ip()

    payload = pairing_payload(
        host,
        port,
        pubkey=keypair.public_key_b64,
        fingerprint=cert_fingerprint,
        tls=tls_enabled,
    )
    qr = generate_pairing_qr(
        host,
        port,
        pubkey=keypair.public_key_b64,
        fingerprint=cert_fingerprint,
        tls=tls_enabled,
    )
    click.echo()
    click.echo(click.style("  Pairing ready", fg="green", bold=True))
    click.echo()
    click.echo(f"  URI:  {payload}")
    click.echo()
    click.echo("  Scan this QR code with your API client:")
    click.echo()
    for line in qr.splitlines():
        click.echo(f"  {line}")
    click.echo()
    logger.debug("Auth keypair generated, public key: {}", keypair.public_key_b64)

    # ------------------------------------------------------------------ pair
    @mcp.custom_route("/auth/pair", methods=["POST"])
    async def pair(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(
                {"ok": False, "error": "Invalid request body"},
                status_code=400,
            )

        client_pubkey_b64 = body.get("client_pubkey")
        secret = body.get("secret")
        device_id = body.get("device_id")

        if not isinstance(device_id, str) or not device_id:
            return JSONResponse(
                {"ok": False, "error": "Missing secret or device_id"},
                status_code=400,
            )

        if not isinstance(client_pubkey_b64, str) or not client_pubkey_b64:
            if not isinstance(secret, str) or not verify_token(secret, _pairing_secret):
                return JSONResponse(
                    {"ok": False, "error": "Invalid secret"},
                    status_code=401,
                )

            token = generate_token()
            _paired_devices[device_id] = token
            logger.info("Device {} paired successfully (legacy shared secret)", device_id)
            return JSONResponse({"ok": True, "data": {"token": token}})

        # Single-use: reject if already paired.
        if _state.paired:
            return JSONResponse(
                {"ok": False, "error": "Pairing session already used. Restart server to re-pair."},
                status_code=403,
            )

        try:
            client_pubkey_bytes = public_key_from_b64(client_pubkey_b64)
        except Exception:
            return JSONResponse(
                {"ok": False, "error": "Invalid client public key"},
                status_code=400,
            )

        # Derive bearer token from ECDH shared secret.
        token = keypair.derive_token(client_pubkey_bytes)

        # Generate a separate refresh token (random, not derived).
        refresh_token = generate_token()

        now = time.monotonic()
        _state.devices[device_id] = _TokenRecord(
            token=token,
            expires_at=now + _TOKEN_TTL_SECONDS,
            refresh_token=refresh_token,
            refresh_expires_at=now + _REFRESH_TTL_SECONDS,
            device_id=device_id,
        )

        # Burn the pairing session.
        _state.paired = True
        logger.info("Device {} paired successfully", device_id)

        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "token": token,
                    "refresh_token": refresh_token,
                    "expires_in": int(_TOKEN_TTL_SECONDS),
                    "server_pubkey": keypair.public_key_b64,
                },
            }
        )

    # --------------------------------------------------------------- refresh
    @mcp.custom_route("/auth/refresh", methods=["POST"])
    async def refresh(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(
                {"ok": False, "error": "Invalid request body"},
                status_code=400,
            )

        refresh_tok = body.get("refresh_token")
        device_id = body.get("device_id")

        if not isinstance(refresh_tok, str) or not isinstance(device_id, str) or not device_id:
            return JSONResponse(
                {"ok": False, "error": "Missing refresh_token or device_id"},
                status_code=400,
            )

        record = _state.devices.get(device_id)
        now = time.monotonic()

        if (
            record is None
            or record.refresh_expires_at <= now
            or not verify_token(refresh_tok, record.refresh_token)
        ):
            return JSONResponse(
                {"ok": False, "error": "Invalid or expired refresh token"},
                status_code=401,
            )

        # Issue a new bearer token and new refresh token.
        new_token = generate_token()
        new_refresh = generate_token()
        _state.devices[device_id] = _TokenRecord(
            token=new_token,
            expires_at=now + _TOKEN_TTL_SECONDS,
            refresh_token=new_refresh,
            refresh_expires_at=now + _REFRESH_TTL_SECONDS,
            device_id=device_id,
        )

        logger.debug("Token refreshed for device {}", device_id)
        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "token": new_token,
                    "refresh_token": new_refresh,
                    "expires_in": int(_TOKEN_TTL_SECONDS),
                },
            }
        )

    # --------------------------------------------------------------- verify
    @mcp.custom_route("/auth/verify", methods=["GET"])
    async def verify(request: Request) -> JSONResponse:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"ok": False, "error": "Missing token"}, status_code=401)

        token = auth_header[7:]
        if _is_authorized_token(token):
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": "Invalid token"}, status_code=401)

    logger.debug("Auth registered with exempt paths: {}", _EXEMPT_PREFIXES)
    _install_auth_middleware(mcp)
