"""Runtime environment utilities for subprocess sanitization.

This module provides functions to sanitize environment variables before passing
them to subprocesses, using an allowlist-based approach that keeps only essential
variables while stripping sensitive credentials and Python-specific settings.
"""

import os
import sys
from collections.abc import Mapping, MutableMapping

# Essential environment variables that should always be preserved in subprocesses.
# Platform-specific sets are selected at call time via _essential_env().

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


def _essential_env(platform_name: str | None = None) -> frozenset[str]:
    """Return the platform-appropriate set of essential environment variable names.

    Args:
        platform_name: Platform identifier (win32, linux, darwin, …).
            Defaults to sys.platform.

    Returns:
        Frozenset of environment variable names that must be preserved.
    """
    key = (platform_name or sys.platform).lower()
    return _ESSENTIAL_ENV_WINDOWS if key == "win32" else _ESSENTIAL_ENV_POSIX


# Sensitive patterns that should be stripped from environment variables
# These match anywhere in the variable name (case-insensitive)
_SENSITIVE_PATTERNS: tuple[str, ...] = (
    "TOKEN",
    "KEY",
    "SECRET",
    "PASSWORD",
    "AWS_",
    "AZURE_",
    "GCP_",
    "OPENAI_",
    "ANTHROPIC_",
    "GITHUB_",
    "LD_PRELOAD",
    "DYLD_INSERT_LIBRARIES",
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


def noisy_env_keys(platform_name: str | None = None) -> tuple[str, ...]:
    """Get noisy environment variable keys for a given platform.

    Args:
        platform_name: Platform identifier (darwin, linux, win32). Defaults to sys.platform.

    Returns:
        Tuple of environment variable keys that are noisy on the platform.
    """
    key = (platform_name or sys.platform).lower()
    return _NOISY_ENV_KEYS_BY_PLATFORM.get(key, ())


def strip_noisy_environment_variables(
    env: MutableMapping[str, str],
    *,
    platform_name: str | None = None,
) -> tuple[str, ...]:
    """Remove noisy environment variables from the given environment.

    Args:
        env: Environment variable mapping to modify in place.
        platform_name: Platform identifier for platform-specific noisy keys.

    Returns:
        Tuple of keys that were removed.
    """
    platform_key = (platform_name or sys.platform).lower()
    exact_keys = noisy_env_keys(platform_key)
    exact_keys_lower = {key.lower() for key in exact_keys}
    noisy_substrings = _NOISY_ENV_SUBSTRINGS_BY_PLATFORM.get(platform_key, ())

    removed: list[str] = []
    for key in tuple(env.keys()):
        key_lower = key.lower()
        if key in exact_keys or key_lower in exact_keys_lower:
            removed.append(key)
            env.pop(key, None)
            continue
        if any(substring in key_lower for substring in noisy_substrings):
            removed.append(key)
            env.pop(key, None)
    return tuple(removed)


def sanitize_startup_environment() -> tuple[str, ...]:
    """Sanitize the current process environment at startup.

    Returns:
        Tuple of keys that were removed from os.environ.
    """
    return strip_noisy_environment_variables(os.environ)


def _is_sensitive_key(key: str) -> bool:
    """Check if an environment variable key matches sensitive patterns.

    Args:
        key: Environment variable name to check.

    Returns:
        True if the key matches any sensitive pattern.
    """
    key_upper = key.upper()
    return any(pattern in key_upper for pattern in _SENSITIVE_PATTERNS)


def _is_python_key(key: str) -> bool:
    """Check if an environment variable key is a Python-specific variable.

    Args:
        key: Environment variable name to check.

    Returns:
        True if the key starts with PYTHON (case-insensitive).
    """
    return key.upper().startswith("PYTHON")


def build_sanitized_subprocess_environment(
    base_env: Mapping[str, str] | None = None,
    *,
    allow_extra: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> dict[str, str]:
    """Build a sanitized environment for subprocess execution.

    This function creates an allowlist-based sanitized environment by:
    1. Starting with essential environment variables (platform-aware allowlist)
    2. Adding any explicitly allowed extra variables
    3. Stripping variables matching sensitive patterns (tokens, keys, secrets)
    4. Stripping Python-specific variables (PYTHONPATH, PYTHONHOME, etc.)
    5. Removing platform-specific noisy variables

    Args:
        base_env: Base environment to sanitize. Defaults to os.environ.
        allow_extra: Additional environment variables to allow (name -> value).
            These override base_env values and bypass sensitive pattern checks.
        platform_name: Platform identifier (win32, linux, darwin, …).
            Defaults to sys.platform. Pass an explicit value in tests to verify
            cross-platform behaviour without running on the target OS.

    Returns:
        Sanitized environment dictionary safe for subprocess execution.

    Example:
        >>> env = build_sanitized_subprocess_environment(allow_extra={"MY_VAR": "value"})
        >>> # env contains only essential vars + MY_VAR, no secrets
    """
    source_env = base_env if base_env is not None else os.environ
    essential = _essential_env(platform_name)

    # Start with essential variables from source environment
    sanitized: dict[str, str] = {}
    for key in essential:
        if key in source_env:
            sanitized[key] = source_env[key]

    # Add any explicitly allowed extra variables (these bypass checks)
    if allow_extra:
        sanitized.update(allow_extra)

    # Remove sensitive and Python-specific variables (unless in allow_extra)
    allowed_extra_keys = set(allow_extra.keys()) if allow_extra else set()
    keys_to_remove: list[str] = []

    for key in sanitized:
        if key in allowed_extra_keys:
            # Explicitly allowed variables bypass all checks
            continue
        if _is_sensitive_key(key) or _is_python_key(key):
            keys_to_remove.append(key)

    for key in keys_to_remove:
        sanitized.pop(key, None)

    # Also strip noisy platform-specific variables
    strip_noisy_environment_variables(sanitized, platform_name=platform_name)

    return sanitized
