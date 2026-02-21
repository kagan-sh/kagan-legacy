from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from kagan.core.commands._parsing import parse_queue_lane
from kagan.core.commands._responses import CommandCode, error_response

if TYPE_CHECKING:
    from kagan.core.api import KaganAPI
    from kagan.core.bootstrap import AppContext
    from kagan.core.domain.enums import QueueLane


def api_from_context(ctx: AppContext) -> KaganAPI:
    from kagan.core.api import KaganAPI

    if isinstance(ctx, KaganAPI):
        return ctx
    api = getattr(ctx, "api", None)
    if api is None:
        raise ValueError("API context is not initialized")
    return cast("KaganAPI", api)


def parse_queue_lane_or_error(
    params: dict[str, Any],
) -> tuple[QueueLane | None, dict[str, Any] | None]:
    try:
        return parse_queue_lane(params.get("lane")), None
    except ValueError as exc:
        return None, error_response(message=str(exc), code=CommandCode.INVALID_LANE)


__all__ = ["api_from_context", "parse_queue_lane_or_error"]
