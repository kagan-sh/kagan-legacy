"""PermissionUI — engine-driven permission flow for the CLI REPL.

Phase 5c: ``handle_request`` consumes a :class:`PermissionRequest` event
emitted by :class:`kagan.core.chat.ChatEngine` and dispatches the user's
decision via ``engine.resolve_permission(session_id, future_id, outcome=...,
feedback=...)``. The class no longer returns ACP responses — translation
back to ACP is handled inside :class:`kagan.cli.chat.acp._CaptureACPClient`.

Constructed once per controller. The same instance handles every permission
event for the lifetime of the chat session; the underlying batch queue
shares state across requests (debounce, session-allow cache).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as _rich_escape

if TYPE_CHECKING:
    from kagan.cli.chat._renderer import CLIRenderer
    from kagan.core.chat.events import PermissionRequest


class PermissionUI:
    """Owns the modal + cache + batch queue for one chat session.

    ``yolo`` short-circuits to ``allow_once`` before the batch queue is armed.
    ``renderer`` is held so the queue can finalize the streaming Markdown
    region before opening a modal. ``engine`` is the :class:`ChatEngine`
    receiving every decision — supplied lazily via :meth:`bind_engine` so
    construction order in the controller stays simple.
    """

    def __init__(
        self,
        *,
        yolo: bool = False,
        renderer: CLIRenderer | None = None,
        engine: Any = None,
    ) -> None:
        from kagan.cli.chat._approval_batch import _BatchApprovalQueue

        self._yolo = yolo
        self._renderer = renderer
        self._engine = engine
        self._batch_queue = _BatchApprovalQueue(engine)

    def bind_engine(self, engine: Any) -> None:
        """(Re)bind the engine reference and rebuild the batch queue.

        Called when the controller switches sessions / restarts the factory
        but keeps the same ``PermissionUI`` instance.
        """
        from kagan.cli.chat._approval_batch import _BatchApprovalQueue

        self._engine = engine
        self._batch_queue = _BatchApprovalQueue(engine)

    # ------------------------------------------------------------------
    # Hooks consumed by ``_BatchApprovalQueue`` for terminal printing.
    # ------------------------------------------------------------------

    def _print_via_terminal(self, fn: Any) -> None:
        from kagan.cli.chat._renderer import print_via_terminal

        print_via_terminal(fn)

    # ------------------------------------------------------------------
    # Entry point — called by the controller for each PermissionRequest event
    # ------------------------------------------------------------------

    async def handle_request(
        self,
        event: PermissionRequest,
        session_id: str,
    ) -> None:
        """Handle one engine permission event.

        Resolves the decision via :meth:`ChatEngine.resolve_permission`. The
        coroutine returns once the decision has been *dispatched* — fast for
        non-interactive / yolo paths; for interactive paths it returns once
        the modal flow finishes and the engine has been notified.
        """
        from kagan.cli.chat import _chat_acp as chat_acp_module

        if self._engine is None:
            raise RuntimeError("PermissionUI.handle_request called before bind_engine")

        # Engine emits ``options`` as plain dicts; preserve dict shape so the
        # batch queue / single-approval helpers can render titles uniformly.
        permission_options = [
            opt
            for opt in (event.options or ())
            if (opt.get("kind") if isinstance(opt, dict) else getattr(opt, "kind", None))
            in {"allow_once", "allow_always", "reject_once", "reject_always"}
        ]
        if not permission_options:
            await self._engine.resolve_permission(session_id, event.future_id, outcome="deny")
            return

        if self._renderer is not None:
            self._renderer.finalize_pending_markdown()

        if self._yolo:
            title = chat_acp_module._format_permission_tool(event.tool_call)

            def _print_yolo(_t: str = title) -> None:
                chat_acp_module._console.print(
                    f"  [red]● yolo auto-approve:[/red] [dim]{_rich_escape(_t)}[/dim]",
                    highlight=False,
                )

            self._print_via_terminal(_print_yolo)
            await self._engine.resolve_permission(session_id, event.future_id, outcome="allow_once")
            return

        if not chat_acp_module._stdio_is_interactive():

            def _print_denied() -> None:
                chat_acp_module._console.print(
                    "[yellow]Permission request denied in non-interactive mode.[/yellow]"
                )

            self._print_via_terminal(_print_denied)
            await self._engine.resolve_permission(session_id, event.future_id, outcome="deny")
            return

        future = await self._batch_queue.enqueue(
            permission_options,
            event.tool_call,
            future_id=event.future_id,
            session_id=session_id,
        )
        # Wait for the queue to dispatch — the queue calls
        # ``engine.resolve_permission`` itself before resolving this future.
        await future

    def reset_batch_queue(self) -> None:
        """Clear queue state at turn start."""
        self._batch_queue.reset()

    def cancel_batch_queue(self) -> None:
        """Cancel all pending batch approval futures (SIGINT)."""
        self._batch_queue.cancel_all()


__all__ = ["PermissionUI"]
