"""Strict test-sandbox guards for DB and core runtime paths."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

STRICT_TEST_ISOLATION_ENV = "KAGAN_STRICT_TEST_ISOLATION"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def strict_test_isolation_enabled() -> bool:
    """Return whether strict test sandbox checks are enabled."""
    raw_value = os.environ.get(STRICT_TEST_ISOLATION_ENV, "")
    return raw_value.strip().lower() in _TRUE_VALUES


def _resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _test_temp_root() -> Path:
    return Path(tempfile.gettempdir()).expanduser().resolve(strict=False)


def _temp_roots() -> tuple[Path, ...]:
    roots: list[Path] = [_test_temp_root()]
    if os.name != "nt":
        roots.append(Path("/tmp").expanduser().resolve(strict=False))

    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def _is_within_temp_roots(path: Path) -> bool:
    return any(path.is_relative_to(root) for root in _temp_roots())


def enforce_test_sandbox_path(
    path: str | Path,
    *,
    subject: str,
    context: str | None = None,
) -> None:
    """Fail fast when strict test mode points at non-temporary storage."""
    if not strict_test_isolation_enabled():
        return

    resolved_path = _resolve_path(path)
    if _is_within_temp_roots(resolved_path):
        return

    location = f" ({context})" if context else ""
    allowed_roots = ", ".join(str(root) for root in _temp_roots())
    raise RuntimeError(
        f"{subject} path escaped strict test sandbox: {resolved_path}{location}. "
        f"Expected a path under one of: {allowed_roots}."
    )


def enforce_test_db_path(path: str | Path, *, context: str | None = None) -> None:
    """Validate DB path safety when strict test isolation is active."""
    if str(path) == ":memory:":
        return
    enforce_test_sandbox_path(path, subject="Database", context=context)


def enforce_test_runtime_dir(path: str | Path, *, context: str | None = None) -> None:
    """Validate core runtime directory safety in strict test mode."""
    enforce_test_sandbox_path(path, subject="Core runtime directory", context=context)


__all__ = [
    "STRICT_TEST_ISOLATION_ENV",
    "enforce_test_db_path",
    "enforce_test_runtime_dir",
    "enforce_test_sandbox_path",
    "strict_test_isolation_enabled",
]
