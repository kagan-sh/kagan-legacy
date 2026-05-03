"""ChatTranscript — message rendering region of the chat panel.

Subclasses ``Vertical`` so it 1:1 replaces the previous ``Vertical(id="chat-overlay-content")``
container in ``ChatPanel.compose()``. The DOM (id, classes, nested children) is
unchanged so snapshot tests remain byte-identical.

Owns rendering of session entries, the streaming output handle, the inline
decision surface (permission prompts), and the hidden messages buffer used by
tests. Cross-cutting state (selected session, runtime status) still lives on
``ChatPanel``; rendering methods take the entries to render as arguments rather
than reaching back into the parent.
"""

from __future__ import annotations

from typing import Any

from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Static

from kagan.tui.widgets.permission import PermissionPrompt
from kagan.tui.widgets.streaming import StreamingOutput

_EMPTY_TEXT = "No messages yet"


class ChatTranscript(Vertical):
    """Vertical container holding the streaming output, decision surface,
    empty-state card, and hidden test buffer. Replaces
    ``Vertical(id="chat-overlay-content")``.
    """

    DEFAULT_CSS = ""

    # ------- query helpers -------

    def stream_output(self) -> StreamingOutput | None:
        try:
            return self.query_one("#chat-overlay-output", StreamingOutput)
        except NoMatches:
            return None

    # ------- rendering -------

    def render_session(
        self,
        entries: list[tuple[str, dict[str, Any]]],
        decision_surface: tuple[str, dict[str, Any]] | None,
    ) -> None:
        stream = self.stream_output()
        if stream is not None:
            stream.clear()
            for kind, payload in entries:
                self.render_entry(stream, kind, payload)
        self.render_decision_surface(decision_surface)
        self.update_hidden_buffer(entries)

    def render_entry(self, stream: StreamingOutput, kind: str, payload: dict[str, Any]) -> None:
        raw_text = str(payload.get("text") or "")
        text = raw_text.strip()
        if kind == "user" and text:
            stream.post_user_input(text)
            return
        if kind == "assistant" and raw_text:
            stream.append_chunk(raw_text, kind="assistant")
            return
        if kind == "thought" and raw_text:
            stream.append_chunk(raw_text, kind="thought")
            return
        if kind == "note" and text:
            stream.post_note(text)
            return
        if kind == "tool":
            stream.upsert_tool_call(
                str(payload.get("tool_id") or "tool"),
                str(payload.get("title") or payload.get("tool_id") or "tool"),
                status=str(payload.get("status") or "running"),
                args=payload.get("args"),
                result=payload.get("result"),
                kind=payload.get("kind"),
            )

    def render_decision_surface(self, decision_surface: tuple[str, dict[str, Any]] | None) -> None:
        try:
            container = self.query_one("#chat-inline-surface", Vertical)
        except NoMatches:
            return
        for child in list(container.children):
            child.remove()
        if decision_surface is None:
            container.display = False
            return

        kind, payload = decision_surface
        if kind == "permission":
            container.mount(
                PermissionPrompt(
                    str(payload.get("text") or "Permission required"),
                    timeout_seconds=int(payload.get("timeout_seconds") or 30),
                )
            )
        container.display = True

    @staticmethod
    def rendered_messages(entries: list[tuple[str, dict[str, Any]]]) -> list[str]:
        rendered: list[str] = []
        for kind, payload in entries:
            text = str(payload.get("text") or "").strip()
            if kind == "user" and text:
                rendered.append(f"You: {text}")
            elif kind == "assistant" and text:
                rendered.append(f"Agent: {text}")
            elif kind == "thought" and text:
                rendered.append(f"Thinking: {text}")
            elif kind == "note" and text:
                rendered.append(f"System: {text}")
            elif kind == "tool":
                title = str(payload.get("title") or payload.get("tool_id") or "tool")
                status = str(payload.get("status") or "running")
                rendered.append(f"Tool: {title} [{status}]")
        return rendered

    def update_hidden_buffer(self, entries: list[tuple[str, dict[str, Any]]]) -> None:
        try:
            messages = self.query_one("#chat-messages", Static)
        except NoMatches:
            return
        rendered = self.rendered_messages(entries)
        if not rendered:
            messages.set_class(True, "chat-empty")
            messages.update(_EMPTY_TEXT)
            return
        messages.set_class(False, "chat-empty")
        messages.update("\n".join(rendered[-200:]))

    # ------- streaming convenience -------

    def append_assistant_fragment(self, text: str, *, merge: bool = True) -> None:
        stream = self.stream_output()
        if stream is None:
            return
        stream.append_chunk(text, kind="assistant", merge=merge)

    def append_thought_fragment(self, text: str, *, merge: bool = True) -> None:
        stream = self.stream_output()
        if stream is None:
            return
        stream.append_chunk(text, kind="thought", merge=merge)

    def post_user_input(self, text: str) -> None:
        stream = self.stream_output()
        if stream is None:
            return
        stream.post_user_input(text)

    def post_note(self, text: str) -> None:
        stream = self.stream_output()
        if stream is None:
            return
        stream.post_note(text)

    def upsert_tool_call(
        self,
        tool_id: str,
        title: str,
        *,
        status: str = "running",
        args: str | None = None,
        result: str | None = None,
        kind: str | None = None,
    ) -> None:
        stream = self.stream_output()
        if stream is None:
            return
        stream.upsert_tool_call(tool_id, title, status=status, args=args, result=result, kind=kind)

    def update_tool_status(self, tool_id: str, status: str, *, result: str | None = None) -> None:
        stream = self.stream_output()
        if stream is None:
            return
        stream.update_tool_status(tool_id, status, result=result)

    def clear_stream(self) -> None:
        stream = self.stream_output()
        if stream is None:
            return
        stream.clear()
