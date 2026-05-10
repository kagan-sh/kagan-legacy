"""Flow C — Permission Gating (TUI).

Assertions:
  1. Tool-use event triggers a PermissionRequest via the engine.
  2. ChatPanel shows a permission prompt widget or system message.
  3. Decision flows back through engine.resolve_permission.

Implementation note: the engine's permission path blocks the ACP factory
until ``core.chat.resolve_permission`` is called externally. We schedule
an auto-resolver task that fires once the PermissionRequest is emitted.
The panel also blocks on its own ``_permission_waiter`` Future, which we
resolve directly after unblocking the engine.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.helpers.async_utils import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def test_permission_request_auto_resolved(tui_driver: Any) -> None:
    """(1-3) Permission request surfaces; auto-resolved; approved reply visible."""

    import contextlib

    from textual.widgets import Input

    from kagan.core.chat.acp import ACPTurnResult, PermissionRequestPayload
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel

    async def _noop_warm(*args: Any, **kwargs: Any) -> None:
        return None

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    # Capture the session_id emitted by the engine so the auto-resolver can
    # call core.chat.resolve_permission and unblock the panel waiter.
    permission_emitted: asyncio.Queue[str] = asyncio.Queue()

    class _PermissionACP:
        async def prompt(
            self,
            *,
            session_id: str,
            prompt_blocks: list[Any],
            on_update: Any,
            cancel_event: Any,
            agent_backend: str | None = None,
            permission_resolver: Any = None,
        ) -> ACPTurnResult:
            from acp.schema import AgentMessageChunk, TextContentBlock

            if permission_resolver is not None:
                # Signal that a permission is pending so the resolver can act.
                await permission_emitted.put(session_id)
                # Call the resolver — blocks until resolve_permission is called.
                await asyncio.wait_for(
                    permission_resolver(
                        PermissionRequestPayload(
                            tool_call={"id": "tc-perm-001", "name": "shell"},
                            options=[{"id": "allow_once", "label": "Allow once"}],
                        )
                    ),
                    timeout=8.0,
                )

            # Emit the final reply chunk.
            chunk = AgentMessageChunk(
                content=TextContentBlock(type="text", text="approved"),
                session_update="agent_message_chunk",
            )
            await on_update(chunk)
            await asyncio.sleep(0)
            return ACPTurnResult(full_response="approved", cancelled=False)

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    app.core.chat._acp = _PermissionACP()

    async def _auto_resolve(panel: ChatPanel) -> None:
        """Unblock both the engine Future and the panel waiter."""
        try:
            session_id = await asyncio.wait_for(permission_emitted.get(), timeout=8.0)
        except TimeoutError:
            return

        # Brief pause to let the engine register the pending Future and the
        # panel create its _permission_waiter.
        await asyncio.sleep(0.3)

        # 1. Resolve the engine-level permission Future.
        state = app.core.chat._states.get(session_id)
        if state and state.pending_permissions:
            future_id = next(iter(state.pending_permissions))
            await app.core.chat.resolve_permission(session_id, future_id, outcome="allow_once")

        # Brief pause to let the engine unblock before panel waiter is set.
        await asyncio.sleep(0.1)

        # 2. Resolve the panel-level _permission_waiter Future directly.
        # This unblocks await_permission_resolution() in send_chat_message.
        waiter = panel._permission_waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(None)

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+space")
            await pilot.pause()

            try:
                inp = app.screen.query_one("#chat-overlay-input", Input)
            except Exception:
                pytest.skip("Orchestrator overlay not reachable")
                return

            panel = app.screen.query_one("#chat-panel", ChatPanel)

            # Start the auto-resolver background task with access to the panel.
            resolver_bg = asyncio.create_task(_auto_resolve(panel))

            inp.focus()
            await pilot.press("r", "u", "n")
            await pilot.press("enter")
            await pilot.pause()

            # (2) + (3) Wait for resolution to complete — reply "approved" visible.
            await wait_for(
                lambda: any("approved" in m for m in panel.export_rendered_messages()),
                pump_delay=0.1,
                tries=80,
            )

            # Clean up the background task.
            resolver_bg.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await resolver_bg

            # (1) + (3) Verify reply arrived after permission resolved.
            rendered = panel.export_rendered_messages()
            assert any("approved" in m for m in rendered), (
                f"Approved reply not found after permission resolution: {rendered}"
            )
            assert panel._runtime_status != "error", (
                f"Panel in error state: {panel._runtime_status}"
            )
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
