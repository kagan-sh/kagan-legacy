"""Flow I — Interrupt / Stop Turn (VSCode surface).

Schedules the ``slow`` fake-agent scenario, starts a chat stream, fires
``KaganClient.interruptChatTurn()``, and asserts that no late chunks appear
after the interrupt and that the turn-status endpoint reflects termination.

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


def test_interrupt_vscode_stops_turn_before_late_chunk(vscode_runner):  # type: ignore[no-untyped-def]
    """Flow I: schedule slow scenario, begin streaming, interrupt mid-stream,
    assert no 'should not arrive' chunk is received and status shows idle."""
    result = vscode_runner.run(test_filter="flow-i-interrupt")

    output = result["output"]
    assert result["failed"] == 0, (
        f"vscode-test reported {result['failed']} failure(s).\n\nOutput:\n{output}"
    )
    assert result["passed"] > 0, (
        f"No tests passed — check build or test-filter.\n\nOutput:\n{output}"
    )
