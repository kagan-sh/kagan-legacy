# CLI Chat Architecture

The `src/kagan/cli/chat/` module implements the chat REPL, the orchestrator chat controller, and the ACP streaming layer. It is one of the more complex subsystems — this document maps the call flow.

## File map

| File                 | Role                                                                                                        |
| -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `commands.py`        | Slash command parsing (`/help`, `/mode`, `/backend`, `/clear`, etc.) — pure data, no I/O                    |
| `controller.py`      | `ChatController` — stateful chat session: ties together commands, streaming, ACP, and the approval batch UI |
| `acp.py`             | ACP client helpers: orchestrator warmup, turn execution, permission handling                                |
| `_streaming.py`      | `StreamRenderer` — converts `ChatEvent` stream into Rich console output (TUI-free path)                     |
| `_renderer.py`       | Lower-level rendering helpers used by `_streaming.py`                                                       |
| `_approval_batch.py` | Batch approval UI for multi-task orchestrator runs                                                          |
| `_approval_panel.py` | Single-task approval panel widget                                                                           |
| `_permission_ui.py`  | Interactive permission prompts (ACP `RequestPermission` events)                                             |
| `_chat_ui.py`        | Rich `Live` layout for the REPL session frame                                                               |
| `_signals.py`        | Internal signal types (e.g. `AbortSignal`) passed between layers                                            |
| `_handshake.py`      | ACP handshake protocol helpers                                                                              |
| `_session_picker.py` | Interactive session selection (attach to existing sessions)                                                 |
| `_title.py`          | Dynamic title bar for the REPL                                                                              |
| `_theme.py`          | Rich theme constants for chat output                                                                        |
| `_completion.py`     | Input completion helpers                                                                                    |
| `agents.py`          | Agent listing/resolution helpers (`/backend` command support)                                               |
| `prompt.py`          | Input normalization utilities                                                                               |
| `__init__.py`        | Public surface: `run_chat_session()` entrypoint                                                             |

## Call flow

```
CLI entrypoint (src/kagan/cli/)
  └─ run_chat_session()            __init__.py
       └─ ChatController           controller.py
            ├─ parse_slash_invocation()    commands.py  (for /slash commands)
            ├─ execute_turn()              acp.py       (for regular messages)
            │    └─ ACP client → agent process (stdio)
            │         └─ AgentMessageChunk stream
            │              └─ ChatEvent stream
            └─ StreamRenderer             _streaming.py (renders ChatEvent to console)
                 └─ _renderer.py          (Rich markup helpers)
```

## Key invariants

**Slash commands are pure data.** `commands.py` parses text into `SlashCommandInvocation` structs and defines `SlashCommandSpec` — it has no I/O, no Rich, no async. The controller interprets and executes them.

**`controller.py` owns all state.** Mode (auto/pair), backend selection, session history, and the approval batch state all live on `ChatController`. Never add mutable state to `_streaming.py` or `acp.py`.

**`acp.py` owns the subprocess.** The ACP agent process is spawned and managed here. It communicates over stdio. All permission and approval handshakes are handled inside `acp.py` and `_permission_ui.py` before the controller sees the result.

**`_streaming.py` is transport-agnostic.** It consumes a `AsyncIterator[ChatEvent]` — it does not know whether events came from ACP, a replay buffer, or a test fixture.

## Adding a new slash command

1. Add a `SlashCommandSpec` to the `SLASH_COMMANDS` list in `commands.py`
1. Add a handler branch in `ChatController._handle_slash_command()` in `controller.py`
1. Add a unit test in `tests/unit/test_chat_commands.py`

## Adding a new ChatEvent variant

1. Add the variant class to `src/kagan/core/chat/events.py`
1. Add it to the `ChatEvent` union type
1. Add a render branch in `StreamRenderer._render_event()` in `_streaming.py`
1. Add a unit test in `tests/unit/test_event_rendering.py`

## Relation to TUI chat

The TUI chat widget (`src/kagan/tui/widgets/chat.py`) is a **separate implementation** sharing only the `ChatEvent` type from `core/chat/events.py`. It does not use `StreamRenderer` or `ChatController`. Do not add CLI-specific logic to the widget, and do not add TUI-specific logic to `controller.py`.
