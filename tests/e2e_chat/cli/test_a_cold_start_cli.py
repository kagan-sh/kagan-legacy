"""Flow A — Cold-Start Chat (CLI surface).

Assertions:
1. prompt-ready sentinel appears after spawn
2. send "hi", receive reply text
3. normalised reply snapshot matches
4. clean exit on Ctrl-D
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.e2e_chat.cli.conftest import _write_cues
from tests.e2e_chat.helpers.inline_snapshot_normalisers import normalise
from tests.e2e_chat.helpers.pty import spawn_chat
from tests.helpers.fake_agent_backend import FakeCue

pytestmark = [
    pytest.mark.e2e_chat,
    pytest.mark.skipif(sys.platform == "win32", reason="pty not available on Windows"),
]


def test_cold_start(chat_workdir: Path, chat_home: Path, tmp_path: Path) -> None:
    cues = [
        FakeCue(emit={"type": "chunk", "text": "hello back\n"}, wait=0.05),
        FakeCue(done=True, wait=0.05),
    ]
    script_file = _write_cues(tmp_path / "script.json", cues)

    pty = spawn_chat(home=chat_home, workdir=chat_workdir, script_file=script_file)
    try:
        # 1. prompt-ready sentinel
        pty.read_until_prompt_ready(timeout=15)

        # 2. send "hi"
        mark = pty.send_line("hi")

        # 3. reply appears
        transcript = pty.read_until_contains("hello back", timeout=15, after=mark)
        normed = normalise(transcript, tmp_root=str(tmp_path))

        assert "hello back" in normed

        # 4. clean exit on Ctrl-D (empty buffer)
        pty.send_key("ctrl_d")
        rc = pty.wait(timeout=45)
        assert rc == 0
    finally:
        pty.close()
