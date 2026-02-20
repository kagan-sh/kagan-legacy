from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.config import KaganConfig
from kagan.core.policy import command
from kagan.core.settings import exposed_settings_snapshot, normalize_settings_updates

from ._parsing import str_object_dict

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


@command("settings", "get", profile="maintainer", description="Get admin-exposed settings.")
async def get_settings(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    _ = params
    return {"settings": exposed_settings_snapshot(ctx.config)}


@command(
    "settings",
    "update",
    profile="maintainer",
    mutating=True,
    description="Update allowlisted settings fields.",
)
async def update_settings(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    raw_fields = str_object_dict(params.get("fields"))
    if raw_fields is None:
        return {
            "success": False,
            "message": (
                "fields must be a non-empty object. Use settings_get to see available fields."
            ),
            "updated": {},
            "settings": exposed_settings_snapshot(ctx.config),
        }

    try:
        updates = normalize_settings_updates(raw_fields)
    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
            "updated": {},
            "settings": exposed_settings_snapshot(ctx.config),
        }

    config_data = ctx.config.model_dump(mode="python")
    for key, value in updates.items():
        section, field = key.split(".", 1)
        section_data = config_data.get(section)
        if not isinstance(section_data, dict):
            return {
                "success": False,
                "message": f"Invalid settings section: {section}",
                "updated": {},
                "settings": exposed_settings_snapshot(ctx.config),
            }
        section_data[field] = value

    try:
        next_config = KaganConfig.model_validate(config_data)
    except Exception as exc:
        return {
            "success": False,
            "message": f"Invalid settings update: {exc}",
            "updated": {},
            "settings": exposed_settings_snapshot(ctx.config),
        }

    await next_config.save(ctx.config_path)
    ctx.config = next_config
    return {
        "success": True,
        "message": "Settings updated",
        "updated": updates,
        "settings": exposed_settings_snapshot(ctx.config),
    }


__all__ = ["get_settings", "update_settings"]
