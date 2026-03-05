import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from loguru import logger
from packaging.version import InvalidVersion, Version
from platformdirs import user_cache_path

from kagan.runtime_env import build_sanitized_subprocess_environment


def make_client(db_path: str | Path | None = None):
    from kagan.core import KaganCore

    logger.debug("Client created")
    return KaganCore(db_path=db_path)


def run_async(coro):
    return asyncio.run(coro)


def _current_version() -> str:
    return version("kagan")


def _cache_file() -> Path:
    cache_dir = user_cache_path("kagan")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "update-check.json"


def _read_cache() -> dict | None:
    path = _cache_file()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(data: dict) -> None:
    try:
        _cache_file().write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write update cache: {}", exc)
        return


def _fetch_pypi_version(timeout_seconds: float = 2.0) -> str | None:
    import urllib.error
    import urllib.request

    url = "https://pypi.org/pypi/kagan/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
            info = data.get("info", {})
            latest = info.get("version")
            if isinstance(latest, str) and latest.strip():
                return latest.strip()
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return None


def _is_newer(latest: str, current: str) -> bool:
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return False


def _refresh_cache(prerelease: bool = False) -> None:
    latest = _fetch_pypi_version()
    if latest is None:
        return
    if not prerelease:
        try:
            if Version(latest).is_prerelease:
                return
        except InvalidVersion:
            return
    _write_cache({"checked_at": int(time.time()), "latest": latest})


def maybe_check_for_updates(skip: bool = False) -> str | None:
    if skip or os.environ.get("KAGAN_SKIP_UPDATE_CHECK") == "1":
        logger.debug("Update check: skipped")
        return None

    try:
        cached = _read_cache()
        logger.debug("Update check: cached={}", cached is not None)
        current = _current_version()
        latest_hint: str | None = None

        if cached is not None:
            latest = cached.get("latest")
            if isinstance(latest, str) and _is_newer(latest, current):
                latest_hint = latest

        thread = threading.Thread(target=_refresh_cache, kwargs={"prerelease": False}, daemon=True)
        thread.start()
        return latest_hint
    except (OSError, RuntimeError, ValueError, PackageNotFoundError):
        return None


def _detect_install_method() -> str:
    methods = ("uv", "pipx")
    return next((m for m in methods if shutil.which(m)), "pip")


def _build_install_command(method: str, prerelease: bool) -> list[str]:
    if method == "uv":
        command = ["uv", "tool", "install", "--upgrade", "kagan"]
        if prerelease:
            command.extend(["--prerelease", "allow"])
        return command
    if method == "pipx":
        if prerelease:
            return ["pipx", "upgrade", "kagan", "--pip-args", "--pre"]
        return ["pipx", "upgrade", "kagan"]
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "kagan"]
    if prerelease:
        cmd.append("--pre")
    return cmd


def check_and_install_update(
    check_only: bool = False,
    prerelease: bool = False,
    force: bool = False,
) -> tuple[bool, str]:
    current = _current_version()
    latest = _fetch_pypi_version(timeout_seconds=6.0)
    if latest is None:
        return False, "Unable to reach PyPI to check for updates."

    if not prerelease:
        try:
            if Version(latest).is_prerelease:
                return (
                    False,
                    "Latest available release is pre-release; pass --prerelease to include it.",
                )
        except InvalidVersion:
            return False, "Latest PyPI version is invalid."

    has_update = _is_newer(latest, current)
    if check_only:
        if has_update:
            return True, f"Update available: {current} -> {latest}"
        return False, f"Already up to date ({current})"

    if not has_update and not force:
        return False, f"Already up to date ({current})"

    method = _detect_install_method()
    command = _build_install_command(method, prerelease)

    logger.info("Installing update via {}", method)
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=build_sanitized_subprocess_environment(),
    )
    if process.returncode != 0:
        output = process.stderr.strip() or process.stdout.strip() or "unknown error"
        logger.error("Update failed: {}", output.splitlines()[0])
        return False, f"Update failed using {method}: {output}"

    _write_cache({"checked_at": int(time.time()), "latest": latest})
    return True, f"Updated via {method}: {current} -> {latest}"
