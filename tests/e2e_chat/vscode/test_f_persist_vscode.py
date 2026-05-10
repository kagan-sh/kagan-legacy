"""Flow F — Session Persistence + Restore (VSCode surface).

Creates an orchestrator session, resets the extension state (simulating a
reload), then fetches the sessions list and asserts the prior session is still
present.  This tests the ``KaganClient.getSessions()`` path that
``getOrCreateSession`` uses on re-entry.

NOTE — participant invocation limitation: see test_a_cold_start_vscode.py.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.e2e_chat,
    pytest.mark.skipif(
        os.environ.get("KAGAN_VSCODE_E2E") != "1",
        reason="VSCode e2e tests require KAGAN_VSCODE_E2E=1",
    ),
]


def test_persist_vscode_session_survives_extension_reset(vscode_runner):  # type: ignore[no-untyped-def]
    """Flow F: create a session, reset state, list sessions, assert prior
    session still appears in the sessions list returned by the server."""
    result = vscode_runner.run(test_filter="flow-f-persist")

    output = result["output"]
    assert result["failed"] == 0, (
        f"vscode-test reported {result['failed']} failure(s).\n\nOutput:\n{output}"
    )
    assert result["passed"] > 0, (
        f"No tests passed — check build or test-filter.\n\nOutput:\n{output}"
    )
