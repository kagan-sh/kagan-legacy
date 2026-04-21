"""Environment-level preflight checks for kagan doctor.

Each function is a pure callable that inspects the runtime environment and
returns a result dict with the same keys as DoctorCheck (name, status,
message, fix_hint, verify_hint, category="environment"). They intentionally
do not import DoctorCheck — that dataclass lives in cli/doctor.py so the
check functions stay import-cycle-free.

Callers (cli/doctor.py) are responsible for wrapping the returned dict into
a DoctorCheck instance.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class EnvCheckResult(TypedDict):
    name: str
    status: str
    message: str
    fix_hint: str
    verify_hint: str
    category: str


# ---------------------------------------------------------------------------
# Category derivation
# ---------------------------------------------------------------------------

# Names whose checks are classified as core infrastructure
_CORE_CHECK_NAMES: frozenset[str] = frozenset({"git", "tmux", "db"})

# Names whose checks are classified as agent backend
_BACKEND_CHECK_NAMES: frozenset[str] = frozenset({"agent backend"})

# Names whose checks are classified as environment
_ENVIRONMENT_CHECK_NAMES: frozenset[str] = frozenset(
    {"ide", "terminal multiplexer", "project config", "startup env"}
)


def _derive_category(name: str) -> str:
    """Derive the category string for a check given its display name."""
    if name in _CORE_CHECK_NAMES:
        return "core"
    if name in _BACKEND_CHECK_NAMES:
        return "backend"
    if name in _ENVIRONMENT_CHECK_NAMES:
        return "environment"
    return "plugin"


# ---------------------------------------------------------------------------
# Unified verify-hint mapping
# ---------------------------------------------------------------------------

_VERIFY_HINTS: dict[str, str] = {
    "git": "git --version",
    "tmux": "tmux -V",
    "db": "kagan projects",
    "ide": "echo $TERM_PROGRAM",
    "gh cli": "gh --version",
    "gh auth": "gh auth token",
    "terminal multiplexer": "zellij --version",
    "project config": "test -f pyproject.toml",
    "startup env": "env | grep -i malloc",
}


def verify_hint_for(check_name: str, backend_name: str | None = None) -> str:
    """Return the verify command for a named check.

    For the ``agent backend`` check the hint is backend-specific and must be
    supplied via *backend_name*; falls back to ``ls`` for unknown names.
    """
    if check_name == "agent backend" and backend_name is not None:
        from kagan.core._agent import CLAUDE_CODE_BACKEND, CODEX_BACKEND, get_backend_spec
        from kagan.core.errors import KaganError

        executable = backend_name
        try:
            spec = get_backend_spec(backend_name)
            if spec.executable:
                executable = spec.executable
        except (ImportError, KaganError):
            pass

        which_cmd = "where" if sys.platform == "win32" else "which"
        if backend_name in {CLAUDE_CODE_BACKEND, CODEX_BACKEND}:
            return f"{executable} --version"
        return f"{which_cmd} {executable}"

    return _VERIFY_HINTS.get(check_name, "ls")


# ---------------------------------------------------------------------------
# Individual environment checks
# ---------------------------------------------------------------------------


def check_ide() -> EnvCheckResult:
    """Detect whether a supported IDE is present."""
    if shutil.which("code") or os.environ.get("TERM_PROGRAM"):
        return EnvCheckResult(
            name="ide",
            status="pass",
            message="IDE integration detected",
            fix_hint="",
            verify_hint=_VERIFY_HINTS["ide"],
            category="environment",
        )
    return EnvCheckResult(
        name="ide",
        status="warn",
        message="IDE integration not detected",
        fix_hint="Open this project in a supported editor for richer workflows",
        verify_hint=_VERIFY_HINTS["ide"],
        category="environment",
    )


def _parse_zellij_version() -> tuple[int, ...] | None:
    """Return Zellij's (major, minor, patch) tuple, or None if unavailable."""
    try:
        out = subprocess.run(
            ["zellij", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        match = re.search(r"(\d+\.\d+\.\d+)", out)
        if match:
            return tuple(int(p) for p in match.group(1).split("."))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def check_zellij() -> EnvCheckResult | None:
    """Return a Zellij compatibility check, or None if Zellij is not active."""
    if not os.environ.get("ZELLIJ"):
        return None

    zellij_version = _parse_zellij_version()
    if zellij_version and zellij_version < (0, 42, 0):
        return EnvCheckResult(
            name="terminal multiplexer",
            status="warn",
            message=(
                f"Zellij {'.'.join(map(str, zellij_version))} has known rendering"
                " issues with Textual TUIs"
            ),
            fix_hint="Upgrade Zellij to >= 0.42.0 (fixes synchronized output bug)",
            verify_hint=_VERIFY_HINTS["terminal multiplexer"],
            category="environment",
        )
    return EnvCheckResult(
        name="terminal multiplexer",
        status="pass",
        message="Zellij detected (compatible version)",
        fix_hint="",
        verify_hint=_VERIFY_HINTS["terminal multiplexer"],
        category="environment",
    )


def check_pyproject(cwd: Path | None = None) -> EnvCheckResult:
    """Check whether pyproject.toml exists in the working directory."""
    target = (cwd or Path.cwd()) / "pyproject.toml"
    if target.exists():
        return EnvCheckResult(
            name="project config",
            status="pass",
            message="pyproject.toml found",
            fix_hint="",
            verify_hint=_VERIFY_HINTS["project config"],
            category="environment",
        )
    return EnvCheckResult(
        name="project config",
        status="warn",
        message="pyproject.toml not found in current directory",
        fix_hint="Run this command from your project root",
        verify_hint="pwd",
        category="environment",
    )


def check_noisy_env() -> EnvCheckResult | None:
    """Return a warning if debug allocator env vars are active, else None."""
    from kagan.runtime_env import noisy_env_keys

    noisy_keys = noisy_env_keys()
    active_noisy = [key for key in noisy_keys if os.environ.get(key)]
    if not active_noisy:
        return None
    return EnvCheckResult(
        name="startup env",
        status="warn",
        message="Debug allocator environment variables are set: " + ", ".join(active_noisy),
        fix_hint="Unset them before launching kagan: unset " + " ".join(active_noisy),
        verify_hint=_VERIFY_HINTS["startup env"],
        category="environment",
    )


def collect_environment_checks(cwd: Path | None = None) -> list[EnvCheckResult]:
    """Collect all environment checks and return non-None results."""
    results: list[EnvCheckResult] = [check_ide()]

    zellij = check_zellij()
    if zellij is not None:
        results.append(zellij)

    results.append(check_pyproject(cwd))

    noisy = check_noisy_env()
    if noisy is not None:
        results.append(noisy)

    return results


# ---------------------------------------------------------------------------
# Backend-resolution helpers (used by cli/doctor.py)
# ---------------------------------------------------------------------------


def resolve_agent_executable(backend_name: str) -> str:
    """Return the CLI executable for *backend_name*, falling back to the name itself."""
    from kagan.core._agent import get_backend_spec
    from kagan.core.errors import KaganError

    try:
        executable = get_backend_spec(backend_name).executable
        if executable:
            return executable
    except (ImportError, KaganError):
        pass
    return backend_name


def resolve_backend_guidance(backend_name: str) -> str | None:
    """Return a joined guidance string for *backend_name*, or None."""
    from kagan.core._agent import get_backend_spec
    from kagan.core.errors import KaganError

    try:
        guidance = get_backend_spec(backend_name).guidance_hints()
    except (ImportError, KaganError):
        return None
    return " ".join(guidance) if guidance else None


def default_agent_backend_name() -> str:
    """Return the configured default agent backend name from env or defaults."""
    from kagan.core._agent import resolve_default_agent_backend

    return os.environ.get("KAGAN_AGENT_BACKEND", resolve_default_agent_backend({}))


async def resolve_doctor_backend_name(client: object) -> str:
    """Resolve the default agent backend from client settings, falling back to env/defaults."""
    from kagan.core._agent import resolve_default_agent_backend
    from kagan.core.errors import KaganError

    settings_ops = getattr(client, "settings", None)
    get_settings = cast(
        "Callable[[], Awaitable[object]] | None",
        getattr(settings_ops, "get", None),
    )
    if callable(get_settings):
        try:
            settings = await get_settings()
            if isinstance(settings, dict):
                return resolve_default_agent_backend(settings)
        except (KaganError, RuntimeError, OSError, ValueError):
            from loguru import logger

            logger.opt(exception=True).debug(
                "Doctor could not read default agent backend from settings"
            )
    return default_agent_backend_name()
