import os
import sys
from collections.abc import Mapping, MutableMapping

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
    key = (platform_name or sys.platform).lower()
    return _NOISY_ENV_KEYS_BY_PLATFORM.get(key, ())


def strip_noisy_environment_variables(
    env: MutableMapping[str, str],
    *,
    platform_name: str | None = None,
) -> tuple[str, ...]:
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
    return strip_noisy_environment_variables(os.environ)


def build_sanitized_subprocess_environment(
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    strip_noisy_environment_variables(env)
    return env
