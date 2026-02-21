"""Shared scalar coercion helpers.

These helpers intentionally centralize common ``object -> scalar|None`` patterns
used across command/MCP boundary code.
"""

from __future__ import annotations


def str_or_none(value: object) -> str | None:
    """Return ``value`` when it is a string, else ``None``."""
    return value if isinstance(value, str) else None


def non_empty_str(value: object) -> str | None:
    """Return stripped non-empty string value, else ``None``."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def dict_str_keys_or_none(value: object) -> dict[str, object] | None:
    """Return a dict with stringified keys, else ``None``."""
    if not isinstance(value, dict):
        return None
    return {str(key): cast_value for key, cast_value in value.items()}


def _coerce_numeric_or_none[NumericT: (int, float)](
    value: object,
    *,
    target_type: type[NumericT],
    allow_numeric_input: bool = False,
    strip_strings: bool = False,
) -> NumericT | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, target_type):
        return value
    if allow_numeric_input and isinstance(value, int | float):
        return target_type(value)
    if not isinstance(value, str):
        return None
    normalized = value.strip() if strip_strings else value
    if strip_strings and not normalized:
        return None
    try:
        return target_type(normalized)
    except ValueError:
        return None


def int_or_none(value: object) -> int | None:
    """Return int values (or numeric strings), excluding booleans."""
    return _coerce_numeric_or_none(value, target_type=int)


def float_or_none(value: object) -> float | None:
    """Return float values (or numeric strings), excluding booleans."""
    return _coerce_numeric_or_none(
        value,
        target_type=float,
        allow_numeric_input=True,
        strip_strings=True,
    )


def strict_int_or_none(value: object) -> int | None:
    """Return int values only (excluding booleans and numeric strings)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


__all__ = [
    "dict_str_keys_or_none",
    "float_or_none",
    "int_or_none",
    "non_empty_str",
    "str_or_none",
    "strict_int_or_none",
]
