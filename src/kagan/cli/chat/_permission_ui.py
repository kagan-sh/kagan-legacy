"""PermissionUI — wraps the permission flow as instance state.

Phase 5b lifts the permission side of ``_OrchestratorACPClient`` here. The
legacy ACP client now constructs ``PermissionUI`` per session and forwards
``request_permission`` calls through ``handle_request``. Phase 5c will rewire
the controller to consume ``ChatEngine.resolve_permission`` via this class.

The single-approval modal (``_run_interactive_modal``, ``_run_legacy_input``,
``_run_approval_panel_async``), result mapping (``_map_approval_result``),
helpers (``_session_approvals``, ``_cancelled_permission_response``, …) and
the batch queue (``_BatchApprovalQueue``) all continue to live where they
were so that monkey-patched test references through ``_chat_acp`` keep
resolving. ``PermissionUI`` simply orchestrates the existing pieces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as _rich_escape

if TYPE_CHECKING:
    from kagan.cli.chat._renderer import CLIRenderer


class PermissionUI:
    """Owns the modal + cache + batch queue for one chat session.

    Construction defaults match the previous ``_OrchestratorACPClient`` init:
    ``yolo`` short-circuits to allow_once before the batch queue is armed,
    ``renderer`` is held so the batch queue can finalize Markdown and route
    prints through the same modal-aware terminal helper.
    """

    def __init__(self, *, yolo: bool = False, renderer: CLIRenderer | None = None) -> None:
        from kagan.cli.chat._approval_batch import _BatchApprovalQueue

        self._yolo = yolo
        self._renderer = renderer
        self._batch_queue = _BatchApprovalQueue(self)

    # ------------------------------------------------------------------
    # Hooks consumed by ``_BatchApprovalQueue`` — preserves the previous
    # ``_OrchestratorACPClient`` interface so the queue keeps working
    # unchanged. The queue reaches into ``self._md_region.finalize`` and
    # ``self._print_via_terminal`` on its owner.
    # ------------------------------------------------------------------

    @property
    def _md_region(self) -> Any:
        if self._renderer is None:
            return None
        return self._renderer._md_region

    def _print_via_terminal(self, fn: Any) -> None:
        from kagan.cli.chat._renderer import print_via_terminal

        print_via_terminal(fn)

    # ------------------------------------------------------------------
    # Entry point — called by ``_OrchestratorACPClient.request_permission``
    # ------------------------------------------------------------------

    async def handle_request(
        self,
        options: Any,
        session_id: str,
        tool_call: Any,
        *,
        engine: Any = None,
    ) -> Any:
        """Handle one permission request and return the ACP response.

        ``engine`` is unused in 5b; phase 5c will route the decision through
        ``engine.resolve_permission`` instead of returning the ACP object.
        """
        del session_id, engine
        # Imported lazily so monkey-patches against ``chat_acp_module`` win.
        from kagan.cli.chat import _chat_acp as chat_acp_module

        permission_options = [
            option
            for option in list(options or ())
            if getattr(option, "kind", None)
            in {"allow_once", "allow_always", "reject_once", "reject_always"}
        ]
        if not permission_options:
            return chat_acp_module._cancelled_permission_response()

        if self._renderer is not None:
            self._renderer.finalize_pending_markdown()

        # --yolo: short-circuit before the batch queue is armed.
        if self._yolo:
            for option in permission_options:
                if getattr(option, "kind", None) == "allow_once":
                    title = chat_acp_module._format_permission_tool(tool_call)

                    def _print_yolo(_t: str = title) -> None:
                        chat_acp_module._console.print(
                            f"  [red]● yolo auto-approve:[/red] [dim]{_rich_escape(_t)}[/dim]",
                            highlight=False,
                        )

                    self._print_via_terminal(_print_yolo)
                    return chat_acp_module._selected_permission_response(option)

        if not chat_acp_module._stdio_is_interactive():

            def _print_denied() -> None:
                chat_acp_module._console.print(
                    "[yellow]Permission request denied in non-interactive mode.[/yellow]"
                )

            self._print_via_terminal(_print_denied)
            return chat_acp_module._cancelled_permission_response()

        future = await self._batch_queue.enqueue(permission_options, tool_call)
        return await future

    def reset_batch_queue(self) -> None:
        """Clear queue state at turn start."""
        self._batch_queue.reset()

    def cancel_batch_queue(self) -> None:
        """Cancel all pending batch approval futures (called from SIGINT handler)."""
        self._batch_queue.cancel_all()


__all__ = ["PermissionUI"]
