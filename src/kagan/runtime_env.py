"""Sanitize env vars for subprocess execution: allowlist-based approach."""

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping

_ESSENTIAL_ENV_POSIX: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "PWD",
        "LANG",
        "LC_ALL",
        "TERM",
        "EDITOR",
        "SSH_AUTH_SOCK",
    }
)

_ESSENTIAL_ENV_WINDOWS: frozenset[str] = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
        "USERNAME",
        "COMPUTERNAME",
        "USERDOMAIN",
        "LANG",
        "LC_ALL",
        "EDITOR",
    }
)

_NOISY_ENV_KEYS_BY_PLATFORM: dict[str, tuple[str, ...]] = {
    "darwin": (
        "MallocStackLogging",
        "MallocStackLoggingNoCompact",
        "MALLOCSTACKLOGGING",
        "MALLOCSTACKLOGGINGNOCOMPACT",
    ),
    "linux": (),
    "win32": (),
}

_NOISY_ENV_SUBSTRINGS_BY_PLATFORM: dict[str, tuple[str, ...]] = {
    "darwin": ("mallocstacklogging",),
    "linux": (),
    "win32": (),
}


def _platform_key(platform_name: str | None = None) -> str:
    return (platform_name or sys.platform).lower()


def _essential_env(platform_name: str | None = None) -> frozenset[str]:
    """Return platform-appropriate essential env var names."""
    return (
        _ESSENTIAL_ENV_WINDOWS if _platform_key(platform_name) == "win32" else _ESSENTIAL_ENV_POSIX
    )


def noisy_env_keys(platform_name: str | None = None) -> tuple[str, ...]:
    """Get noisy environment variable keys for platform."""
    return _NOISY_ENV_KEYS_BY_PLATFORM.get(_platform_key(platform_name), ())


def strip_noisy_environment_variables(
    env: MutableMapping[str, str],
    *,
    platform_name: str | None = None,
) -> tuple[str, ...]:
    """Remove noisy env vars from mapping in place; return removed keys."""
    platform_key = _platform_key(platform_name)
    exact_lower = {key.lower() for key in noisy_env_keys(platform_key)}
    substrings = _NOISY_ENV_SUBSTRINGS_BY_PLATFORM.get(platform_key, ())

    removed = [
        key
        for key in tuple(env)
        if key.lower() in exact_lower or any(sub in key.lower() for sub in substrings)
    ]
    for key in removed:
        env.pop(key, None)
    return tuple(removed)


def sanitize_startup_environment() -> tuple[str, ...]:
    """Sanitize current process env at startup; return removed keys."""
    return strip_noisy_environment_variables(os.environ)


def build_sanitized_subprocess_environment(
    base_env: Mapping[str, str] | None = None,
    *,
    allow_extra: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> dict[str, str]:
    """Build a subprocess env from an allowlist of essential vars.

    The allowlist is the security boundary: only known-safe names pass, so
    secrets and interpreter-specific vars in the parent env never propagate.
    """
    source_env = base_env if base_env is not None else os.environ
    sanitized = {key: source_env[key] for key in _essential_env(platform_name) if key in source_env}

    # A child must never block on a git credential prompt; callers may override.
    sanitized.setdefault("GIT_TERMINAL_PROMPT", "0")

    if allow_extra:
        sanitized.update(allow_extra)

    return sanitized
