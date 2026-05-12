"""Flow B — Multiturn + Queue Drain (CLI surface).

Note: Per-turn director scheduling across process boundaries is not possible
(see conftest.py decision doc).  This test asserts that:

1. First prompt gets a reply.
2. A second prompt after the reply completes also gets a reply.

Both turns use the same default script (same cue list repeated).  The "↓ 1
queued" toolbar indicator is not directly testable over PTY because it
requires a second send *while* streaming — this would require precise timing
that is unreliable across CI environments.  The test focuses on the drain
property: both turns eventually produce output.

Assertions:
(1) send first prompt, wait for reply
(2) send second prompt, wait for second reply
(3) both replies visible in transcript
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.e2e_chat.cli.conftest import _write_cues
from tests.e2e_chat.helpers.pty import spawn_chat
from tests.helpers.fake_agent_backend import FakeCue

pytestmark = [
    pytest.mark.e2e_chat,
    pytest.mark.skipif(sys.platform == "win32", reason="pty not available on Windows"),
]


def test_multiturn_drain(chat_workdir: Path, chat_home: Path, tmp_path: Path) -> None:
    # Script covers one turn; the factory re-reads the same script each call.
    cues = [
        FakeCue(emit={"type": "chunk", "text": "turn reply\n"}, wait=0.05),
        FakeCue(done=True, wait=0.05),
    ]
    script_file = _write_cues(tmp_path / "script.json", cues)

    pty = spawn_chat(home=chat_home, workdir=chat_workdir, script_file=script_file)
    try:
        pty.read_until_prompt_ready(timeout=15)

        # (1) first turn
        m1 = pty.send_line("first")
        pty.read_until_contains("turn reply", timeout=15, after=m1)

        # Drain trailing output so the second prompt isn't fighting the first
        # turn's tail rendering.  PROMPT_READY ("Agent ready.") only prints
        # once at startup; re-prompts are signalled by the message counter
        # bumping ("1 msg").
        pty.read_until_contains("1 msg", timeout=15, after=m1)

        # (2) second turn
        m3 = pty.send_line("second")
        pty.read_until_contains("turn reply", timeout=15, after=m3)

        # (3) both replies in full transcript
        full = pty.normalised_text()
        assert full.count("turn reply") >= 2

        pty.send_key("ctrl_d")
        assert pty.wait(timeout=90) == 0
    finally:
        pty.close()
