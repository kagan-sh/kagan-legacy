from __future__ import annotations

import contextlib
from time import monotonic
from typing import Any

from kagan.core.agents.planner_parser import parse_proposed_plan
from kagan.core.domain.enums import ChatRole, StreamPhase
from kagan.core.safety import normalize_untrusted_text, redact_sensitive_text


class ChatOverlayTargetManager:
    """Manage target/session selection concerns for ChatOverlay."""

    def __init__(self, overlay: Any) -> None:
        self._overlay = overlay

    async def _load_task_context(self, task_id: str) -> Any | None:
        overlay = self._overlay
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return None
        existing_context = overlay._task_context_by_id.get(normalized_task_id)
        if existing_context is not None:
            return existing_context
        ctx = getattr(overlay.app, "ctx", None)
        if ctx is None:
            return None
        try:
            task = await ctx.api.get_task(normalized_task_id)
        except Exception:
            return None
        if task is None:
            return None
        return overlay._task_context(task)

    async def refresh_chat_targets(self, *, force: bool = False) -> None:
        overlay = self._overlay
        current_key = overlay._active_target().key
        target_scope_task_id = overlay._target_scope_task_id
        requested_task_id = overlay._requested_task_id
        requested_context = overlay._requested_task_context

        cache_key = (
            target_scope_task_id,
            requested_task_id,
            requested_context.task_id if requested_context is not None else None,
        )
        if (
            not force
            and overlay._chat_targets
            and requested_task_id is None
            and requested_context is None
            and overlay._chat_targets_cache_key == cache_key
            and monotonic() - overlay._chat_targets_cache_at
            <= overlay._CHAT_TARGETS_CACHE_TTL_SECONDS
        ):
            overlay._sync_active_target_ui()
            with contextlib.suppress(Exception):
                await overlay._sync_active_target_session()
            return

        overlay._task_context_by_id = {}

        overlay._focused_task_context = None
        targets: list[Any]
        preferred_key: str | None = None
        if target_scope_task_id is None:
            targets = overlay._orchestrator_targets()
            if requested_context is None and requested_task_id:
                requested_context = await self._load_task_context(requested_task_id)
            if requested_context is not None:
                overlay._task_context_by_id[requested_context.task_id] = requested_context
                overlay._focused_task_context = requested_context
            preferred_key = overlay._active_orchestrator_target_key()
        else:
            targets = []
            if requested_context is None or requested_context.task_id != target_scope_task_id:
                requested_context = await self._load_task_context(target_scope_task_id)
            if requested_context is not None:
                overlay._task_context_by_id[requested_context.task_id] = requested_context
                overlay._focused_task_context = requested_context
                for target in overlay._scoped_targets_for_context(requested_context):
                    overlay._append_target_if_missing(targets, target)
                preferred_key = overlay._preferred_target_key_for_context(
                    requested_context,
                    targets,
                )
            if not targets:
                targets.append(overlay._fallback_scoped_target(target_scope_task_id))
                preferred_key = targets[0].key

        overlay._chat_targets = targets
        selected_index: int | None = None
        for index, target in enumerate(overlay._chat_targets):
            if target.key == current_key:
                selected_index = index
                break
        if selected_index is None and preferred_key is not None:
            for index, target in enumerate(overlay._chat_targets):
                if target.key == preferred_key:
                    selected_index = index
                    break
        overlay._active_target_index = selected_index if selected_index is not None else 0
        overlay._requested_task_id = None
        overlay._requested_task_context = None
        overlay._chat_targets_cache_key = (
            target_scope_task_id,
            None,
            None,
        )
        overlay._chat_targets_cache_at = monotonic()
        overlay._sync_active_target_ui()
        with contextlib.suppress(Exception):
            await overlay._sync_active_target_session()


class ChatOverlaySlashCommandExecutor:
    """Execute slash-command behaviors extracted from ChatOverlay."""

    def __init__(self, overlay: Any) -> None:
        self._overlay = overlay

    async def execute_help(self) -> None:
        overlay = self._overlay
        overlay._show_output()
        commands = sorted(overlay._slash_popup_commands(), key=lambda cmd: cmd.command)
        verbosity = overlay._interaction_verbosity()

        if verbosity == "tldr":
            quick = {
                "help": "Show commands",
                "clear": "Reset conversation",
                "new": "Start fresh session",
                "export": "Copy session transcript",
                "compact": "Compact context",
                "sessions": "Open session quick-pick",
                "agent": "Run grouped agent commands",
                "restart": "Restart AUTO runtime task",
                "stop": "Stop AUTO runtime task",
                "close": "Close orchestrator session",
                "mode": "List/set mode",
            }
            lines = ["**Quick Commands:**", ""]
            for name, description in quick.items():
                lines.append(f"- `/{name}` - {description}")
            lines.append("")
            lines.append(
                "Switch to short/technical verbosity in Settings for full command details."
            )
            await overlay.output.post_note("\n".join(lines))
            return

        help_text = "**Available Commands:**\n"
        for command in commands:
            aliases = ""
            if command.aliases:
                alias_text = ", ".join(f"/{alias}" for alias in command.aliases)
                aliases = f" ({alias_text})"
            help_text += f"- `/{command.command}`{aliases} - {command.help}\n"
        if verbosity == "technical":
            help_text += (
                "\n**Usage Notes:**\n"
                "- `Ctrl+K` opens the session quick-pick for all active project sessions.\n"
                "- `Tab` cycles linearly in task scope.\n"
                "- On board, `Tab` cycles active attention targets.\n"
                "- `/sessions` opens the same quick-pick palette.\n"
                "- `/agent` lists grouped agent commands; `/agent <command> [args]` executes one.\n"
                "- `/restart [extra context]` starts the next AUTO iteration "
                "for the active AUTO runtime task.\n"
                "- `/stop` requests stop for the active AUTO runtime task.\n"
                "- `/new session` creates and switches to a new orchestrator session.\n"
                "- `/close session` closes the active orchestrator session.\n"
                "- `/export` copies the active session transcript to the clipboard.\n"
                "- `/clear all sessions` resets local chat sessions and target focus.\n"
                "- `/agent skills` lists trusted local skill metadata; "
                "`/agent skills refresh` rescans.\n"
                "- `/mode` with no args lists modes; `/mode <id>` switches mode.\n"
                "- `/compact` prefers native agent compaction; when unavailable it uses "
                "Kagan's redacted snapshot + fresh-session fallback.\n"
            )
        await overlay.output.post_note(help_text)

    async def execute_skills(self, args: str) -> None:
        overlay = self._overlay
        normalized = overlay._normalize_command_args(args)
        if normalized not in {"", "list", "refresh"}:
            overlay.notify("Usage: /agent skills [list|refresh]", severity="warning")
            return

        overlay._show_output()
        if not overlay._auto_skill_discovery_enabled():
            await overlay.output.post_note(
                "Skill discovery is disabled. Enable "
                "`general.auto_skill_discovery` in Settings to scan trusted local skill roots.",
                classes="info",
            )
            return

        discovered = await overlay._discover_local_skills_async(
            force_refresh=normalized == "refresh"
        )
        if not discovered:
            await overlay.output.post_note(
                "No local skills discovered in trusted roots "
                "(`.agents/.pi/.claude/.codex/.vtcode`).",
                classes="info",
            )
            return

        lines = [
            "**Discovered Local Skills:**",
            "",
            "Metadata-only catalog from trusted local roots. Skill instruction bodies are not "
            "auto-loaded.",
            "",
        ]
        for skill in discovered[: overlay._SKILL_DISCOVERY_DISPLAY_LIMIT]:
            try:
                relative_path = skill.location.relative_to(skill.source_root)
                location = f"{skill.source_root}/{relative_path}"
            except ValueError:
                location = str(skill.location)
            description = skill.description or "No description"
            lines.append(f"- `{skill.name}`: {description} (`{location}`)")
        if len(discovered) > overlay._SKILL_DISCOVERY_DISPLAY_LIMIT:
            omitted = len(discovered) - overlay._SKILL_DISCOVERY_DISPLAY_LIMIT
            lines.append("")
            lines.append(f"... and {omitted} more skill(s).")
        await overlay.output.post_note("\n".join(lines))


class ChatOverlayStreamCoordinator:
    """Coordinate stream/event-specific handlers for ChatOverlay."""

    def __init__(self, overlay: Any) -> None:
        self._overlay = overlay

    async def on_agent_message(self, message: object) -> None:
        overlay = self._overlay
        await overlay._get_agent_stream().dispatch(message)

    async def handle_agent_update(self, msg: object) -> None:
        overlay = self._overlay
        await overlay.output.post_response(msg.text)

    async def handle_thinking(self, msg: object) -> None:
        overlay = self._overlay
        await overlay.output.post_thought(msg.text)

    async def handle_agent_ready(self) -> None:
        overlay = self._overlay
        overlay._clearing = False
        await overlay.output.clear_thinking_indicator(phase=StreamPhase.IDLE)
        overlay._update_status("ready", overlay._ready_hint(overlay._active_target()))

    async def handle_tool_call(self, msg: object) -> None:
        overlay = self._overlay
        tool = msg.tool_call
        tool_id = (
            getattr(tool, "tool_call_id", None) or getattr(tool, "toolCallId", None) or "unknown"
        )
        tool_name = (getattr(tool, "name", None) or getattr(tool, "title", None) or "").lower()
        if "plan_tasks" not in tool_name and "plan_submit" not in tool_name:
            await overlay.output.upsert_tool_call(tool)
            return
        tasks, _todos, err = parse_proposed_plan({tool_id: tool})
        if err or not tasks:
            await overlay.output.post_note(err or "Could not parse plan", classes="error")
            return
        await overlay.output.post_plan_approval(tasks)

    def build_compact_snapshot(self) -> str:
        overlay = self._overlay
        target = overlay._active_target()
        target_kind = getattr(getattr(target, "kind", None), "value", "")
        target_key = (
            target.key
            if target_kind == "orchestrator"
            else overlay._active_orchestrator_target_key()
        )
        conversation_history = overlay._conversation_history_by_target_key.get(target_key, [])
        if not conversation_history:
            return ""
        lines: list[str] = []
        for role, content in conversation_history[-overlay._COMPACT_MAX_HISTORY_ITEMS :]:
            role_token = str(role).strip().lower()
            role_label = (
                "User"
                if role_token in {str(ChatRole.USER), ChatRole.USER.value, "user"}
                else "Assistant"
            )
            sanitized = redact_sensitive_text(
                normalize_untrusted_text(content, max_chars=overlay._COMPACT_ENTRY_MAX_CHARS),
                redact_pii=True,
            ).strip()
            if not sanitized:
                continue
            lines.append(f"{role_label}: {sanitized}")
        snapshot = "\n".join(lines).strip()
        if len(snapshot) > overlay._COMPACT_SNAPSHOT_MAX_CHARS:
            return snapshot[: overlay._COMPACT_SNAPSHOT_MAX_CHARS - 1].rstrip() + "…"
        return snapshot


__all__ = [
    "ChatOverlaySlashCommandExecutor",
    "ChatOverlayStreamCoordinator",
    "ChatOverlayTargetManager",
]
