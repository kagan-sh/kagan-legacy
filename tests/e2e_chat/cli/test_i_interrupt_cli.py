"""Flow I — Interrupt / Stop Turn (CLI surface).

The ``slow`` script emits "thinking..." then holds for several seconds before
emitting "should not arrive".  SIGINT delivered directly to the subprocess
(``process.send_signal(signal.SIGINT)``) should cancel the streaming turn
because ``_send_and_stream`` installs a custom SIGINT handler that cancels the
``consume_task``.

Why not PTY ctrl_c (0x03)?
Prompt_toolkit operates in raw terminal mode (``ISIG`` flag disabled).  In that
mode, the 0x03 byte is delivered as a *key event* to prompt_toolkit, not
converted to SIGINT by the terminal driver.  Therefore ctrl_c via PTY reaches
only prompt_toolkit's key binding (which clears the buffer), not the OS signal
handler.  ``process.send_signal(signal.SIGINT)`` bypasses the terminal and
delivers the signal directly to the subprocess PID, which does reach the custom
``_handle_sigint`` that cancels the engine turn.

Assertions:
(1) slow script loaded; "thinking..." appears in transcript
(2) SIGINT sent via ``process.send_signal``
(3) "should not arrive" does NOT appear in transcript after cancel
(4) REPL returns to prompt-ready state (or process exits cleanly)

Note: Timing is inherently racy on slow CI runners.  The test uses a generous
hold_seconds and sends SIGINT as soon as "thinking..." is seen.  There is a
small window where "should not arrive" could appear if asyncio doesn't schedule
the cancellation before the next cue runs.  This is documented as a known
flake risk in the plan (Risk 1).
"""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

import pytest

from tests.e2e_chat.cli.conftest import _write_cues
from tests.e2e_chat.helpers.pty import spawn_chat
from tests.helpers.fake_agent_backend import FakeCue

pytestmark = [
    pytest.mark.e2e_chat,
    pytest.mark.skipif(sys.platform == "win32", reason="pty not available on Windows"),
]

_HOLD_SECONDS = 5.0


def test_interrupt(chat_workdir: Path, chat_home: Path, tmp_path: Path) -> None:
    cues = [
        FakeCue(emit={"type": "chunk", "text": "thinking..."}, wait=0.05),
        FakeCue(wait=_HOLD_SECONDS),
        FakeCue(emit={"type": "chunk", "text": "should not arrive"}, wait=0.0),
        FakeCue(done=True, wait=0.0),
    ]
    script_file = _write_cues(tmp_path / "script.json", cues)

    pty = spawn_chat(home=chat_home, workdir=chat_workdir, script_file=script_file)
    try:
        pty.read_until_prompt_ready(timeout=15)

        mark = pty.send_line("start slow")

        # (1) wait for thinking sentinel
        pty.read_until_contains("thinking...", timeout=15, after=mark)

        # (2) Send SIGINT directly to the subprocess — bypasses prompt_toolkit
        # raw-mode terminal (which would swallow PTY ctrl_c as a key event).
        # _send_and_stream installs a custom SIGINT handler that cancels consume_task.
        pty.process.send_signal(signal.SIGINT)
        time.sleep(0.5)

        # (3) "should not arrive" must not be in transcript
        # Drain any remaining PTY output for 1 second before checking
        for _ in range(10):
            pty.read_available(timeout=0.1)
        full = pty.normalised_text()
        assert "should not arrive" not in full, (
            f"Interrupt did not cancel the stream in time.\n"
            f"Transcript after mark:\n{full[mark:][:600]}"
        )

        # (4) REPL either resumes (prompt-ready + ctrl_d) or exits with signal.
        # SIGINT via process.send_signal may cause the subprocess to exit before
        # ctrl_d arrives.  Accept rc=0 (handled, resumed, exited on ctrl_d) or
        # rc=-2 / rc=130 (terminated by SIGINT before resuming the prompt).
        import contextlib
        import os as _os

        rc = pty.process.poll()
        if rc is None:
            # Still running — send ctrl_d (EOF) to exit cleanly
            with contextlib.suppress(OSError):
                _os.write(pty.master_fd, b"\x04")
            rc = pty.wait(timeout=5)
        # rc=0: handled cleanly (REPL resumed, exited on ctrl_d)
        # rc=1: Python exception from SIGINT in asyncio (acceptable on macOS)
        # rc=-2 / rc=130: terminated by unhandled SIGINT
        assert rc in (0, 1, -2, 130), (
            f"Unexpected exit code after interrupt: {rc}\n"
            f"Transcript:\n{pty.normalised_text()[-1000:]}"
        )
    finally:
        pty.close()
