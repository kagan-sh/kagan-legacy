# CLI Chat Architecture

The `src/kagan/cli/chat/` module implements the chat REPL, the orchestrator chat controller, and the ACP streaming layer. It is one of the more complex subsystems — this document maps the call flow.

## File map

| File                 | Role                                                                                                        |
| -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `commands.py`        | Slash command parsing (`/help`, `/agents`, `/sessions`, `/attach`, `/clear`, etc.) — pure data, no I/O      |
| `controller.py`      | `ChatController` — stateful chat session: ties together commands, streaming, ACP, and the approval batch UI |
| `acp.py`             | ACP client helpers for orchestrator warmup and legacy spawn-per-turn execution                              |
| `_streaming.py`      | Response buffering and markdown streaming primitives used by the CLI renderer                               |
| `_renderer.py`       | `CLIRenderer` — converts `ChatEvent` stream into Rich console output                                        |
| `_approval_batch.py` | Batch approval UI for multi-task orchestrator runs                                                          |
| `_approval_panel.py` | Single-task approval panel widget                                                                           |
| `_permission_ui.py`  | Interactive permission prompts (ACP `RequestPermission` events)                                             |
| `_chat_ui.py`        | Rich `Live` layout for the REPL session frame                                                               |
| `_signals.py`        | Internal signal types (e.g. `AbortSignal`) passed between layers                                            |
| `_handshake.py`      | ACP handshake protocol helpers                                                                              |
| `_session_picker.py` | Interactive session selection (attach to existing sessions)                                                 |
| `_title.py`          | Dynamic title bar for the REPL                                                                              |
| `_theme.py`          | Rich theme constants for chat output                                                                        |
| `_utils.py`          | Shared helpers (`fuzzy_match`, etc.) used by REPL completion and session picker                             |
| `agents.py`          | Agent listing/resolution helpers (`/agents` command support)                                                |
| `prompt.py`          | Input normalization utilities                                                                               |
| `__init__.py`        | Public surface: `run_chat()` / `run_chat_async()` entrypoints                                               |

## Call flow

```
CLI entrypoint (src/kagan/cli/)
  └─ run_chat_async()              __init__.py
       └─ ChatController           controller.py
            ├─ parse_slash_invocation()    commands.py  (for /slash commands)
            ├─ client.chat.stream_assistant()  core ChatEngine (for regular messages)
            │    └─ LongLivedACPFactory → agent process (stdio)
            │         └─ ChatEvent stream
            ├─ CLIRenderer                 _renderer.py (renders ChatEvent to console)
            └─ PermissionUI                _permission_ui.py (resolves permission events)
```

## Key invariants

**Slash commands are pure data.** `commands.py` parses text into `SlashCommandInvocation` structs and defines `SlashCommandSpec` — it has no I/O, no Rich, no async. The controller interprets and executes them.

**`controller.py` owns REPL orchestration state.** Backend selection, attach mode, session selection, and the approval batch state live on `ChatController`. Chat persistence and turn execution live in core `ChatSessions` / `ChatEngine`.

**Permission policy is event-driven.** `kg chat` has no startup permission bypass flag. ACP permission requests become `PermissionRequest` events; `PermissionUI` resolves them through the inline trust-tier panel and routes the decision back to `ChatEngine.resolve_permission()`. Kagan-owned MCP tools are auto-approved by name.

**`_renderer.py` is transport-agnostic.** It consumes `ChatEvent` objects — it does not know whether events came from ACP, a replay buffer, or a test fixture.

## Adding a new slash command

1. Add a `SlashCommandSpec` to the `SLASH_COMMANDS` list in `commands.py`
1. Add a handler branch in `ChatController._handle_slash_command()` in `controller.py`
1. Add a unit test in `tests/unit/test_chat_commands.py`

## Adding a new ChatEvent variant

1. Add the variant class to `src/kagan/core/chat/events.py`
1. Add it to the `ChatEvent` union type
1. Add a render branch in `CLIRenderer.on_event()` in `_renderer.py`
1. Add a unit test in `tests/unit/test_event_rendering.py`

## Session + Attach Slash Commands

`kagan chat` uses the same target-switching concept as the TUI and web: the
user can talk to the orchestrator, jump into a running worker / reviewer
stream, and detach back to orchestrator mode without leaving the REPL.

- **`/sessions [query]`** lists persisted chat sessions and can reattach the
  REPL to a selected session. Interactive terminals use the searchable picker;
  non-interactive terminals render a static table.
- **`/attach <task-id|session-id>`** parses the argument in `commands.py`
  (`SlashAction.ATTACH_AGENT`), then `controller.py` resolves it via
  `client.resolve_active_session` / the running-agents listing and calls
  `client.attach_chat`.
- **`/detach`** clears the attach (`SlashAction.DETACH_AGENT` →
  `client.attach_chat(..., session_id=None)`).
- **Read-only banner.** While attached, the REPL renders a banner indicating
  the session is being observed read-only; the write path back into the
  attached agent is a follow-up.

## Relation to TUI chat

The TUI chat widget (`src/kagan/tui/widgets/chat.py`) is a **separate implementation** sharing only the `ChatEvent` type from `core/chat/events.py`. It does not use `CLIRenderer` or `ChatController`. Do not add CLI-specific logic to the widget, and do not add TUI-specific logic to `controller.py`.
