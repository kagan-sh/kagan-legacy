from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from kagan.server._envelope import WireEnvelope

if TYPE_CHECKING:
    from kagan.server.mcp.server import ServerContext


class AccessTier(Enum):
    READONLY = auto()
    STANDARD = auto()
    ADMIN = auto()


def _effective_tier(ctx: ServerContext | None) -> AccessTier:
    opts = getattr(ctx, "opts", None)
    if bool(getattr(opts, "admin", False)):
        return AccessTier.ADMIN
    if bool(getattr(opts, "readonly", False)):
        return AccessTier.READONLY
    return AccessTier.STANDARD


def is_access_allowed(ctx: ServerContext | None, minimum_tier: AccessTier) -> bool:
    return _effective_tier(ctx).value >= minimum_tier.value


def http_forbidden(*, operation: str, minimum_tier: AccessTier) -> JSONResponse:
    label = minimum_tier.name.lower()
    payload = WireEnvelope(
        ok=False,
        error=f"{operation} requires {label} access.",
    ).model_dump()
    payload["error_code"] = "ACCESS_TIER_FORBIDDEN"
    return JSONResponse(payload, status_code=403)
