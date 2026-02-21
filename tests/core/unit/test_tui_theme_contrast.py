from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from kagan.tui.theme import KAGAN_THEME, KAGAN_THEME_256

if TYPE_CHECKING:
    from textual.theme import Theme

_MIN_WCAG_AA_RATIO = 4.5

_BASE_THEME_PAIRS: tuple[tuple[str, str], ...] = (
    ("text", "background"),
    ("text", "kanban-background"),
    ("text", "surface"),
    ("text", "panel"),
    ("text-muted", "background"),
    ("text-muted", "surface"),
    ("text-muted", "panel"),
    ("text-muted", "border"),
    ("text-disabled", "background"),
    ("text-disabled", "surface"),
    ("text-disabled", "panel"),
    ("footer-key-foreground", "background"),
    ("footer-key-foreground", "panel"),
    ("footer-description-foreground", "background"),
    ("footer-description-foreground", "panel"),
    ("primary", "background"),
    ("secondary", "background"),
    ("accent", "background"),
    ("warning", "background"),
    ("error", "background"),
    ("success", "background"),
    ("link-color", "background"),
    ("background", "primary"),
    ("background", "secondary"),
    ("background", "accent"),
    ("background", "warning"),
    ("background", "error"),
    ("background", "success"),
    ("button-color-foreground", "primary"),
    ("button-color-foreground", "secondary"),
    ("button-color-foreground", "warning"),
    ("button-color-foreground", "success"),
)

_TCSS_ALIAS_PAIRS: tuple[tuple[str, str], ...] = (
    ("priority-high-text", "priority-high"),
    ("priority-medium-text", "priority-medium"),
    ("priority-low-text", "priority-low"),
    ("success-text", "success"),
    ("warning-text", "warning"),
    ("error-text", "error"),
)


def _hex_to_rgba(value: str) -> tuple[float, float, float, float]:
    color = value.strip().lower().lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color) + "ff"
    elif len(color) == 4:
        color = "".join(ch * 2 for ch in color)
    elif len(color) == 6:
        color = color + "ff"
    elif len(color) == 8:
        pass
    else:
        raise ValueError(f"Unsupported color format: {value}")
    red, green, blue, alpha = (int(color[idx : idx + 2], 16) / 255 for idx in (0, 2, 4, 6))
    return red, green, blue, alpha


def _composite(
    foreground: tuple[float, float, float, float],
    background: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    fr, fg, fb, fa = foreground
    br, bg, bb, ba = background
    out_alpha = fa + ba * (1 - fa)
    if out_alpha == 0:
        return 0.0, 0.0, 0.0, 0.0
    out_red = (fr * fa + br * ba * (1 - fa)) / out_alpha
    out_green = (fg * fa + bg * ba * (1 - fa)) / out_alpha
    out_blue = (fb * fa + bb * ba * (1 - fa)) / out_alpha
    return out_red, out_green, out_blue, out_alpha


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def _channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = rgb
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast_ratio(foreground_hex: str, background_hex: str) -> float:
    foreground = _hex_to_rgba(foreground_hex)
    background = _hex_to_rgba(background_hex)
    if foreground[3] < 1.0:
        foreground = _composite(foreground, background)
    luminance_foreground = _relative_luminance(foreground[:3])
    luminance_background = _relative_luminance(background[:3])
    lighter, darker = (
        max(luminance_foreground, luminance_background),
        min(luminance_foreground, luminance_background),
    )
    return (lighter + 0.05) / (darker + 0.05)


def _require_color_token(token_name: str, value: str | None) -> str:
    if value is None:
        raise ValueError(f"Theme token {token_name!r} is undefined")
    return value


def _theme_tokens(theme: Theme) -> dict[str, str]:
    tokens = {
        "text": _require_color_token("text", theme.foreground),
        "background": _require_color_token("background", theme.background),
        "surface": _require_color_token("surface", theme.surface),
        "panel": _require_color_token("panel", theme.panel),
        "primary": _require_color_token("primary", theme.primary),
        "secondary": _require_color_token("secondary", theme.secondary),
        "accent": _require_color_token("accent", theme.accent),
        "warning": _require_color_token("warning", theme.warning),
        "error": _require_color_token("error", theme.error),
        "success": _require_color_token("success", theme.success),
    }
    for token_name, token_value in theme.variables.items():
        tokens[token_name] = _require_color_token(token_name, token_value)
    return tokens


def _load_tcss_variables() -> dict[str, str]:
    tcss = Path("src/kagan/tui/styles/kagan.tcss").read_text()
    return {
        name: value.strip()
        for name, value in re.findall(r"^\s*\$([\w-]+):\s*([^;]+);", tcss, flags=re.MULTILINE)
    }


def _resolve_color_expression(
    expression: str,
    *,
    theme_tokens: dict[str, str],
    tcss_variables: dict[str, str],
    seen: tuple[str, ...] = (),
) -> str:
    value = expression.strip()
    if value.startswith("$"):
        token_name = value[1:]
        if token_name in seen:
            raise ValueError(f"Variable cycle detected: {' -> '.join((*seen, token_name))}")
        if token_name in tcss_variables:
            return _resolve_color_expression(
                tcss_variables[token_name],
                theme_tokens=theme_tokens,
                tcss_variables=tcss_variables,
                seen=(*seen, token_name),
            )
        if token_name in theme_tokens:
            return _resolve_color_expression(
                theme_tokens[token_name],
                theme_tokens=theme_tokens,
                tcss_variables=tcss_variables,
                seen=(*seen, token_name),
            )
        raise KeyError(f"Unknown color token: {token_name}")
    if value.lower() == "transparent":
        raise ValueError("Transparent cannot be used in contrast checks")
    if value.startswith("#"):
        return value
    raise ValueError(f"Unsupported color expression for contrast checks: {expression}")


def _resolve_token_color(
    token_name: str,
    *,
    theme_tokens: dict[str, str],
    tcss_variables: dict[str, str],
) -> str:
    if token_name in tcss_variables:
        return _resolve_color_expression(
            f"${token_name}",
            theme_tokens=theme_tokens,
            tcss_variables=tcss_variables,
        )
    if token_name in theme_tokens:
        return _resolve_color_expression(
            theme_tokens[token_name],
            theme_tokens=theme_tokens,
            tcss_variables=tcss_variables,
        )
    raise KeyError(f"Unknown token name: {token_name}")


@pytest.mark.parametrize("theme", [KAGAN_THEME, KAGAN_THEME_256], ids=lambda theme: theme.name)
def test_tui_theme_contrast_meets_wcag_aa(theme: Theme) -> None:
    theme_tokens = _theme_tokens(theme)
    tcss_variables = _load_tcss_variables()

    failures: list[str] = []
    for foreground_token, background_token in (*_BASE_THEME_PAIRS, *_TCSS_ALIAS_PAIRS):
        foreground = _resolve_token_color(
            foreground_token,
            theme_tokens=theme_tokens,
            tcss_variables=tcss_variables,
        )
        background = _resolve_token_color(
            background_token,
            theme_tokens=theme_tokens,
            tcss_variables=tcss_variables,
        )
        ratio = _contrast_ratio(foreground, background)
        if ratio < _MIN_WCAG_AA_RATIO:
            failures.append(
                f"{foreground_token} on {background_token}: {ratio:.2f} < {_MIN_WCAG_AA_RATIO:.1f}"
            )

    assert not failures, "Contrast ratios below WCAG AA:\n" + "\n".join(failures)


def test_tcss_text_opacity_keeps_readable_text_fully_opaque() -> None:
    tcss = Path("src/kagan/tui/styles/kagan.tcss").read_text()

    failures: list[str] = []
    for match in re.finditer(r"text-opacity:\s*(\d+)%\s*;", tcss):
        opacity = int(match.group(1))
        if opacity < 100:
            line_number = tcss.count("\n", 0, match.start()) + 1
            failures.append(f"line {line_number}: {opacity}%")

    assert not failures, "Readable text must stay fully opaque:\n" + "\n".join(failures)
