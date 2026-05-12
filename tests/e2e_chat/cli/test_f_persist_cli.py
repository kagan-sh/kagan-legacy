"""Flow F — Session Persistence + Restore (CLI surface).

Assertions:
(1) send msg, get reply, Ctrl-D exits cleanly
(2) re-spawn with ``--session-id <id>`` loads the same session
(3) prior message and reply are present in restored transcript

Session id is read from the SQLite DB after the first turn — it is not
rendered into the REPL banner so PTY scraping is unreliable.
"""

from __future__ import annotations

import sqlite3
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


def _latest_chat_session_id(workdir: Path) -> str | None:
    """Return the most recent chat-session id from the workdir's SQLite DB."""
    candidates = list(workdir.rglob("kagan.db"))
    if not candidates:
        return None
    db = max(candidates, key=lambda p: p.stat().st_mtime)
    with sqlite3.connect(str(db)) as conn:
        cur = conn.execute("SELECT id FROM chat_sessions ORDER BY updated_at DESC LIMIT 1")
        row = cur.fetchone()
    return row[0] if row else None


def test_session_persist_and_restore(chat_workdir: Path, chat_home: Path, tmp_path: Path) -> None:
    cues = [
        FakeCue(emit={"type": "chunk", "text": "persist reply\n"}, wait=0.05),
        FakeCue(done=True, wait=0.05),
    ]
    script_file = _write_cues(tmp_path / "script.json", cues)

    # --- First session ---
    pty1 = spawn_chat(home=chat_home, workdir=chat_workdir, script_file=script_file)
    try:
        pty1.read_until_prompt_ready(timeout=15)

        mark = pty1.send_line("remember this")
        pty1.read_until_contains("persist reply", timeout=15, after=mark)
        # Wait until the REPL counter / prompt_async is idle again; Ctrl-D during
        # composing can be ignored and caused ubuntu+3.14 main CI to hang at exit.
        pty1.read_until_contains("1 msg", timeout=20, after=mark)

        pty1.send_key("ctrl_d")
        assert pty1.wait(timeout=120) == 0
    finally:
        pty1.close()

    session_id = _latest_chat_session_id(chat_workdir)
    assert session_id is not None, "No chat_session row written by first run"

    # --- Restore session ---
    pty2 = spawn_chat(
        home=chat_home,
        workdir=chat_workdir,
        script_file=script_file,
        args=["--session-id", session_id],
    )
    try:
        # Wait for the restore banner, then for replayed turn text (may arrive in a
        # later PTY chunk than the "Resumed transcript:" header on some platforms).
        # Anchor `after=` at the character after the banner text — not `pty2.mark()`
        # (buffer end), which can land past the whole replay when one `read()` returns
        # everything on fast machines (Greptile).
        buf_with_banner = pty2.read_until_contains("Resumed transcript", timeout=20)
        _banner = "Resumed transcript"
        mark_after_banner = buf_with_banner.index(_banner) + len(_banner)
        pty2.read_until_contains("persist reply", timeout=20, after=mark_after_banner)
        full = pty2.normalised_text()
        assert "remember this" in full, f"Restored transcript missing user line:\n{full[-2000:]}"
        pty2.read_until_contains("Type a request", timeout=20, after=mark_after_banner)

        pty2.send_key("ctrl_d")
        assert pty2.wait(timeout=120) == 0
    finally:
        pty2.close()
