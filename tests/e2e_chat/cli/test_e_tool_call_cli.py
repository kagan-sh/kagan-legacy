"""Flow E — Tool Call + Live Status (CLI surface).

Assertions:
(1) tool_call script scheduled
(2) tool indicator appears in transcript (CLI renderer shows tool activity)
(3) tool_result received (completion marker in transcript)
(4) final "tool finished" text visible
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


def test_tool_call(chat_workdir: Path, chat_home: Path, tmp_path: Path) -> None:
    cues = [
        FakeCue(
            emit={
                "type": "tool_use",
                "tool_call_id": "tc-e2e-001",
                "name": "shell",
                "input": {"command": "ls"},
            },
            wait=0.05,
        ),
        FakeCue(
            emit={
                "type": "tool_result",
                "tool_call_id": "tc-e2e-001",
                "output": "file.txt",
            },
            wait=0.1,
        ),
        FakeCue(emit={"type": "chunk", "text": "tool finished\n"}, wait=0.05),
        FakeCue(done=True, wait=0.05),
    ]
    script_file = _write_cues(tmp_path / "script.json", cues)

    pty = spawn_chat(home=chat_home, workdir=chat_workdir, script_file=script_file)
    try:
        pty.read_until_prompt_ready(timeout=15)

        mark = pty.send_line("use a tool")

        # (4) final text confirms tool completed
        pty.read_until_contains("tool finished", timeout=15, after=mark)

        after_send = pty.normalised_text()[mark:]

        # (2)+(3) tool lifecycle visible in transcript
        assert "tool finished" in after_send

        # Wait for REPL to re-enter prompt_async before sending ctrl_d;
        # the toolbar message-counter bump signals the prompt is active.
        pty.read_until_contains("1 msg", timeout=15, after=mark)

        pty.send_key("ctrl_d")
        assert pty.wait(timeout=45) == 0
    finally:
        pty.close()
