"""Canonical PAIR terminal backend catalog and helpers."""

__all__ = [
    "ANTIGRAVITY_BACKEND",
    "CURSOR_BACKEND",
    "KIRO_BACKEND",
    "NVIM_BACKEND",
    "PAIR_TERMINAL_BACKEND_SELECT_OPTIONS",
    "PAIR_TERMINAL_BACKEND_SPECS",
    "PAIR_TERMINAL_BACKEND_SPECS_BY_VALUE",
    "PAIR_TERMINAL_BACKEND_VALUES",
    "PAIR_TERMINAL_BACKEND_VALUE_SET",
    "TMUX_BACKEND",
    "UNIX_PAIR_TERMINAL_FALLBACK_ORDER",
    "VSCODE_BACKEND",
    "WINDOWS_PAIR_TERMINAL_FALLBACK_ORDER",
    "WINDSURF_BACKEND",
    "PairTerminalBackendLiteral",
    "PairTerminalBackendSpec",
    "coerce_pair_terminal_backend",
    "default_pair_terminal_backend_for_os",
    "pair_terminal_backend_executable",
    "pair_terminal_backend_fallback_order",
    "pair_terminal_backend_install_hint",
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

PAIR_TERMINAL_BACKEND_VALUES: Final = (
    TMUX_BACKEND,
    NVIM_BACKEND,
    VSCODE_BACKEND,
    CURSOR_BACKEND,
    WINDSURF_BACKEND,
    KIRO_BACKEND,
    ANTIGRAVITY_BACKEND,
)
PairTerminalBackendLiteral = Literal[
    "tmux",
    "nvim",
    "vscode",
    "cursor",
    "windsurf",
    "kiro",
    "antigravity",
]

PAIR_TERMINAL_BACKEND_VALUE_SET: Final[frozenset[str]] = frozenset(PAIR_TERMINAL_BACKEND_VALUES)


@dataclass(frozen=True, slots=True)
class PairTerminalBackendSpec:
    value: PairTerminalBackendLiteral
    label: str
    executable: str
    install_hint: str


PAIR_TERMINAL_BACKEND_SPECS: Final[tuple[PairTerminalBackendSpec, ...]] = (
    PairTerminalBackendSpec(
        value=TMUX_BACKEND,
        label="tmux",
        executable="tmux",
        install_hint="https://github.com/tmux/tmux/wiki/Installing",
    ),
    PairTerminalBackendSpec(
        value=NVIM_BACKEND,
        label="Neovim",
        executable="nvim",
        install_hint="https://neovim.io",
    ),
    PairTerminalBackendSpec(
        value=VSCODE_BACKEND,
        label="VS Code",
        executable="code",
        install_hint="https://code.visualstudio.com/download",
    ),
    PairTerminalBackendSpec(
        value=CURSOR_BACKEND,
        label="Cursor",
        executable="cursor",
        install_hint="https://cursor.com/downloads",
    ),
    PairTerminalBackendSpec(
        value=WINDSURF_BACKEND,
        label="Windsurf",
        executable="windsurf",
        install_hint="https://windsurf.com/download",
    ),
    PairTerminalBackendSpec(
        value=KIRO_BACKEND,
        label="Kiro",
        executable="kiro",
        install_hint="https://kiro.dev/downloads",
    ),
    PairTerminalBackendSpec(
        value=ANTIGRAVITY_BACKEND,
        label="Antigravity",
        executable="agy",
        install_hint="https://antigravity.dev",
    ),
)

PAIR_TERMINAL_BACKEND_SPECS_BY_VALUE: Final[dict[str, PairTerminalBackendSpec]] = {
    spec.value: spec for spec in PAIR_TERMINAL_BACKEND_SPECS
}
PAIR_TERMINAL_BACKEND_SELECT_OPTIONS: Final[tuple[tuple[str, str], ...]] = tuple(
    (spec.label, spec.value) for spec in PAIR_TERMINAL_BACKEND_SPECS
)

WINDOWS_PAIR_TERMINAL_FALLBACK_ORDER: Final[tuple[PairTerminalBackendLiteral, ...]] = (
    VSCODE_BACKEND,
    CURSOR_BACKEND,
    WINDSURF_BACKEND,
    KIRO_BACKEND,
    ANTIGRAVITY_BACKEND,
    NVIM_BACKEND,
)
UNIX_PAIR_TERMINAL_FALLBACK_ORDER: Final[tuple[PairTerminalBackendLiteral, ...]] = (
    NVIM_BACKEND,
    VSCODE_BACKEND,
    CURSOR_BACKEND,
    WINDSURF_BACKEND,
    KIRO_BACKEND,
    ANTIGRAVITY_BACKEND,
)


def coerce_pair_terminal_backend(value: object) -> PairTerminalBackendLiteral | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in PAIR_TERMINAL_BACKEND_VALUE_SET:
            return cast("PairTerminalBackendLiteral", normalized)
    return None


def default_pair_terminal_backend_for_os(os_name: str) -> PairTerminalBackendLiteral:
    return VSCODE_BACKEND if os_name == "windows" else TMUX_BACKEND


def pair_terminal_backend_executable(backend: str) -> str | None:
    spec = PAIR_TERMINAL_BACKEND_SPECS_BY_VALUE.get(backend)
    return spec.executable if spec is not None else None


def pair_terminal_backend_install_hint(backend: str) -> str | None:
    spec = PAIR_TERMINAL_BACKEND_SPECS_BY_VALUE.get(backend)
    return spec.install_hint if spec is not None else None


def pair_terminal_backend_fallback_order(
    *,
    windows: bool,
) -> tuple[PairTerminalBackendLiteral, ...]:
    return WINDOWS_PAIR_TERMINAL_FALLBACK_ORDER if windows else UNIX_PAIR_TERMINAL_FALLBACK_ORDER
