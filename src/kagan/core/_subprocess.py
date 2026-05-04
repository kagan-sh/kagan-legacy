"""Platform-aware command resolution for asyncio.create_subprocess_exec.

On Windows, ``asyncio.create_subprocess_exec`` calls ``CreateProcess`` directly,
which neither honours ``PATHEXT`` nor executes ``.cmd`` / ``.bat`` files.
Node-based CLI tools (claude, codex, gemini, copilot, ...) and IDE launchers
(code.cmd, cursor.cmd) install as ``.cmd`` shims, so bare-name invocations
fail with ``FileNotFoundError`` and full ``.cmd`` paths fail with
``WinError 193`` (not a valid Win32 application).

``resolve_spawn_command`` wraps the executable in the appropriate interpreter
so every spawn site works correctly on Windows while being a no-op on POSIX.
"""

import shutil
import sys
from pathlib import Path

__all__ = ["resolve_spawn_command"]


def resolve_spawn_command(executable: str, *args: str) -> list[str]:
    """Resolve a command for ``asyncio.create_subprocess_exec`` on any platform.

    On POSIX returns ``[executable, *args]`` (or ``[resolved, *args]`` if
    ``shutil.which`` finds an alternative path — functionally equivalent).

    On Windows:

    - Resolves via ``shutil.which()`` so ``PATHEXT`` is honoured (finds
      ``.cmd`` / ``.bat`` / ``.ps1`` / ``.exe`` shims).
    - If the resolved path ends in ``.cmd`` or ``.bat`` returns
      ``["cmd.exe", "/c", resolved, *args]``.
    - If the resolved path ends in ``.ps1`` returns
      ``["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
      resolved, *args]``.
    - Otherwise (``.exe`` or a bare path that is a PE binary) returns
      ``[resolved, *args]``.
    - If ``shutil.which()`` returns ``None`` falls back to
      ``[executable, *args]`` so the caller still sees ``FileNotFoundError``
      with the original name in the error message.

    Absolute paths skip ``which`` and have their suffix inspected directly.
    Suffix matching is case-insensitive so ``.CMD`` and ``.cmd`` both work.
    """
    if sys.platform != "win32":
        resolved = shutil.which(executable)
        result_exe = resolved if resolved is not None else executable
        return [result_exe, *args]

    # --- Windows path ---

    # If the caller passed an absolute or root-relative path, skip which() and
    # inspect suffix. On Windows/Python 3.13, pathlib no longer treats
    # "\foo" or "/foo" as absolute because they lack a drive, but those are
    # still explicit paths rather than command names.
    if Path(executable).is_absolute() or executable.startswith(("/", "\\")):
        return _wrap_windows(executable, args)

    resolved = shutil.which(executable)
    if resolved is None:
        # Fall back so FileNotFoundError names the original executable.
        return [executable, *args]

    return _wrap_windows(resolved, args)


def _wrap_windows(resolved: str, args: tuple[str, ...]) -> list[str]:
    """Wrap *resolved* in the correct Windows interpreter based on its suffix."""
    suffix = Path(resolved).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return ["cmd.exe", "/c", resolved, *args]
    if suffix == ".ps1":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            resolved,
            *args,
        ]
    return [resolved, *args]
