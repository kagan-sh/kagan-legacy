"""Flow A — Cold Start (VSCode surface).

Drives the ``KaganClient`` HTTP path that the @kagan chat participant uses
internally.  The vscode-test subprocess boots an Extension Development Host,
activates the extension, then creates an orchestrator chat session via the
live ``kagan web --fake-agent`` server and asserts an assistant chunk appears.

NOTE — vscode.chat.sendRequest() limitation (2026-05-08):
  @types/vscode@1.115.0 does not expose ``vscode.chat.sendRequest()``.
  The participant's request handler cannot be invoked programmatically from
  inside @vscode/test-electron.  This test therefore drives the *KaganClient*
  HTTP tier directly (the same path the participant calls), and verifies the
  session lifecycle visible to the extension.  See:
  https://github.com/microsoft/vscode/issues/199908
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


def test_cold_start_vscode_creates_session_and_receives_chunk(vscode_runner):  # type: ignore[no-untyped-def]
    """Flow A: extension activates, creates an orchestrator session via HTTP,
    sends a user message, and receives at least one CHAT_CHUNK frame."""
    result = vscode_runner.run(test_filter="flow-a-cold-start")

    output = result["output"]
    assert result["failed"] == 0, (
        f"vscode-test reported {result['failed']} failure(s).\n\nOutput:\n{output}"
    )
    assert result["passed"] > 0, (
        f"No tests passed — check build or test-filter.\n\nOutput:\n{output}"
    )
