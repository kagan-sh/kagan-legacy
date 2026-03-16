from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse

from kagan.mcp._policy import AccessTier
from kagan.wire.envelopes import WireEnvelope


def _effective_tier(ctx: Any | None) -> AccessTier:
    opts = getattr(ctx, "opts", None)
    if bool(getattr(opts, "admin", False)):
        return AccessTier.ADMIN
    if bool(getattr(opts, "readonly", False)):
        return AccessTier.READONLY
    return AccessTier.STANDARD


def is_access_allowed(ctx: Any | None, minimum_tier: AccessTier) -> bool:
    return _effective_tier(ctx).value >= minimum_tier.value


def http_forbidden(*, operation: str, minimum_tier: AccessTier) -> JSONResponse:
    label = minimum_tier.name.lower()
    payload = WireEnvelope(
        ok=False,
        error=f"{operation} requires {label} access.",
    ).model_dump()
    payload["error_code"] = "ACCESS_TIER_FORBIDDEN"
    return JSONResponse(payload, status_code=403)


def websocket_forbidden(
    *,
    event_type: str,
    operation: str,
    minimum_tier: AccessTier,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    label = minimum_tier.name.lower()
    payload: dict[str, object] = {
        "t": event_type,
        "error": f"{operation} requires {label} access.",
        "error_code": "ACCESS_TIER_FORBIDDEN",
    }
    if extra:
        payload.update(extra)
    return payload
