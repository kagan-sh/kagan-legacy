from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.streaming import StreamingOutput

StreamChunkKind = Literal["assistant", "thought", "note", "user"]
Confidence = Literal["certain", "assumption", "needs-validation"]


@dataclass(frozen=True)
class AgentEventPresentation:
    text: str | None = None
    chunk_kind: StreamChunkKind | None = None
    note: str | None = None
    runtime_status: str | None = None
    stream_action: str | None = None
    confidence: Confidence = "certain"
    tool_id: str | None = None
    tool_title: str | None = None
    tool_status: str | None = None
    tool_args: str | None = None
    tool_result: str | None = None
    tool_kind: str | None = None
    terminal: Literal["completed", "failed"] | None = None

    @property
    def has_tool(self) -> bool:
        return self.tool_id is not None and self.tool_title is not None


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


def present_agent_event(event_type: str, payload: dict[str, Any]) -> AgentEventPresentation:
    if event_type == "output_chunk":
        text = stream_chunk_text(payload)
        if not text:
            return AgentEventPresentation()
        kind = stream_chunk_kind(payload)
        if kind == "thought":
            return AgentEventPresentation(
                text=text,
                chunk_kind=kind,
                runtime_status="thinking",
                stream_action="Reasoning through approach",
                confidence="assumption",
            )
        return AgentEventPresentation(
            text=text,
            chunk_kind=kind,
            runtime_status="thinking",
            stream_action="Streaming response",
        )

    if event_type in {"tool_call_start", "tool_call_update"}:
        title = tool_call_title(payload)
        status = tool_call_status(
            payload,
            default="running" if event_type == "tool_call_start" else "updated",
        )
        return AgentEventPresentation(
            runtime_status="thinking",
            stream_action=f"Running tool: {title}",
            tool_id=tool_call_id(payload),
            tool_title=title,
            tool_status=status,
            tool_args=tool_call_args(payload),
            tool_result=tool_call_result(payload),
            tool_kind=tool_call_kind(payload),
        )

    if event_type == "agent_completed":
        return AgentEventPresentation(
            note="Agent completed",
            runtime_status="ready",
            stream_action="Waiting for prompt",
            terminal="completed",
        )

    if event_type == "agent_failed":
        detail = stream_chunk_text(payload) or "Agent failed"
        return AgentEventPresentation(
            note=detail,
            runtime_status="error",
            stream_action="Agent failed",
            confidence="needs-validation",
            terminal="failed",
        )

    if event_type == "agent_status":
        status_text = str(payload.get("status") or acp_payload(payload).get("status") or "").lower()
        if status_text in {"running", "thinking", "initializing", "pending"}:
            return AgentEventPresentation(
                runtime_status="thinking",
                stream_action="Waiting for task agent response",
                confidence="assumption",
            )

    return AgentEventPresentation()


def render_agent_event_to_chat(panel: ChatPanel, event: AgentEventPresentation) -> None:
    if event.runtime_status is not None:
        panel.set_runtime_status(event.runtime_status)
    if event.stream_action is not None:
        panel.set_stream_action(event.stream_action, confidence=event.confidence)

    if event.text:
        if event.chunk_kind == "thought":
            panel.append_thought_fragment(event.text)
        else:
            panel.append_assistant_fragment(event.text)
        return

    if event.has_tool:
        panel.upsert_tool_call(
            event.tool_id or "tool",
            event.tool_title or "tool",
            status=event.tool_status or "running",
            args=event.tool_args,
            result=event.tool_result,
            kind=event.tool_kind,
        )
        return

    if event.terminal == "failed" and event.note:
        panel.add_system_message(event.note)


def render_agent_event_to_output(
    output: StreamingOutput,
    event: AgentEventPresentation,
    *,
    merge: bool,
) -> None:
    if event.text and event.chunk_kind is not None:
        output.append_chunk(event.text, kind=event.chunk_kind, merge=merge)
        return
    if event.note:
        output.post_note(event.note)
