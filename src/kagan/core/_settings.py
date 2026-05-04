"""Settings key-value store with transparent Fernet encryption for sensitive keys."""

import functools
import os
import stat
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import select

from kagan.core._db_helpers import _db_async
from kagan.core.models import Setting

# Keys whose values are stored encrypted at rest.
# Pattern: any key ending with _token, _key, or _secret.
_SENSITIVE_SUFFIXES: tuple[str, ...] = ("_token", "_key", "_secret")
_FERNET_PREFIX = "fernet:"


def _is_sensitive_key(key: str) -> bool:
    return any(key.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)


def _secret_key_path() -> Path:
    """Return the path to the Fernet secret key file.

    Respects XDG_DATA_HOME; falls back to ~/.local/share/kagan/.
    """
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "kagan" / "secret.key"


def _load_or_create_fernet_key() -> bytes:
    """Return an existing Fernet key or generate and persist a new one.

    The key file is created with mode 0600 so only the owning user can read it.
    """
    from cryptography.fernet import Fernet

    path = _secret_key_path()
    if path.exists():
        return path.read_bytes().strip()

    key = Fernet.generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return key


def _encrypt_value(plaintext: str) -> str:
    """Encrypt *plaintext* and return a ``fernet:``-prefixed ciphertext string."""
    from cryptography.fernet import Fernet

    key = _load_or_create_fernet_key()
    return _FERNET_PREFIX + Fernet(key).encrypt(plaintext.encode()).decode()


def _decrypt_value(ciphertext: str) -> str:
    """Decrypt a ``fernet:``-prefixed ciphertext; return the original plaintext."""
    from cryptography.fernet import Fernet, InvalidToken
    from loguru import logger

    token = ciphertext[len(_FERNET_PREFIX):]
    try:
        key = _load_or_create_fernet_key()
        return Fernet(key).decrypt(token.encode()).decode()
    except (InvalidToken, Exception) as exc:
        logger.warning("Failed to decrypt settings value — returning ciphertext raw: {}", exc)
        return ciphertext


def _maybe_encrypt(key: str, value: str) -> str:
    """Encrypt *value* if *key* is sensitive and the value isn't already encrypted."""
    if not _is_sensitive_key(key):
        return value
    if value.startswith(_FERNET_PREFIX):
        return value  # already encrypted
    return _encrypt_value(value)


def _maybe_decrypt(key: str, value: str) -> str:
    """Decrypt *value* if *key* is sensitive and the value is encrypted."""
    if not _is_sensitive_key(key):
        return value
    if value.startswith(_FERNET_PREFIX):
        return _decrypt_value(value)
    return value  # plaintext / legacy — return as-is


# ── Module-level functions (canonical API) ─────────────────────────


async def get_settings(engine: Engine) -> dict[str, str]:
    def op(s):
        rows = s.exec(select(Setting)).all()
        return {row.key: row.value for row in rows}

    raw = await _db_async(engine, op)
    return {k: _maybe_decrypt(k, v) for k, v in raw.items()}


async def set_settings(engine: Engine, updates: Mapping[str, str]) -> None:
    data = {k: _maybe_encrypt(k, v) for k, v in updates.items()}

    def op(s):
        for key, value in data.items():
            existing = s.get(Setting, key)
            if existing:
                existing.value = value
                s.add(existing)
            else:
                s.add(Setting(key=key, value=value))

    await _db_async(engine, op, commit=True)


# ── Typed namespace (replaces SimpleNamespace + Any return) ────────────────────────


@dataclass(slots=True)
class _SettingsNs:
    """Typed delegate for ``KaganCore.settings``.

    Fields are bound callables so the call site ``await client.settings.get()``
    and ``await client.settings.set({...})`` remain unchanged.
    """

    get: Callable[[], Awaitable[dict[str, str]]]
    set: Callable[[Mapping[str, str]], Awaitable[None]]


def _make_settings_ns(engine: Engine) -> _SettingsNs:
    """Build a typed settings delegate bound to *engine*."""
    return _SettingsNs(
        get=functools.partial(get_settings, engine),
        set=functools.partial(set_settings, engine),
    )


__all__ = ["get_settings", "set_settings"]
