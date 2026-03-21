"""Canonical ATTACHED terminal backend catalog and helpers."""

__all__ = [
    "ANTIGRAVITY_BACKEND",
    "ATTACHED_TERMINAL_BACKEND_SELECT_OPTIONS",
    "ATTACHED_TERMINAL_BACKEND_SPECS",
    "ATTACHED_TERMINAL_BACKEND_SPECS_BY_VALUE",
    "ATTACHED_TERMINAL_BACKEND_VALUES",
    "ATTACHED_TERMINAL_BACKEND_VALUE_SET",
    "CURSOR_BACKEND",
    "KIRO_BACKEND",
    "NVIM_BACKEND",
    "TMUX_BACKEND",
    "UNIX_ATTACHED_TERMINAL_FALLBACK_ORDER",
    "VSCODE_BACKEND",
    "WINDOWS_ATTACHED_TERMINAL_FALLBACK_ORDER",
    "WINDSURF_BACKEND",
    "AttachedTerminalBackendLiteral",
    "AttachedTerminalBackendSpec",
    "attached_terminal_backend_executable",
    "attached_terminal_backend_fallback_order",
    "coerce_attached_terminal_backend",
]

from dataclasses import dataclass
from typing import Final, Literal, cast

TMUX_BACKEND: Final = "tmux"
NVIM_BACKEND: Final = "nvim"
VSCODE_BACKEND: Final = "vscode"
CURSOR_BACKEND: Final = "cursor"
WINDSURF_BACKEND: Final = "windsurf"
KIRO_BACKEND: Final = "kiro"
ANTIGRAVITY_BACKEND: Final = "antigravity"

ATTACHED_TERMINAL_BACKEND_VALUES: Final = (
    TMUX_BACKEND,
    NVIM_BACKEND,
    VSCODE_BACKEND,
    CURSOR_BACKEND,
    WINDSURF_BACKEND,
    KIRO_BACKEND,
    ANTIGRAVITY_BACKEND,
)
AttachedTerminalBackendLiteral = Literal[
    "tmux",
    "nvim",
    "vscode",
    "cursor",
    "windsurf",
    "kiro",
    "antigravity",
]

ATTACHED_TERMINAL_BACKEND_VALUE_SET: Final[frozenset[str]] = frozenset(
    ATTACHED_TERMINAL_BACKEND_VALUES
)


@dataclass(frozen=True, slots=True)
class AttachedTerminalBackendSpec:
    value: AttachedTerminalBackendLiteral
    label: str
    executable: str
    install_hint: str


ATTACHED_TERMINAL_BACKEND_SPECS: Final[tuple[AttachedTerminalBackendSpec, ...]] = (
    AttachedTerminalBackendSpec(
        value=TMUX_BACKEND,
        label="tmux",
        executable="tmux",
        install_hint="https://github.com/tmux/tmux/wiki/Installing",
    ),
    AttachedTerminalBackendSpec(
        value=NVIM_BACKEND,
        label="Neovim",
        executable="nvim",
        install_hint="https://neovim.io",
    ),
    AttachedTerminalBackendSpec(
        value=VSCODE_BACKEND,
        label="VS Code",
        executable="code",
        install_hint="https://code.visualstudio.com/download",
    ),
    AttachedTerminalBackendSpec(
        value=CURSOR_BACKEND,
        label="Cursor",
        executable="cursor",
        install_hint="https://cursor.com/downloads",
    ),
    AttachedTerminalBackendSpec(
        value=WINDSURF_BACKEND,
        label="Windsurf",
        executable="windsurf",
        install_hint="https://windsurf.com/download",
    ),
    AttachedTerminalBackendSpec(
        value=KIRO_BACKEND,
        label="Kiro",
        executable="kiro",
        install_hint="https://kiro.dev/downloads",
    ),
    AttachedTerminalBackendSpec(
        value=ANTIGRAVITY_BACKEND,
        label="Antigravity",
        executable="agy",
        install_hint="https://antigravity.dev",
    ),
)

ATTACHED_TERMINAL_BACKEND_SPECS_BY_VALUE: Final[dict[str, AttachedTerminalBackendSpec]] = {
    spec.value: spec for spec in ATTACHED_TERMINAL_BACKEND_SPECS
}
ATTACHED_TERMINAL_BACKEND_SELECT_OPTIONS: Final[tuple[tuple[str, str], ...]] = tuple(
    (spec.label, spec.value) for spec in ATTACHED_TERMINAL_BACKEND_SPECS
)

WINDOWS_ATTACHED_TERMINAL_FALLBACK_ORDER: Final[tuple[AttachedTerminalBackendLiteral, ...]] = (
    VSCODE_BACKEND,
    CURSOR_BACKEND,
    WINDSURF_BACKEND,
    KIRO_BACKEND,
    ANTIGRAVITY_BACKEND,
    NVIM_BACKEND,
)
UNIX_ATTACHED_TERMINAL_FALLBACK_ORDER: Final[tuple[AttachedTerminalBackendLiteral, ...]] = (
    NVIM_BACKEND,
    VSCODE_BACKEND,
    CURSOR_BACKEND,
    WINDSURF_BACKEND,
    KIRO_BACKEND,
    ANTIGRAVITY_BACKEND,
)


def coerce_attached_terminal_backend(value: object) -> AttachedTerminalBackendLiteral | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ATTACHED_TERMINAL_BACKEND_VALUE_SET:
            return cast("AttachedTerminalBackendLiteral", normalized)
    return None


def attached_terminal_backend_executable(backend: str) -> str | None:
    spec = ATTACHED_TERMINAL_BACKEND_SPECS_BY_VALUE.get(backend)
    return spec.executable if spec is not None else None


def attached_terminal_backend_fallback_order(
    *,
    windows: bool,
) -> tuple[AttachedTerminalBackendLiteral, ...]:
    return (
        WINDOWS_ATTACHED_TERMINAL_FALLBACK_ORDER
        if windows
        else UNIX_ATTACHED_TERMINAL_FALLBACK_ORDER
    )
