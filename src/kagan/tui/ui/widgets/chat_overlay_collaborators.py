from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from kagan.core.agents.planner_parser import parse_proposed_plan
from kagan.core.domain.enums import ChatRole, StreamPhase, TaskStatus
from kagan.core.safety import normalize_untrusted_text, redact_sensitive_text


class ChatOverlayTargetManager:
    """Manage target/session selection concerns for ChatOverlay."""

    def __init__(self, overlay: Any) -> None:
        self._overlay = overlay

    async def refresh_chat_targets(self) -> None:
        overlay = self._overlay
        current_key = overlay._active_target().key
        targets: list[Any] = [overlay._orchestrator_target()]
        overlay._task_context_by_id = {}
        ctx = getattr(overlay.app, "ctx", None)
        requested_task_id = overlay._requested_task_id
        requested_context = overlay._requested_task_context

        if ctx is not None and getattr(ctx, "active_project_id", None):
            project_id = ctx.active_project_id
            in_progress: list[object] = []
            in_review: list[object] = []
            try:
                in_progress_result, in_review_result = await asyncio.gather(
                    ctx.api.list_tasks(
                        project_id=project_id,
                        status=TaskStatus.IN_PROGRESS.value,
                    ),
                    ctx.api.list_tasks(
                        project_id=project_id,
                        status=TaskStatus.REVIEW.value,
                    ),
                    return_exceptions=True,
                )
                if not isinstance(in_progress_result, Exception):
                    in_progress = list(in_progress_result)
                if not isinstance(in_review_result, Exception):
                    in_review = list(in_review_result)
            except Exception:
                in_progress = []
                in_review = []

            for task in in_progress:
                context = overlay._task_context(task)
                if context is None:
                    continue
                overlay._task_context_by_id[context.task_id] = context
                overlay._append_target_if_missing(targets, overlay._target_from_context(context))

            for task in in_review:
                context = overlay._task_context(task)
                if context is None:
                    continue
                overlay._task_context_by_id[context.task_id] = context
                overlay._append_target_if_missing(targets, overlay._target_from_context(context))

        if requested_context is None and requested_task_id:
            requested_context = overlay._task_context_by_id.get(requested_task_id)
        if requested_context is None and requested_task_id and ctx is not None:
            try:
                fetched_task = await ctx.api.get_task(requested_task_id)
            except Exception:
                fetched_task = None
            if fetched_task is not None:
                requested_context = overlay._task_context(fetched_task)
                if requested_context is not None:
                    overlay._task_context_by_id[requested_context.task_id] = requested_context

        preferred_key: str | None = None
        if requested_context is not None:
            overlay._focused_task_context = requested_context
            overlay._append_target_if_missing(
                targets, overlay._target_from_context(requested_context)
            )
            preferred_key = overlay._preferred_target_key_for_context(requested_context, targets)
        elif requested_task_id:
            for target in targets:
                if target.task_id == requested_task_id:
                    preferred_key = target.key
                    break

        overlay._chat_targets = targets
        selected_index: int | None = None
        if preferred_key is not None:
            for index, target in enumerate(overlay._chat_targets):
                if target.key == preferred_key:
                    selected_index = index
                    break
        if selected_index is None:
            for index, target in enumerate(overlay._chat_targets):
                if target.key == current_key:
                    selected_index = index
                    break
        overlay._active_target_index = selected_index if selected_index is not None else 0
        overlay._requested_task_id = None
        overlay._requested_task_context = None
        overlay._sync_active_target_ui()
        with contextlib.suppress(Exception):
            await overlay._sync_active_target_session()

    async def execute_targets(self) -> None:
        overlay = self._overlay
        await self.refresh_chat_targets()
        overlay._show_output()
        lines = [
            "**Chat Sessions (Tab to cycle):**",
            "",
            "Use `/attach <task-id|kind|label>` to switch directly.",
            "",
        ]
        active_key = overlay._active_target().key
        for target in overlay._chat_targets:
            marker = " (active)" if target.key == active_key else ""
            task_hint = f" [task: `{target.task_id}`]" if target.task_id else ""
            lines.append(f"- `{target.kind.value}`: {target.label}{task_hint}{marker}")
        await overlay.output.post_note("\n".join(lines))


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
                "compact": "Compact context",
                "browse": "List chat sessions",
                "attach": "Attach to a session",
                "restart": "Restart AUTO target",
                "stop": "Stop AUTO target",
                "skills": "List local skills",
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
                "- `Tab` cycles active chat session (Orchestrator/AUTO/REVIEW).\n"
                "- `/browse` lists sessions; `/attach <id|kind|label>` switches directly.\n"
                "- `/restart [extra context]` starts the next AUTO iteration "
                "for the active AUTO target.\n"
                "- `/stop` requests stop for the active AUTO session.\n"
                "- `/new session` starts a fresh local chat session.\n"
                "- `/clear all sessions` resets local chat sessions and target focus.\n"
                "- `/skills` lists trusted local skill metadata; `/skills refresh` rescans.\n"
                "- `/mode` with no args lists modes; `/mode <id>` switches mode.\n"
                "- `/compact` prefers native agent compaction; when unavailable it uses "
                "Kagan's redacted snapshot + fresh-session fallback.\n"
            )
        await overlay.output.post_note(help_text)

    async def execute_skills(self, args: str) -> None:
        overlay = self._overlay
        normalized = overlay._normalize_command_args(args)
        if normalized not in {"", "list", "refresh"}:
            overlay.notify("Usage: /skills [list|refresh]", severity="warning")
            return

        overlay._show_output()
        if not overlay._auto_skill_discovery_enabled():
            await overlay.output.post_note(
                "Skill discovery is disabled. Enable "
                "`general.auto_skill_discovery` in Settings to scan trusted local skill roots.",
                classes="info",
            )
            return

        discovered = overlay._discover_local_skills(force_refresh=normalized == "refresh")
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
        if not overlay._conversation_history:
            return ""
        lines: list[str] = []
        for role, content in overlay._conversation_history[-overlay._COMPACT_MAX_HISTORY_ITEMS :]:
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
