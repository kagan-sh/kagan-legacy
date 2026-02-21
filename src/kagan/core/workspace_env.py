"""Workspace runtime environment helpers.

This module computes optional cache-related environment overrides that help
multiple worktrees share heavy build/runtime artifacts safely.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from kagan.core.paths import get_cache_dir

if TYPE_CHECKING:
    from collections.abc import Mapping

_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def workspace_env_overrides(
    worktree_path: Path,
    *,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return shared-cache env overrides for a workspace path.

    Overrides are intentionally conservative:
    - `CARGO_TARGET_DIR` when `Cargo.toml` exists
    - `UV_PROJECT_ENVIRONMENT` when `uv.lock` exists

    Existing values in `base_env` are always respected and never overwritten.
    """
    env = base_env if base_env is not None else os.environ
    if not _shared_cache_enabled(env):
        return {}

    project_root = _resolve_project_root(worktree_path)
    cache_root = _resolve_cache_root(env)
    repo_key = _repo_key(project_root)

    overrides: dict[str, str] = {}
    if "CARGO_TARGET_DIR" not in env and (project_root / "Cargo.toml").exists():
        overrides["CARGO_TARGET_DIR"] = str(cache_root / "cargo-target" / repo_key)

    uv_lock = project_root / "uv.lock"
    if "UV_PROJECT_ENVIRONMENT" not in env and uv_lock.exists():
        lock_hash = _file_hash_prefix(uv_lock)
        py_tag = f"py{sys.version_info.major}.{sys.version_info.minor}"
        overrides["UV_PROJECT_ENVIRONMENT"] = str(
            cache_root / "uv-envs" / repo_key / f"{lock_hash}-{py_tag}"
        )

    return overrides


def _shared_cache_enabled(env: Mapping[str, str]) -> bool:
    raw = str(env.get("KAGAN_SHARED_WORKSPACE_CACHE", "")).strip().lower()
    if not raw:
        return True
    return raw not in _FALSE_VALUES


def _resolve_cache_root(env: Mapping[str, str]) -> Path:
    override = str(env.get("KAGAN_SHARED_WORKSPACE_CACHE_ROOT", "")).strip()
    if override:
        try:
            return Path(override).expanduser().resolve(strict=False)
        except OSError:
            return Path(override).expanduser()
    return get_cache_dir() / "workspace-cache"


def _resolve_project_root(worktree_path: Path) -> Path:
    candidate = worktree_path if worktree_path.is_dir() else worktree_path.parent
    try:
        resolved = candidate.expanduser().resolve(strict=False)
    except OSError:
        resolved = candidate
    for current in (resolved, *resolved.parents):
        if (current / ".git").exists():
            return current
    return resolved


def _repo_key(project_root: Path) -> str:
    slug = _slugify(project_root.name) or "repo"
    source = _repo_identity_source(project_root)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def _repo_identity_source(project_root: Path) -> str:
    git_meta = project_root / ".git"
    if git_meta.is_dir():
        return str(git_meta.resolve(strict=False))
    if git_meta.is_file():
        common_git_dir = _common_git_dir(project_root, git_meta)
        if common_git_dir is not None:
            return str(common_git_dir)
    return str(project_root.resolve(strict=False))


def _common_git_dir(project_root: Path, git_file: Path) -> Path | None:
    try:
        content = git_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None
    raw_git_dir = content.split(":", 1)[1].strip()
    git_dir = Path(raw_git_dir)
    if not git_dir.is_absolute():
        git_dir = (project_root / git_dir).resolve(strict=False)
    else:
        git_dir = git_dir.resolve(strict=False)

    # In linked worktrees: <repo>/.git/worktrees/<worktree-id>
    if git_dir.parent.name == "worktrees":
        return git_dir.parent.parent.resolve(strict=False)
    return git_dir


def _file_hash_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
        return digest.hexdigest()[:12]
    except OSError:
        return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-")
