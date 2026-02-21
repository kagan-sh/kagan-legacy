"""Explicit runtime context for DB/config/runtime path selection."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kagan.core.paths import (
    get_config_path,
    get_core_runtime_dir,
    get_data_dir,
    get_database_path,
)
from kagan.core.test_isolation import (
    enforce_test_db_path,
    enforce_test_runtime_dir,
    strict_test_isolation_enabled,
)

RUNTIME_CONTEXT_ENV = "KAGAN_RUNTIME_CONTEXT_JSON"
RUNTIME_MODE_ENV = "KAGAN_RUNTIME_MODE"


class RuntimeMode(StrEnum):
    """Execution mode for runtime invariants."""

    PROD = "prod"
    DEV = "dev"
    TEST = "test"


@dataclass(frozen=True, slots=True)
class CoreRuntimeContext:
    """Resolved runtime context used by all process/runtime boundaries."""

    context_id: str
    mode: RuntimeMode
    config_path: Path
    db_path: Path
    runtime_dir: Path

    def to_payload(self) -> dict[str, str]:
        """Serialize as a JSON-safe payload."""
        return {
            "context_id": self.context_id,
            "mode": self.mode.value,
            "config_path": str(self.config_path),
            "db_path": str(self.db_path),
            "runtime_dir": str(self.runtime_dir),
        }

    def to_json(self) -> str:
        """Serialize this context to a JSON string."""
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoreRuntimeContext:
        """Deserialize from a payload previously produced by :meth:`to_payload`."""
        context_id = str(payload.get("context_id", "")).strip()
        if not context_id:
            raise ValueError("Runtime context payload is missing context_id")
        mode = RuntimeMode(str(payload.get("mode", RuntimeMode.DEV.value)).strip().lower())
        config_path = _resolve_path(payload.get("config_path"))
        db_path = _resolve_path(payload.get("db_path"))
        runtime_dir = _resolve_path(payload.get("runtime_dir"))
        return cls(
            context_id=context_id,
            mode=mode,
            config_path=config_path,
            db_path=db_path,
            runtime_dir=runtime_dir,
        )

    @classmethod
    def from_json(cls, data: str) -> CoreRuntimeContext:
        """Deserialize from JSON."""
        loaded = json.loads(data)
        if not isinstance(loaded, dict):
            raise ValueError("Runtime context JSON must decode to an object")
        return cls.from_payload(loaded)


def _resolve_path(value: object) -> Path:
    if isinstance(value, Path):
        raw = value
    elif isinstance(value, str):
        raw = Path(value)
    else:
        raise ValueError(f"Expected path-like value, got {type(value).__name__}")
    return raw.expanduser().resolve(strict=False)


def _resolve_executable() -> Path:
    try:
        return Path(sys.executable).expanduser().resolve(strict=False)
    except OSError:
        return Path(sys.executable)


def _runtime_suffix(config_path: Path, db_path: Path) -> str:
    key = f"{config_path}\n{db_path}\n{_resolve_executable()}".encode()
    return hashlib.sha256(key).hexdigest()[:16]


def _derive_runtime_dir(config_path: Path, db_path: Path) -> Path:
    override = os.environ.get("KAGAN_CORE_RUNTIME_DIR")
    if override:
        return _resolve_path(override)

    default_config = get_config_path().expanduser().resolve(strict=False)
    default_db = get_database_path().expanduser().resolve(strict=False)
    if config_path == default_config and db_path == default_db:
        return get_core_runtime_dir().expanduser().resolve(strict=False)

    suffix = _runtime_suffix(config_path, db_path)
    if os.name == "nt":
        return (get_data_dir() / "core" / "scoped" / suffix).expanduser().resolve(strict=False)
    return (Path("/tmp") / "kagan-core" / suffix).expanduser().resolve(strict=False)


def _derive_context_id(config_path: Path, db_path: Path, runtime_dir: Path) -> str:
    key = f"{config_path}\n{db_path}\n{runtime_dir}\n{_resolve_executable()}".encode()
    return hashlib.sha256(key).hexdigest()[:20]


def _temp_roots() -> tuple[Path, ...]:
    roots: list[Path] = [Path(tempfile.gettempdir()).expanduser().resolve(strict=False)]
    if os.name != "nt":
        roots.append(Path("/tmp").expanduser().resolve(strict=False))
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def _is_temp_path(path: Path) -> bool:
    return any(path.is_relative_to(root) for root in _temp_roots())


def _coerce_mode(value: str | RuntimeMode | None) -> RuntimeMode | None:
    if value is None:
        return None
    if isinstance(value, RuntimeMode):
        return value
    raw = value.strip().lower()
    if not raw:
        return None
    return RuntimeMode(raw)


def _infer_mode(config_path: Path, db_path: Path, explicit_mode: RuntimeMode | None) -> RuntimeMode:
    if explicit_mode is not None:
        return explicit_mode

    env_mode = _coerce_mode(os.environ.get(RUNTIME_MODE_ENV))
    if env_mode is not None:
        return env_mode

    if strict_test_isolation_enabled():
        return RuntimeMode.TEST

    default_config = get_config_path().expanduser().resolve(strict=False)
    default_db = get_database_path().expanduser().resolve(strict=False)
    if config_path == default_config and db_path == default_db:
        return RuntimeMode.PROD

    return RuntimeMode.DEV


def validate_runtime_context(context: CoreRuntimeContext) -> None:
    """Validate mode/path invariants for a runtime context."""
    if context.mode is RuntimeMode.TEST:
        enforce_test_db_path(context.db_path, context="runtime_context")
        enforce_test_runtime_dir(context.runtime_dir, context="runtime_context")
        return

    if context.mode is RuntimeMode.PROD:
        if _is_temp_path(context.db_path):
            raise RuntimeError(
                f"PROD runtime context DB path must not be under temp roots: {context.db_path}"
            )
        if _is_temp_path(context.runtime_dir):
            raise RuntimeError(
                "PROD runtime context runtime_dir must not be under temp roots: "
                f"{context.runtime_dir}"
            )


def create_runtime_context(
    *,
    config_path: str | Path | None = None,
    db_path: str | Path | None = None,
    runtime_dir: str | Path | None = None,
    mode: str | RuntimeMode | None = None,
    context_id: str | None = None,
) -> CoreRuntimeContext:
    """Build a runtime context from explicit values and deterministic defaults."""
    resolved_config = _resolve_path(config_path) if config_path is not None else get_config_path()
    resolved_db = _resolve_path(db_path) if db_path is not None else get_database_path()
    resolved_runtime = (
        _resolve_path(runtime_dir)
        if runtime_dir is not None
        else _derive_runtime_dir(resolved_config, resolved_db)
    )
    resolved_mode = _infer_mode(resolved_config, resolved_db, _coerce_mode(mode))
    resolved_context_id = (context_id or "").strip() or _derive_context_id(
        resolved_config, resolved_db, resolved_runtime
    )
    context = CoreRuntimeContext(
        context_id=resolved_context_id,
        mode=resolved_mode,
        config_path=resolved_config,
        db_path=resolved_db,
        runtime_dir=resolved_runtime,
    )
    validate_runtime_context(context)
    return context


def resolve_runtime_context(
    *,
    config_path: str | Path | None = None,
    db_path: str | Path | None = None,
    runtime_dir: str | Path | None = None,
    mode: str | RuntimeMode | None = None,
    context_id: str | None = None,
) -> CoreRuntimeContext:
    """Resolve runtime context from explicit inputs or process environment."""
    has_explicit = any(
        value is not None for value in (config_path, db_path, runtime_dir, mode, context_id)
    )
    raw = os.environ.get(RUNTIME_CONTEXT_ENV, "")
    if raw and not has_explicit:
        context = CoreRuntimeContext.from_json(raw)
        validate_runtime_context(context)
        return context
    return create_runtime_context(
        config_path=config_path,
        db_path=db_path,
        runtime_dir=runtime_dir,
        mode=mode,
        context_id=context_id,
    )


def runtime_context_env(context: CoreRuntimeContext) -> dict[str, str]:
    """Return environment variables that propagate the runtime context."""
    return {
        RUNTIME_CONTEXT_ENV: context.to_json(),
        RUNTIME_MODE_ENV: context.mode.value,
        "KAGAN_CORE_RUNTIME_DIR": str(context.runtime_dir),
    }


__all__ = [
    "RUNTIME_CONTEXT_ENV",
    "RUNTIME_MODE_ENV",
    "CoreRuntimeContext",
    "RuntimeMode",
    "create_runtime_context",
    "resolve_runtime_context",
    "runtime_context_env",
    "validate_runtime_context",
]
