"""Shared ACP stream message routing for Textual screens/modals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.acp import messages
from kagan.acp.messages import Answer
from kagan.ui.utils.agent_exit import is_graceful_agent_termination

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kagan.ui.widgets.streaming_output import StreamingOutput

type UpdateHandler = Callable[[messages.AgentUpdate], Awaitable[None]]
type ThinkingHandler = Callable[[messages.Thinking], Awaitable[None]]
type ToolCallHandler = Callable[[messages.ToolCall], Awaitable[None]]
type ToolCallUpdateHandler = Callable[[messages.ToolCallUpdate], Awaitable[None]]
type ReadyHandler = Callable[[messages.AgentReady], Awaitable[None]]
type FailHandler = Callable[[messages.AgentFail], Awaitable[None]]
type CompleteHandler = Callable[[messages.AgentComplete], Awaitable[None]]
type PlanHandler = Callable[[messages.Plan], Awaitable[None]]
type PermissionHandler = Callable[[messages.RequestPermission], Awaitable[None]]
type SetModesHandler = Callable[[messages.SetModes], None]
type ModeUpdateHandler = Callable[[messages.ModeUpdate], None]
type CommandsUpdateHandler = Callable[[messages.AvailableCommandsUpdate], None]
type IgnoreFailHandler = Callable[[messages.AgentFail], bool]


class AgentStreamRouter:
    """Route ACP messages with optional per-screen overrides and defaults."""

    def __init__(
        self,
        *,
        get_output: Callable[[], StreamingOutput],
        show_output: Callable[[], None] | None = None,
        on_update: UpdateHandler | None = None,
        on_thinking: ThinkingHandler | None = None,
        on_tool_call: ToolCallHandler | None = None,
        on_tool_call_update: ToolCallUpdateHandler | None = None,
        on_ready: ReadyHandler | None = None,
        on_fail: FailHandler | None = None,
        on_complete: CompleteHandler | None = None,
        on_plan: PlanHandler | None = None,
        on_request_permission: PermissionHandler | None = None,
        on_set_modes: SetModesHandler | None = None,
        on_mode_update: ModeUpdateHandler | None = None,
        on_commands_update: CommandsUpdateHandler | None = None,
        ignore_fail: IgnoreFailHandler | None = None,
    ) -> None:
        self._get_output = get_output
        self._show_output = show_output
        self._on_update = on_update
        self._on_thinking = on_thinking
        self._on_tool_call = on_tool_call
        self._on_tool_call_update = on_tool_call_update
        self._on_ready = on_ready
        self._on_fail = on_fail
        self._on_complete = on_complete
        self._on_plan = on_plan
        self._on_request_permission = on_request_permission
        self._on_set_modes = on_set_modes
        self._on_mode_update = on_mode_update
        self._on_commands_update = on_commands_update
        self._ignore_fail = ignore_fail

    async def dispatch(self, message: messages.AgentMessage) -> None:
        """Dispatch a single ACP message."""
        match message:
            case messages.AgentUpdate():
                self._show()
                if self._on_update is not None:
                    await self._on_update(message)
                    return
                await self._get_output().post_response(message.text)
            case messages.Thinking():
                self._show()
                if self._on_thinking is not None:
                    await self._on_thinking(message)
                    return
                await self._get_output().post_thought(message.text)
            case messages.ToolCall():
                self._show()
                if self._on_tool_call is not None:
                    await self._on_tool_call(message)
                    return
                await self._get_output().upsert_tool_call(message.tool_call)
            case messages.ToolCallUpdate():
                self._show()
                if self._on_tool_call_update is not None:
                    await self._on_tool_call_update(message)
                    return
                await self._get_output().apply_tool_call_update(message.update, message.tool_call)
            case messages.AgentReady():
                self._show()
                if self._on_ready is not None:
                    await self._on_ready(message)
                    return
                await self._get_output().post_note("Agent ready", classes="success")
            case messages.AgentFail():
                if self._ignore_fail is not None and self._ignore_fail(message):
                    return
                self._show()
                if self._on_fail is not None:
                    await self._on_fail(message)
                    return
                await self._default_fail(message)
            case messages.AgentComplete():
                if self._on_complete is not None:
                    await self._on_complete(message)
            case messages.Plan():
                self._show()
                if self._on_plan is not None:
                    await self._on_plan(message)
                    return
                await self._get_output().post_plan(message.entries)
            case messages.SetModes():
                if self._on_set_modes is not None:
                    self._on_set_modes(message)
            case messages.ModeUpdate():
                if self._on_mode_update is not None:
                    self._on_mode_update(message)
            case messages.AvailableCommandsUpdate():
                if self._on_commands_update is not None:
                    self._on_commands_update(message)
            case messages.RequestPermission():
                if self._on_request_permission is not None:
                    await self._on_request_permission(message)
                    return
                self._resolve_permission(message)

    async def _default_fail(self, message: messages.AgentFail) -> None:
        output = self._get_output()
        if is_graceful_agent_termination(message.message):
            await output.post_note(
                "Agent stream ended by cancellation (SIGTERM).",
                classes="dismissed",
            )
            return

        await output.post_note(f"Error: {message.message}", classes="error")
        if message.details:
            await output.post_note(message.details)

    def _show(self) -> None:
        if self._show_output is not None:
            self._show_output()

    def _resolve_permission(self, message: messages.RequestPermission) -> None:
        option_id = self._find_option(message, "allow_once")
        if option_id is None:
            option_id = self._find_option_contains(message, "allow")
        if option_id is None and message.options:
            option_id = message.options[0].option_id
        if option_id is None:
            return
        if not message.result_future.done():
            message.result_future.set_result(Answer(option_id))

    @staticmethod
    def _find_option(message: messages.RequestPermission, kind: str) -> str | None:
        for option in message.options:
            if option.kind == kind:
                return option.option_id
        return None

    @staticmethod
    def _find_option_contains(message: messages.RequestPermission, text: str) -> str | None:
        for option in message.options:
            if text in option.kind:
                return option.option_id
        return None
