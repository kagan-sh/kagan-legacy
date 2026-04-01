import contextlib
import json
from collections.abc import Callable
from typing import Any, Literal, cast

from acp.schema import AgentMessageChunk, AgentThoughtChunk, ToolCallProgress, ToolCallStart

from kagan.cli.chat import (
    build_orchestrator_prompt,
    resolve_default_agent_backend,
    run_orchestrator_turn,
    warm_orchestrator_backend,
)
from kagan.core import KaganCore
from kagan.core.enums import SessionEventType
from kagan.core.errors import KaganError
from kagan.tui.widgets.chat import ChatPanel

StreamChunkKind = Literal["assistant", "thought", "note", "user"]


def acp_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("acp")
    return nested if isinstance(nested, dict) else {}


def _content_text(content: object) -> str:
    if isinstance(content, dict):
        if str(content.get("type") or "") != "text":
            return ""
        return str(content.get("text") or "")
    if content is None or getattr(content, "type", None) != "text":
        return ""
    return str(getattr(content, "text", "") or "")


def _serialize_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True)
    except TypeError:
        return str(value)


def stream_chunk_kind(payload: dict[str, Any]) -> StreamChunkKind:
    kind = str(payload.get("kind") or "").strip().lower()
    if kind in {"assistant", "thought", "note", "user"}:
        return cast("StreamChunkKind", kind)
    if payload.get("thought"):
        return "thought"
    session_update = str(acp_payload(payload).get("sessionUpdate") or "").strip().lower()
    if session_update == "agent_thought_chunk":
        return "thought"
    return "assistant"


def stream_chunk_text(payload: object) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("text", "chunk", "content"):
            text = payload.get(key)
            if isinstance(text, str) and text:
                return text
            if text is not None:
                nested_text = _content_text(text)
                if nested_text:
                    return nested_text
        text = _content_text(acp_payload(payload).get("content"))
        if text:
            return text
        for key in ("error", "details", "reason"):
            if key in payload:
                return str(payload[key])
        if "message" in payload:
            return str(payload["message"])
    return ""


def tool_call_id(payload: dict[str, Any]) -> str:
    nested = acp_payload(payload)
    return str(
        payload.get("id")
        or payload.get("tool_id")
        or nested.get("toolCallId")
        or nested.get("tool_call_id")
        or payload.get("name")
        or "tool"
    )


def _format_tool_name(raw: str) -> str:
    if raw.startswith("toolu_") or raw.startswith("call_"):
        return "tool call"
    if "__" in raw:
        parts = raw.split("__")
        if parts[0] in {"mcp", "functions"} and len(parts) >= 3:
            return " / ".join(parts[1:])
        return " / ".join(parts)
    return raw.replace("_", " ")


def tool_call_title(payload: dict[str, Any]) -> str:
    nested = acp_payload(payload)
    raw = str(
        nested.get("title") or payload.get("name") or payload.get("tool") or tool_call_id(payload)
    )
    return _format_tool_name(raw)


def tool_call_status(payload: dict[str, Any], *, default: str) -> str:
    nested = acp_payload(payload)
    return str(payload.get("status") or nested.get("status") or default)


def tool_call_kind(payload: dict[str, Any]) -> str | None:
    nested = acp_payload(payload)
    return str(nested.get("kind") or payload.get("kind") or "") or None


def tool_call_args(payload: dict[str, Any]) -> str | None:
    nested = acp_payload(payload)
    raw = payload.get("args") or payload.get("rawInput") or nested.get("rawInput")
    return _serialize_value(raw)


def tool_call_result(payload: dict[str, Any]) -> str | None:
    nested = acp_payload(payload)
    return _serialize_value(
        payload.get("result") or payload.get("rawOutput") or nested.get("rawOutput")
    )


def apply_task_chat_event(
    panel: ChatPanel,
    event_type: SessionEventType,
    payload: dict[str, Any],
) -> None:
    if event_type == SessionEventType.OUTPUT_CHUNK:
        text = stream_chunk_text(payload)
        if not text:
            return
        kind = stream_chunk_kind(payload)
        panel.set_runtime_status("thinking")
        if kind == "thought":
            panel.set_stream_action("Reasoning through approach", confidence="assumption")
            panel.append_thought_fragment(text)
            return
        panel.set_stream_action("Streaming response", confidence="certain")
        panel.append_assistant_fragment(text)
        return

    if event_type == SessionEventType.TOOL_CALL_START:
        title = tool_call_title(payload)
        panel.set_runtime_status("thinking")
        panel.upsert_tool_call(
            tool_call_id(payload),
            title,
            status=tool_call_status(payload, default="running"),
            args=tool_call_args(payload),
            result=tool_call_result(payload),
            kind=tool_call_kind(payload),
        )
        panel.set_stream_action(f"Running tool: {title}", confidence="certain")
        return

    if event_type == SessionEventType.TOOL_CALL_UPDATE:
        title = tool_call_title(payload)
        panel.set_runtime_status("thinking")
        panel.upsert_tool_call(
            tool_call_id(payload),
            title,
            status=tool_call_status(payload, default="updated"),
            args=tool_call_args(payload),
            result=tool_call_result(payload),
            kind=tool_call_kind(payload),
        )
        panel.set_stream_action(f"Running tool: {title}", confidence="certain")
        return

    if event_type == SessionEventType.AGENT_COMPLETED:
        panel.set_runtime_status("ready")
        panel.set_stream_action("Waiting for prompt", confidence="certain")
        return

    if event_type == SessionEventType.AGENT_FAILED:
        panel.set_runtime_status("error")
        panel.set_stream_action("Agent failed", confidence="needs-validation")
        detail = stream_chunk_text(payload) or "Agent failed"
        panel.add_system_message(detail)
        return

    if event_type == SessionEventType.AGENT_STATUS:
        status_text = str(payload.get("status") or acp_payload(payload).get("status") or "").lower()
        if status_text in {"running", "thinking", "initializing", "pending"}:
            panel.set_runtime_status("thinking")
            panel.set_stream_action("Waiting for task agent response", confidence="assumption")


async def send_orchestrator_message(
    *,
    core: KaganCore,
    panel: ChatPanel,
    text: str,
    history: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    settings = await core.settings.get()
    backend = panel.preferred_agent_backend() or resolve_default_agent_backend(settings)
    panel.set_agent_backend(backend)
    prompt = build_orchestrator_prompt(history, text)
    panel.set_runtime_status("initializing")
    panel.set_stream_action("Initializing...", confidence="assumption")
    with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
        await warm_orchestrator_backend(core, agent_backend=backend)
    streamed_assistant = False

    async def _on_update(update: object) -> None:
        nonlocal streamed_assistant
        if isinstance(update, AgentThoughtChunk):
            fragment = _content_text(update.content)
            if fragment:
                panel.set_runtime_status("thinking")
                panel.set_stream_action("Reasoning through approach", confidence="assumption")
                panel.append_thought_fragment(fragment)
            return

        if isinstance(update, AgentMessageChunk):
            fragment = _content_text(update.content)
            if fragment:
                streamed_assistant = True
                panel.set_runtime_status("thinking")
                panel.set_stream_action("Streaming response", confidence="certain")
                panel.append_assistant_fragment(fragment)
            return

        if isinstance(update, ToolCallStart):
            panel.set_runtime_status("thinking")
            panel.upsert_tool_call(
                update.tool_call_id,
                update.title,
                status=str(update.status or "running"),
                args=_serialize_value(update.raw_input),
                result=_serialize_value(update.raw_output),
            )
            panel.set_stream_action(f"Running tool: {update.title}", confidence="certain")
            return

        if isinstance(update, ToolCallProgress):
            title = str(update.title or update.tool_call_id)
            panel.set_runtime_status("thinking")
            panel.upsert_tool_call(
                update.tool_call_id,
                title,
                status=str(update.status or "updated"),
                result=_serialize_value(update.raw_output),
            )
            panel.set_stream_action(f"Running tool: {title}", confidence="certain")

    reply = await run_orchestrator_turn(
        core,
        prompt=prompt,
        agent_backend=backend,
        on_update=_on_update,
    )
    response = reply or "No response from orchestrator"
    if not streamed_assistant and response:
        panel.add_assistant_message(response)
    panel.set_runtime_status("ready")
    panel.increment_turn_count()
    panel.set_stream_action("Waiting for prompt", confidence="certain")
    return [*history, ("user", text), ("assistant", response)]


async def stream_task_chat(
    *,
    core: KaganCore,
    panel: ChatPanel,
    task_id: str,
    is_active: Callable[[], bool],
) -> None:
    async for event in core.tasks.events.stream(task_id):
        if not is_active():
            continue

        payload = event.payload or {}
        apply_task_chat_event(panel, event.event_type, payload)
