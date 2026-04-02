"""Agent lifecycle hooks — extensible pre/post tool execution callbacks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from loguru import logger


class HookEvent(StrEnum):
    """Points in the agent lifecycle where hooks can fire."""

    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    POST_TURN = "post_turn"
    SESSION_END = "session_end"


class HookAction(StrEnum):
    """What a hook wants the runner to do after executing."""

    CONTINUE = "continue"
    CANCEL_SESSION = "cancel_session"


@dataclass(slots=True)
class HookContext:
    """Data passed to hooks at each lifecycle point."""

    task_id: str
    session_id: str
    event: HookEvent
    tool_name: str | None = None
    tool_arguments: Any = None
    tool_result: Any = None


@dataclass(slots=True)
class HookResult:
    """What a hook returns after execution."""

    action: HookAction = HookAction.CONTINUE
    message: str | None = None


class Hook(Protocol):
    """Protocol for lifecycle hooks."""

    @property
    def name(self) -> str: ...

    @property
    def events(self) -> frozenset[HookEvent]: ...

    def execute(self, context: HookContext) -> HookResult: ...


@dataclass(slots=True)
class RepetitionHook:
    """Built-in hook: detects agents stuck in tool-call loops.

    Migrated from the standalone RepetitionGuard.
    """

    _name: str = "repetition_guard"
    _events: frozenset[HookEvent] = field(default_factory=lambda: frozenset({HookEvent.PRE_TOOL}))
    window: int = 20
    threshold: int = 8
    _recent: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self._name

    @property
    def events(self) -> frozenset[HookEvent]:
        return self._events

    def execute(self, context: HookContext) -> HookResult:
        from kagan.core._repetition_guard import _normalize_for_hash

        if context.tool_name is None:
            return HookResult()

        arg_hash = hashlib.blake2s(
            _normalize_for_hash(context.tool_arguments).encode(), digest_size=8
        ).hexdigest()
        key = f"{context.tool_name}:{arg_hash}"

        self._recent.append(key)
        if len(self._recent) > self.window:
            self._recent.pop(0)

        count = sum(1 for k in self._recent if k == key)
        if count >= self.threshold:
            return HookResult(
                action=HookAction.CANCEL_SESSION,
                message="Agent detected in tool-call loop; session cancelled",
            )
        return HookResult()


@dataclass(slots=True)
class DangerousCommandHook:
    """Built-in hook: blocks known destructive shell commands."""

    _name: str = "dangerous_command_guard"
    _events: frozenset[HookEvent] = field(default_factory=lambda: frozenset({HookEvent.PRE_TOOL}))
    _blocked_patterns: tuple[str, ...] = (
        "rm -rf /",
        "git push --force",
        "git push -f",
        "git reset --hard",
        "DROP TABLE",
        "DROP DATABASE",
    )

    @property
    def name(self) -> str:
        return self._name

    @property
    def events(self) -> frozenset[HookEvent]:
        return self._events

    def execute(self, context: HookContext) -> HookResult:
        if context.tool_name is None or context.tool_arguments is None:
            return HookResult()

        args_str = str(context.tool_arguments).lower()
        for pattern in self._blocked_patterns:
            if pattern.lower() in args_str:
                logger.warning(
                    "Dangerous command blocked: pattern={!r} tool={} task={}",
                    pattern,
                    context.tool_name,
                    context.task_id,
                )
                return HookResult(
                    action=HookAction.CANCEL_SESSION,
                    message=f"Blocked dangerous command matching pattern: {pattern!r}",
                )
        return HookResult()


class HookRunner:
    """Manages and executes hooks at lifecycle points."""

    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        self._hooks.append(hook)
        logger.debug("Registered hook: {}", hook.name)

    def fire(self, context: HookContext) -> HookResult:
        """Fire all hooks registered for the given event.

        Returns first non-CONTINUE result, or CONTINUE if all pass.
        """
        for hook in self._hooks:
            if context.event not in hook.events:
                continue
            try:
                result = hook.execute(context)
                if result.action != HookAction.CONTINUE:
                    logger.info(
                        "Hook {!r} returned action={} for event={} task={}",
                        hook.name,
                        result.action.value,
                        context.event.value,
                        context.task_id,
                    )
                    return result
            except Exception:
                logger.exception("Hook {!r} failed for event={}", hook.name, context.event.value)
        return HookResult()

    def default_hooks(self) -> HookRunner:
        """Register the default built-in hooks and return self for chaining."""
        self.register(RepetitionHook())
        self.register(DangerousCommandHook())
        return self
