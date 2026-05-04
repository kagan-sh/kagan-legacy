"""kagan.server._middleware — Security middleware for the HTTP API server.

Provides:
- Security headers (CWE-693)
- CORS configuration (CWE-346)
- CSRF protection via content-type enforcement (CWE-352)
- In-memory rate limiting (CWE-770)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.types import ASGIApp, Receive, Scope, Send


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "0",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    ),
}

_CORS_ALLOWED_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8765",
    "http://localhost:8766",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8765",
    "http://127.0.0.1:8766",
]

_STATE_CHANGING_METHODS: frozenset[str] = frozenset({"POST", "PATCH", "DELETE"})
_RATE_LIMITED_PREFIXES: tuple[str, ...] = (
    "/api/",
    "/mcp",
)

# Rate-limit windows (seconds) and thresholds.
# GET / SSE endpoints: 300/min per key.
# POST (state-mutating) endpoints: 60/min per key.
# Key is the auth token when a Bearer header is present, otherwise the client IP.
_RATE_WINDOW_SECONDS: int = 60
_RATE_LIMIT_DEFAULT: int = 300
_RATE_LIMIT_POST: int = 60
# How often to purge stale entries (seconds).
_RATE_CLEANUP_INTERVAL: int = 120


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware:
    """Inject security headers into every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for name, value in _SECURITY_HEADERS.items():
                    headers.append((name.lower().encode(), value.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, _send_with_headers)


# ---------------------------------------------------------------------------
# CSRF Protection Middleware
# ---------------------------------------------------------------------------

# Paths that are exempt from CSRF content-type checks.
# API endpoints are protected by CORS instead (browsers cannot send
# cross-origin JSON requests without a preflight check).
_CSRF_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/",  # REST API — CORS-protected, clients always send JSON
    "/mcp",  # MCP protocol endpoints have their own auth
    "/health",
)


class CSRFMiddleware:
    """Reject state-changing requests that lack ``Content-Type: application/json``.

    Browsers cannot send cross-origin requests with a JSON content-type
    without triggering a CORS preflight, making this a lightweight but
    effective CSRF mitigation.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        method = request.method

        if method not in _STATE_CHANGING_METHODS:
            await self.app(scope, receive, send)
            return

        path = request.url.path
        if any(path.startswith(prefix) for prefix in _CSRF_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            logger.debug(
                "CSRF check failed: {} {} content-type='{}'",
                method,
                path,
                content_type,
            )
            response = JSONResponse(
                {"ok": False, "error": "Invalid Content-Type; expected application/json"},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Rate Limiting Middleware
# ---------------------------------------------------------------------------


class _BucketEntry:
    """Track request counts within a rolling window."""

    __slots__ = ("count", "window_start")

    def __init__(self, window_start: float) -> None:
        self.window_start = window_start
        self.count = 1


class RateLimitMiddleware:
    """Simple in-memory per-IP rate limiter.

    - Regular endpoints: ``_RATE_LIMIT_DEFAULT`` requests per minute.
    - POST endpoints: ``_RATE_LIMIT_POST`` requests per minute.

    Returns ``429 Too Many Requests`` when a limit is exceeded.
    Stale entries are cleaned up periodically.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._buckets: dict[str, _BucketEntry] = {}
        self._post_buckets: dict[str, _BucketEntry] = {}
        self._last_cleanup = time.monotonic()

    # -- helpers --

    @staticmethod
    def _client_ip(scope: Scope) -> str:
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"

    @staticmethod
    def _rate_limit_key(scope: Scope) -> str:
        """Return the rate-limit key for this request.

        Auth-token keying prevents a shared IP (e.g. NAT, corporate proxy) from
        starving legitimate users: each token gets its own independent quota.
        Falls back to IP when no Bearer token is present.
        """
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode("latin-1", errors="replace")
        if auth.startswith("Bearer ") and len(auth) > 7:
            return f"token:{auth[7:].strip()}"
        client = scope.get("client")
        return client[0] if client else "unknown"

    @staticmethod
    def _safe_log_key(key: str) -> str:
        """Return a non-reversible label safe to emit to logs.

        Token keys are hashed so a leaked log line cannot replay against the
        API; IP keys are passed through (they are not credentials).
        """
        if key.startswith("token:"):
            import hashlib

            digest = hashlib.sha256(key[len("token:") :].encode()).hexdigest()
            return f"token:{digest[:8]}"
        return key

    def _cleanup_stale(self, now: float) -> None:
        if now - self._last_cleanup < _RATE_CLEANUP_INTERVAL:
            return
        self._last_cleanup = now

        cutoff = now - _RATE_WINDOW_SECONDS
        purged = 0
        for bucket_map in (self._buckets, self._post_buckets):
            stale_keys = [k for k, v in bucket_map.items() if v.window_start < cutoff]
            for key in stale_keys:
                del bucket_map[key]
            purged += len(stale_keys)

        if purged:
            logger.debug("Rate-limiter cleanup: purged {} stale entries", purged)

    def _check_limit(
        self,
        buckets: dict[str, _BucketEntry],
        key: str,
        limit: int,
        now: float,
    ) -> bool:
        """Return True if the request should be allowed, False if rate-limited."""
        entry = buckets.get(key)
        if entry is None or now - entry.window_start >= _RATE_WINDOW_SECONDS:
            buckets[key] = _BucketEntry(now)
            return True

        entry.count += 1
        return entry.count <= limit

    @staticmethod
    def _should_rate_limit(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in _RATE_LIMITED_PREFIXES)

    # -- ASGI interface --

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        self._cleanup_stale(now)

        path = scope.get("path", "")
        if not self._should_rate_limit(path):
            await self.app(scope, receive, send)
            return

        key = self._rate_limit_key(scope)
        method = scope.get("method", "GET")

        # Check general rate limit.
        if not self._check_limit(self._buckets, key, _RATE_LIMIT_DEFAULT, now):
            logger.warning("Rate limit exceeded for key={} (general)", self._safe_log_key(key))
            response = JSONResponse(
                {"ok": False, "error": "Rate limit exceeded — try again later"},
                status_code=429,
                headers={"Retry-After": str(_RATE_WINDOW_SECONDS)},
            )
            await response(scope, receive, send)
            return

        # Check stricter POST rate limit.
        if method == "POST" and not self._check_limit(
            self._post_buckets, key, _RATE_LIMIT_POST, now
        ):
            logger.warning("Rate limit exceeded for key={} (POST)", self._safe_log_key(key))
            response = JSONResponse(
                {"ok": False, "error": "Rate limit exceeded for POST — try again later"},
                status_code=429,
                headers={"Retry-After": str(_RATE_WINDOW_SECONDS)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Public: wire all middleware into a Starlette app
# ---------------------------------------------------------------------------


def install_security_middleware(app: Starlette) -> None:
    """Add all security middleware to the given Starlette application.

    Middleware is added in reverse order of desired execution — Starlette
    wraps from the outside in, so the **last** ``add_middleware`` call runs
    **first** on each request.

    Execution order per request:
    1. Rate limiting (outermost — reject early)
    2. CORS (handle preflight before body inspection)
    3. CSRF content-type check
    4. Security headers (innermost — always applied to the response)
    """
    # 4. Security headers — innermost, runs last on request / first on response.
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. CSRF — after CORS has handled OPTIONS preflight.
    app.add_middleware(CSRFMiddleware)

    # 2. CORS — Starlette's built-in middleware handles preflight and headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # 1. Rate limiting — outermost, runs first.
    app.add_middleware(RateLimitMiddleware)

    logger.info("Security middleware installed (headers, CORS, CSRF, rate-limit)")
