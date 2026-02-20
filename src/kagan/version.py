"""Shared package version helpers."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_RUNTIME_HASH_SOURCE_FILES: tuple[str, ...] = (
    "version.py",
    "core/ipc/contracts.py",
    "core/host.py",
    "sdk/_transport.py",
    "mcp/server.py",
    "tui/app.py",
)


@lru_cache(maxsize=1)
def get_kagan_version() -> str:
    """Return installed kagan version, or 'dev' when package metadata is unavailable."""
    try:
        return version("kagan")
    except PackageNotFoundError:
        return "dev"


@lru_cache(maxsize=1)
def get_kagan_runtime_hash() -> str:
    """Return a deterministic runtime fingerprint for client/core compatibility checks."""
    digest = hashlib.sha256()
    digest.update(get_kagan_version().encode("utf-8"))

    package_root = Path(__file__).resolve().parent
    for relative_path in _RUNTIME_HASH_SOURCE_FILES:
        digest.update(relative_path.encode("utf-8"))
        source_path = package_root / relative_path
        try:
            source_bytes = source_path.read_bytes()
        except OSError:
            digest.update(b"<missing>")
            continue
        digest.update(hashlib.sha256(source_bytes).digest())

    # Short but collision-resistant enough for runtime compatibility checks.
    return digest.hexdigest()[:16]


__all__ = ["get_kagan_runtime_hash", "get_kagan_version"]
