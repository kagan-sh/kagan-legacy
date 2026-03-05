from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

from rich.markup import escape

from kagan.chat.agents import (
    format_agent_usage,
    resolve_agent_command_argument,
)
from kagan.chat.prompt import (
    format_session_payload,
    normalize_chat_input,
)


@dataclass(frozen=True, slots=True)
class SlashCommandSpec:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class SlashCommandInvocation:
    name: str
    arg: str


def parse_slash_invocation(text: str) -> SlashCommandInvocation | None:
    stripped = normalize_chat_input(text)
    if not stripped.startswith("/"):
        return None
    parts = stripped[1:].split(None, 1)
    name = parts[0].lower() if parts else ""
    argument = parts[1].strip() if len(parts) > 1 else ""
    return SlashCommandInvocation(name=name, arg=argument)


def format_unknown_slash_command(name: str) -> str:
    return f"Unknown command: /{name}  (type /help for list)"


@dataclass(frozen=True, slots=True)
class SlashCommandOutcome:
    handled: bool
    close_requested: bool = False
    clear_requested: bool = False
    new_session_requested: bool = False
    selected_agent: str | None = None
    sessions_requested: bool = False
    sessions_query: str | None = None
    delete_session_query: str | None = None
    agent_picker_requested: bool = False
    help_overlay_requested: bool = False
    info_lines: tuple[str, ...] = ()
    error_lines: tuple[str, ...] = ()
    tool_requested: bool = False
    tool_query: str | None = None


@dataclass(frozen=True, slots=True)
class SlashPresentationLine:
    tone: Literal["info", "error"]
    text: str


@dataclass(frozen=True, slots=True)
class _SlashCommandContext:
    session_label: str
    session_key: str
    runtime_session_id: str | None
    current_backend: str | None
    available_backends: list[str] | None


SlashCommandHandler = Callable[[SlashCommandInvocation, _SlashCommandContext], SlashCommandOutcome]


@dataclass(frozen=True, slots=True)
class SlashCommand:
    spec: SlashCommandSpec
    handler: SlashCommandHandler


class SlashCommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        handler: SlashCommandHandler,
    ) -> None:
        key = name.strip().lower()
        if not key:
            raise ValueError("Slash command name must be non-empty")
        if key in self._commands:
            raise ValueError(f"Slash command already registered: {key}")
        self._commands[key] = SlashCommand(
            spec=SlashCommandSpec(name=key, description=description),
            handler=handler,
        )

    def get(self, name: str) -> SlashCommand | None:
        return self._commands.get(name.strip().lower())

    def specs(self) -> tuple[SlashCommandSpec, ...]:
        return tuple(self._commands[name].spec for name in sorted(self._commands))

    def format_help_lines(self) -> list[str]:
        lines = ["Available commands:"]
        for spec in self.specs():
            lines.append(f"  /{spec.name}  {escape(spec.description)}")
        quick_refs = " ".join(f"/{spec.name}" for spec in self.specs())
        lines.append(f"Quick refs: {quick_refs}".strip())
        return lines


def _handle_help(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(handled=True, help_overlay_requested=True)


def _handle_exit(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(handled=True, close_requested=True)


def _handle_clear(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(handled=True, clear_requested=True)


def _handle_new(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(handled=True, new_session_requested=True)


def _handle_session(
    _invocation: SlashCommandInvocation, ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    descriptor, runtime = format_session_payload(
        session_label=ctx.session_label,
        session_key=ctx.session_key,
        runtime_session_id=ctx.runtime_session_id,
    )
    return SlashCommandOutcome(handled=True, info_lines=(descriptor, runtime))


def _handle_sessions(
    invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    normalized_query = invocation.arg.strip() or None
    # /sessions delete <id|number>
    if normalized_query and normalized_query.startswith("delete"):
        delete_arg = normalized_query[len("delete") :].strip() or None
        if not delete_arg:
            return SlashCommandOutcome(
                handled=True,
                error_lines=("Usage: /sessions delete <number|id>",),
            )
        return SlashCommandOutcome(handled=True, delete_session_query=delete_arg)
    return SlashCommandOutcome(
        handled=True,
        sessions_requested=True,
        sessions_query=normalized_query,
    )


def _handle_agents(
    invocation: SlashCommandInvocation, ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    if ctx.available_backends is None:
        return SlashCommandOutcome(handled=True, error_lines=(format_agent_usage(),))

    show_list, selected, error = resolve_agent_command_argument(
        invocation.arg, ctx.available_backends
    )
    if show_list:
        return SlashCommandOutcome(handled=True, agent_picker_requested=True)
    if error is not None:
        return SlashCommandOutcome(handled=True, error_lines=(error,))
    if selected is None:
        return SlashCommandOutcome(handled=True, error_lines=(format_agent_usage(),))
    return SlashCommandOutcome(handled=True, selected_agent=selected)


def _handle_tool(
    invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    query = invocation.arg.strip() or None
    return SlashCommandOutcome(handled=True, tool_requested=True, tool_query=query)


def _handle_flow(
    invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    goal = invocation.arg.strip()
    lines: list[str] = [
        "Structured flow: Plan -> Execute -> Orchestrate",
        "PLAN: State the outcome, constraints, and acceptance criteria in 1-3 bullets.",
        "EXECUTE: Implement one small step at a time and verify each step.",
        "ORCHESTRATE: Summarize what changed, what was verified, and the next action.",
    ]
    if goal:
        lines.insert(1, f"Goal: {goal}")
    lines.append("Tip: Start your next message with 'Plan for: <goal>' to begin explicitly.")
    return SlashCommandOutcome(handled=True, info_lines=tuple(lines))


def _build_slash_command_registry() -> SlashCommandRegistry:
    registry = SlashCommandRegistry()
    registry.register(
        name="help",
        description="Show available slash commands",
        handler=_handle_help,
    )
    registry.register(
        name="exit",
        description="Exit the chat session",
        handler=_handle_exit,
    )
    registry.register(
        name="clear",
        description="Clear the current chat view",
        handler=_handle_clear,
    )
    registry.register(
        name="new",
        description="Start a new chat session",
        handler=_handle_new,
    )
    registry.register(
        name="session",
        description="Show current session details",
        handler=_handle_session,
    )
    registry.register(
        name="sessions",
        description="List, create, or attach chat sessions",
        handler=_handle_sessions,
    )
    registry.register(
        name="agents",
        description="Switch agent backend: /agents [list|<name>]",
        handler=_handle_agents,
    )
    registry.register(
        name="tool",
        description="Inspect tool calls: /tool [id]",
        handler=_handle_tool,
    )
    registry.register(
        name="flow",
        description="Show guided Plan -> Execute -> Orchestrate flow",
        handler=_handle_flow,
    )
    return registry


SLASH_COMMAND_REGISTRY: Final[SlashCommandRegistry] = _build_slash_command_registry()


def resolve_slash_command(
    *,
    name: str,
    arg: str,
    session_label: str,
    session_key: str,
    runtime_session_id: str | None,
    current_backend: str | None,
    available_backends: list[str] | None,
) -> SlashCommandOutcome:
    invocation = SlashCommandInvocation(name=name.strip().lower(), arg=arg)
    command = SLASH_COMMAND_REGISTRY.get(invocation.name)
    if command is None:
        return SlashCommandOutcome(
            handled=True, error_lines=(format_unknown_slash_command(invocation.name),)
        )

    ctx = _SlashCommandContext(
        session_label=session_label,
        session_key=session_key,
        runtime_session_id=runtime_session_id,
        current_backend=current_backend,
        available_backends=available_backends,
    )
    return command.handler(invocation, ctx)


def resolve_slash_input(
    text: str,
    *,
    session_label: str,
    session_key: str,
    runtime_session_id: str | None,
    current_backend: str | None,
    available_backends: list[str] | None,
) -> SlashCommandOutcome:
    parsed = parse_slash_invocation(text)
    if parsed is None:
        return SlashCommandOutcome(handled=False)
    if parsed.name == "":
        return resolve_slash_command(
            name="help",
            arg="",
            session_label=session_label,
            session_key=session_key,
            runtime_session_id=runtime_session_id,
            current_backend=current_backend,
            available_backends=available_backends,
        )
    name, arg = parsed.name, parsed.arg
    return resolve_slash_command(
        name=name,
        arg=arg,
        session_label=session_label,
        session_key=session_key,
        runtime_session_id=runtime_session_id,
        current_backend=current_backend,
        available_backends=available_backends,
    )


def build_slash_presentation_lines(
    result: SlashCommandOutcome,
) -> tuple[SlashPresentationLine, ...]:
    lines: list[SlashPresentationLine] = [
        SlashPresentationLine(tone="info", text=text) for text in result.info_lines
    ]
    lines.extend(SlashPresentationLine(tone="error", text=text) for text in result.error_lines)
    return tuple(lines)
