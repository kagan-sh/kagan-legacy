from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

from rich.markup import escape

from kagan.chat.agents import (
    format_agent_usage,
    resolve_agent_command_argument,
)
from kagan.chat.prompt import normalize_chat_input


@dataclass(frozen=True, slots=True)
class SlashCommandSpec:
    name: str
    description: str
    orchestrator_only: bool = False


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


class SlashAction(Enum):
    NONE = "none"
    CLOSE = "close"
    CLEAR = "clear"
    NEW_SESSION = "new_session"
    SWITCH_AGENT = "switch_agent"
    LIST_SESSIONS = "list_sessions"
    DELETE_SESSION = "delete_session"
    SHOW_AGENTS = "show_agents"
    SHOW_HELP = "show_help"
    SHOW_TOOL = "show_tool"
    SHOW_STATUS = "show_status"
    SWITCH_PROJECT = "switch_project"
    SHOW_PROJECT = "show_project"
    SHOW_INFO = "show_info"


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
    status_requested: bool = False
    project_switch_requested: str | None = None
    project_info_requested: bool = False
    action: SlashAction = SlashAction.NONE
    data: str | None = None


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
    project_name: str | None
    project_id: str | None
    turn_count: int
    is_orchestrator: bool = True


SlashCommandHandler = Callable[[SlashCommandInvocation, _SlashCommandContext], SlashCommandOutcome]


@dataclass(frozen=True, slots=True)
class SlashCommand:
    spec: SlashCommandSpec
    handler: SlashCommandHandler


class SlashCommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._aliases: dict[str, str] = {}

    def register_alias(self, alias: str, target: str) -> None:
        self._aliases[alias] = target

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

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
        key = name.strip().lower()
        if key not in self._commands:
            key = self._aliases.get(key, key)
        return self._commands.get(key)

    def specs(self, *, orchestrator_only: bool | None = None) -> tuple[SlashCommandSpec, ...]:
        """Return command specs, optionally filtering by orchestrator_only flag.

        Args:
            orchestrator_only: If True, return only orchestrator-only commands.
                If False, return only non-orchestrator commands.
                If None (default), return all commands.
        """
        result = []
        for name in sorted(self._commands):
            spec = self._commands[name].spec
            if orchestrator_only is None or spec.orchestrator_only == orchestrator_only:
                result.append(spec)
        return tuple(result)

    def format_help_lines(self) -> list[str]:
        lines = ["Available commands:"]
        for spec in self.specs():
            lines.append(f"  /{spec.name}  {escape(spec.description)}")
        quick_refs = " ".join(f"/{spec.name}" for spec in self.specs())
        if self._aliases:
            alias_parts = " ".join(
                f"/{alias}→{target}" for alias, target in sorted(self._aliases.items())
            )
            quick_refs += f"  Aliases: {alias_parts}"
        lines.append(f"Quick refs: {quick_refs}".strip())
        return lines


def _handle_help(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(
        handled=True, help_overlay_requested=True, action=SlashAction.SHOW_HELP
    )


def _handle_exit(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(handled=True, close_requested=True, action=SlashAction.CLOSE)


def _handle_clear(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(handled=True, clear_requested=True, action=SlashAction.CLEAR)


def _handle_new(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(
        handled=True, new_session_requested=True, action=SlashAction.NEW_SESSION
    )


def _handle_sessions(
    invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    query = invocation.arg.strip() or None
    return SlashCommandOutcome(
        handled=True,
        sessions_requested=True,
        sessions_query=query,
        action=SlashAction.LIST_SESSIONS,
        data=query,
    )


def _handle_status(
    _invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    return SlashCommandOutcome(handled=True, status_requested=True, action=SlashAction.SHOW_STATUS)


def _handle_project(
    invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    arg = invocation.arg.strip()
    if arg:
        return SlashCommandOutcome(
            handled=True, project_switch_requested=arg, action=SlashAction.SWITCH_PROJECT, data=arg
        )
    return SlashCommandOutcome(
        handled=True, project_info_requested=True, action=SlashAction.SHOW_PROJECT
    )


def _handle_delete(
    invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    query = invocation.arg.strip() or None
    if not query:
        return SlashCommandOutcome(
            handled=True,
            error_lines=("Usage: /delete <number|id>",),
        )
    return SlashCommandOutcome(
        handled=True, delete_session_query=query, action=SlashAction.DELETE_SESSION, data=query
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
        return SlashCommandOutcome(
            handled=True, agent_picker_requested=True, action=SlashAction.SHOW_AGENTS
        )
    if error is not None:
        return SlashCommandOutcome(handled=True, error_lines=(error,))
    if selected is None:
        return SlashCommandOutcome(handled=True, error_lines=(format_agent_usage(),))
    return SlashCommandOutcome(
        handled=True, selected_agent=selected, action=SlashAction.SWITCH_AGENT, data=selected
    )


def _handle_tool(
    invocation: SlashCommandInvocation, _ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    query = invocation.arg.strip() or None
    return SlashCommandOutcome(
        handled=True,
        tool_requested=True,
        tool_query=query,
        action=SlashAction.SHOW_TOOL,
        data=query,
    )


def _handle_flow(
    invocation: SlashCommandInvocation, ctx: _SlashCommandContext
) -> SlashCommandOutcome:
    # Only available in orchestrator sessions
    if not ctx.is_orchestrator:
        return SlashCommandOutcome(
            handled=True,
            error_lines=(
                "The /flow command is only available in orchestrator sessions. "
                "Switch to the orchestrator session to use guided flow.",
            ),
        )
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
    return SlashCommandOutcome(handled=True, info_lines=tuple(lines), action=SlashAction.SHOW_INFO)


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
        name="sessions",
        description="List or attach chat sessions",
        handler=_handle_sessions,
    )
    registry.register(
        name="status",
        description="Show current project, session, and agent",
        handler=_handle_status,
    )
    registry.register(
        name="project",
        description="Show or switch active project",
        handler=_handle_project,
    )
    registry.register(
        name="delete",
        description="Delete a chat session: /delete <number|id>",
        handler=_handle_delete,
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
    # Mark flow as orchestrator-only after registration
    flow_cmd = registry._commands["flow"]
    registry._commands["flow"] = SlashCommand(
        spec=SlashCommandSpec(
            name="flow",
            description="Show guided Plan -> Execute -> Orchestrate flow",
            orchestrator_only=True,
        ),
        handler=flow_cmd.handler,
    )
    registry.register_alias("q", "exit")
    registry.register_alias("?", "help")
    registry.register_alias("s", "sessions")
    registry.register_alias("a", "agents")
    registry.register_alias("f", "flow")
    registry.register_alias("p", "project")
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
    project_name: str | None = None,
    project_id: str | None = None,
    turn_count: int = 0,
    is_orchestrator: bool = True,
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
        project_name=project_name,
        project_id=project_id,
        turn_count=turn_count,
        is_orchestrator=is_orchestrator,
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
    project_name: str | None = None,
    project_id: str | None = None,
    turn_count: int = 0,
    is_orchestrator: bool = True,
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
            project_name=project_name,
            project_id=project_id,
            turn_count=turn_count,
            is_orchestrator=is_orchestrator,
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
        project_name=project_name,
        project_id=project_id,
        turn_count=turn_count,
        is_orchestrator=is_orchestrator,
    )


def build_slash_presentation_lines(
    result: SlashCommandOutcome,
) -> tuple[SlashPresentationLine, ...]:
    lines: list[SlashPresentationLine] = [
        SlashPresentationLine(tone="info", text=text) for text in result.info_lines
    ]
    lines.extend(SlashPresentationLine(tone="error", text=text) for text in result.error_lines)
    return tuple(lines)
