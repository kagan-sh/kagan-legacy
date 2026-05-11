"""Flow D — Streaming Output + Typewriter (CLI surface).

Assertions:
(1) 3 chunks scheduled via script file
(2) all 3 chunk texts appear in transcript
(3) normalised final transcript snapshot matches expected chunks
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

_CHUNKS = ("alpha", "bravo", "charlie")


def test_streaming_chunks(chat_workdir: Path, chat_home: Path, tmp_path: Path) -> None:
    cues = [FakeCue(emit={"type": "chunk", "text": c}, wait=0.05) for c in _CHUNKS] + [
        FakeCue(done=True, wait=0.05)
    ]
    script_file = _write_cues(tmp_path / "script.json", cues)

    pty = spawn_chat(home=chat_home, workdir=chat_workdir, script_file=script_file)
    try:
        pty.read_until_prompt_ready(timeout=15)

        mark = pty.send_line("stream this")

        # (2) wait for last chunk
        pty.read_until_contains(_CHUNKS[-1], timeout=15, after=mark)

        normed = normalise(pty.normalised_text()[mark:], tmp_root=str(tmp_path))

        # (1)+(2) all chunks present
        for chunk in _CHUNKS:
            assert chunk in normed

        # (3) chunks concatenate in order
        assert "alphabravocharlie" in normed.replace("\n", "").replace(" ", "")

        pty.send_key("ctrl_d")
        assert pty.wait(timeout=10) == 0
    finally:
        pty.close()
