"""PTY harness for ``kg chat`` REPL e2e tests.

Lifted from ``references/kimi-cli/tests/e2e/shell_pty_helpers.py`` and
adapted: prompt-ready sentinel uses kagan's bottom-toolbar marker
(``tip:``) emitted by ``src/kagan/cli/chat/repl.py:_bottom_toolbar``.

macOS PTY safety: ``setsid()`` + ``TIOCSCTTY`` in preexec, ``EIO`` on
``read_available`` treated as EOF, ``env -i``-style environment built
in :func:`make_chat_env` so the spawned process is hermetic.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_TIMEOUT = 15.0
# PROMPT_READY is the sentinel string that appears in linearised PTY output once
# the REPL's prompt_async is active and accepting input.
#
# The bottom-toolbar ``tip:`` text is rendered by prompt_toolkit via cursor-
# positioning escape sequences and does NOT appear in the linear PTY byte stream
# after ANSI stripping.
#
# ``Press /help`` is emitted by the Rich console as the shortcut hint just
# before the REPL loop calls ``prompt_async``.  It appears in the linear PTY
# output reliably; waiting for it means prompt_async is about to be entered (we
# still allow a brief settling delay in ``read_until_prompt_ready``).
#
# ``> Type a request`` is the prompt_toolkit placeholder text rendered by
# prompt_async when the buffer is empty.  It confirms that prompt_async is
# running and the process can accept input.
PROMPT_READY = "Press /help"

_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OTHER_ESC = re.compile(r"\x1b[@-_]")


def make_chat_env(
    *,
    home: Path,
    workdir: Path,
    fake_agent_delay_ms: int = 100,
    script_file: Path | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Hermetic env for the spawned ``kagan chat`` subprocess.

    ``script_file`` — path to a JSON cue file written by the test.  When
    provided it is passed as ``KAGAN_FAKE_AGENT_SCRIPT_FILE`` so the
    subprocess's fake-agent reads a deterministic script for every turn that
    has no per-session script in its director registry.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "TERM": "xterm-256color",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "KAGAN_FAKE_AGENT": "1",
        "KAGAN_FAKE_AGENT_DELAY_MS": str(fake_agent_delay_ms),
        "KAGAN_DATA_DIR": str(workdir),
        "XDG_DATA_HOME": str(workdir),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "KAGAN_CHAT_SKIP_BOOT_ANIMATION": "1",
        "NO_COLOR": "1",
        # Prevents prompt_toolkit from issuing Cursor-Position-Report (CPR)
        # escape sequences.  Without this the spawned subprocess loops waiting
        # for CPR responses from the PTY, causing the whole REPL to stall.
        "PROMPT_TOOLKIT_NO_CPR": "1",
    }
    if script_file is not None:
        env["KAGAN_FAKE_AGENT_SCRIPT_FILE"] = str(script_file)
    if extra:
        env.update(extra)
    return env


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _OSC.sub("", text)
    text = _CSI.sub("", text)
    text = _OTHER_ESC.sub("", text)
    return text.replace("\x00", "").replace("\x08", "")


def _set_window(fd: int, *, columns: int = 120, lines: int = 40) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", lines, columns, 0, 0))


def _preexec(slave_fd: int) -> Callable[[], None]:
    def run() -> None:
        os.setsid()
        with contextlib.suppress(OSError):
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

    return run


@dataclass
class ChatPTY:
    """Mark-aware PTY wrapper around a running ``kg chat`` process."""

    process: subprocess.Popen[bytes]
    master_fd: int
    _chunks: list[bytes] = field(default_factory=list)

    def raw_text(self) -> str:
        return b"".join(self._chunks).decode("utf-8", errors="replace")

    def normalised_text(self) -> str:
        return _normalise(self.raw_text())

    def mark(self) -> int:
        return len(self.normalised_text())

    def read_available(self, timeout: float = 0.1) -> bytes:
        ready, _, _ = select.select([self.master_fd], [], [], timeout)
        if not ready:
            return b""
        try:
            chunk = os.read(self.master_fd, 4096)
        except OSError as exc:
            if exc.errno == errno.EIO:
                return b""
            raise
        if chunk:
            self._chunks.append(chunk)
        return chunk

    def read_until_contains(
        self, text: str, *, timeout: float = DEFAULT_TIMEOUT, after: int = 0
    ) -> str:
        deadline = time.monotonic() + timeout
        while True:
            buf = self.normalised_text()
            if text in buf[after:]:
                return buf
            if self.process.poll() is not None:
                while self.read_available(timeout=0.01):
                    buf = self.normalised_text()
                    if text in buf[after:]:
                        return buf
                raise AssertionError(
                    f"Process exited before {text!r} appeared.\n"
                    f"Return code: {self.process.returncode}\n"
                    f"Transcript:\n{buf}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"Timed out waiting for {text!r}.\nTranscript:\n{buf}")
            self.read_available(timeout=min(0.2, remaining))

    def read_until_prompt_ready(self, *, timeout: float = DEFAULT_TIMEOUT, after: int = 0) -> str:
        """Wait for the REPL to be ready to accept input.

        First waits for the PROMPT_READY sentinel (``Press /help``), then
        waits for the prompt_toolkit placeholder text which confirms that
        ``prompt_async`` has started and the process accepts keystrokes.
        """
        self.read_until_contains(PROMPT_READY, timeout=timeout, after=after)
        # Wait for prompt_async placeholder which confirms prompt is active.
        # Use a shorter sub-timeout since PROMPT_READY already fired.
        return self.read_until_contains("Type a request", timeout=min(timeout, 8.0), after=after)

    def send(self, text: str) -> None:
        os.write(self.master_fd, text.encode("utf-8"))

    def send_key(self, key: str) -> None:
        keys = {
            "enter": b"\r",
            "escape": b"\x1b",
            "tab": b"\t",
            "ctrl_c": b"\x03",
            "ctrl_d": b"\x04",
            "ctrl_t": b"\x14",
            "up": b"\x1b[A",
            "down": b"\x1b[B",
        }
        payload = keys.get(key)
        if payload is None:
            raise ValueError(f"Unsupported key: {key!r}")
        os.write(self.master_fd, payload)

    def send_line(self, text: str) -> int:
        """Submit ``text`` + Enter; returns the pre-send mark."""
        before = self.mark()
        if text:
            self.send(text)
        self.send_key("enter")
        return before

    def wait(self, timeout: float = DEFAULT_TIMEOUT) -> int:
        deadline = time.monotonic() + timeout
        while True:
            rc = self.process.poll()
            if rc is not None:
                while self.read_available(timeout=0.01):
                    pass
                return rc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    f"Process did not exit within {timeout}s.\n"
                    f"Transcript:\n{self.normalised_text()}"
                )
            self.read_available(timeout=min(0.2, remaining))

    def close(self) -> None:
        with contextlib.suppress(ProcessLookupError, OSError, subprocess.TimeoutExpired):
            self.process.terminate()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    self.process.wait(timeout=2.0)
        with contextlib.suppress(OSError):
            os.close(self.master_fd)


def spawn_chat(
    *,
    home: Path,
    workdir: Path,
    args: list[str] | None = None,
    fake_agent_delay_ms: int = 100,
    script_file: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> ChatPTY:
    """Spawn ``kagan chat --agent fake-agent`` under a PTY.

    ``script_file`` — optional JSON cue file to inject as
    ``KAGAN_FAKE_AGENT_SCRIPT_FILE`` so the subprocess runs a deterministic
    fake-agent script for every turn.
    """
    master_fd, slave_fd = pty.openpty()
    _set_window(slave_fd)
    cmd = [sys.executable, "-m", "kagan", "chat", "--agent", "fake-agent"]
    if args:
        cmd.extend(args)
    env = make_chat_env(
        home=home,
        workdir=workdir,
        fake_agent_delay_ms=fake_agent_delay_ms,
        script_file=script_file,
        extra=extra_env,
    )
    process = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        cwd=workdir,
        preexec_fn=_preexec(slave_fd),
        close_fds=True,
    )
    os.close(slave_fd)
    return ChatPTY(process=process, master_fd=master_fd)


def write_script_file(dest: Path, cues: list[dict[str, object]]) -> Path:
    """Write a JSON cue list to *dest* for ``KAGAN_FAKE_AGENT_SCRIPT_FILE``.

    ``cues`` should be plain dicts (e.g. from ``asdict(FakeCue(...))``).
    Returns *dest* for convenience.
    """
    import json

    dest.write_text(json.dumps(cues), encoding="utf-8")
    return dest


__all__ = ["PROMPT_READY", "ChatPTY", "make_chat_env", "spawn_chat", "write_script_file"]
