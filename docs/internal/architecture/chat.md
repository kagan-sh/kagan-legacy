# Chat Architecture — `kagan.cli.chat`

*Conversational layer over core: REPL, slash commands, session persistence, ACP streaming.*

______________________________________________________________________

## References

| Package            | Repo                                                                                            | Use                                                              |
| ------------------ | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **ACP SDK**        | [anthropics/agent-client-protocol](https://github.com/anthropics/agent-client-protocol)         | Streaming agent output, tool calls, bidirectional communication. |
| **Prompt Toolkit** | [prompt-toolkit/python-prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) | REPL input with history, completion, editing.                    |
| **Rich**           | [Textualize/rich](https://github.com/Textualize/rich)                                           | Console output, markdown rendering, syntax highlighting.         |
| **Loguru**         | [Delgan/loguru](https://github.com/Delgan/loguru)                                               | Structured logging (config in core).                             |

______________________________________________________________________

## Context

`kagan.cli.chat` provides conversational abstractions over `kagan.core`:

1. **REPL** — interactive terminal chat with an orchestrator agent
1. **Slash commands** — structured actions (`/agents`, `/sessions`, `/help`)
1. **Session persistence** — conversation history in core `ChatSessions`
1. **Orchestrator turns** — `ChatEngine` streams ACP-backed events

**Dependency direction:**

```text
kagan.cli.chat ──► kagan.core   (agent spawning, events, tasks)
kagan.tui  ──► kagan.cli.chat   (slash parsing, backend helpers, ACP turn helpers)
kagan.cli  ──► kagan.cli.chat   (run_chat for REPL)
kagan.core ──✘► kagan.cli.chat  NEVER
```

______________________________________________________________________

## Package Layout

```text
src/kagan/cli/chat/
├── __init__.py        # Public API exports
├── _approval_batch.py # Batched approval state
├── _approval_panel.py # Rich approval panel rendering
├── _chat_ui.py        # Shared chat prompt/status UI helpers
├── _approval_types.py # Shared approval/session-decision types (PermissionUI + batch panel)
├── _utils.py          # Shared helpers (e.g. fuzzy_match for slash completion)
├── _handshake.py      # Agent handshake/preflight helpers
├── _permission_ui.py  # Permission prompt interactions (trust-tier approval panel)
├── _renderer.py       # ACP event renderer and tool call display
├── _session_picker.py # Interactive session picker
├── _signals.py        # Signal handling helpers
├── _streaming.py      # Immediate Markdown streaming region
├── _theme.py          # Chat colors and glyphs
├── _title.py          # Session title generation
├── controller.py      # ChatController over core ChatEngine
├── acp.py             # run_orchestrator_turn, ACP bridge
├── agents.py          # Agent backend selection
├── commands.py        # SlashCommandSpec, SlashCommandRegistry
├── repl.py            # run_chat, run_chat_async
└── tool_runs.py       # Tool execution tracking
```

______________________________________________________________________

## Core Components

### ChatController

Main orchestrator for REPL interaction:

- Manages the REPL lifecycle around core `ChatEngine`
- Processes user input (text or slash commands)
- Streams agent output to the Rich console as chunks arrive
- Maintains conversation state
- Dispatches permission requests to `PermissionUI`

| Method                                            | Description                      |
| ------------------------------------------------- | -------------------------------- |
| `run(prompt=None)`                                | Main orchestrator lifecycle loop |
| `hydrate_persistent_session(explicit_session_id)` | Load or create session           |

### SlashCommandRegistry

Declarative slash command registration:

```python
@dataclass(frozen=True, slots=True)
class SlashCommandSpec:
    name: str
    description: str
    orchestrator_only: bool = False
```

| Command     | Description                                   |
| ----------- | --------------------------------------------- |
| `/help`     | List available commands                       |
| `/agents`   | List and switch agent backends                |
| `/sessions` | List, attach, or delete chat sessions         |
| `/tool`     | Inspect recent tool calls by ID               |
| `/clear`    | Clear the current session                     |
| `/new`      | Start a new chat session                      |
| `/session`  | Show current session details                  |
| `/status`   | Show current project, session, and agent      |
| `/project`  | Show or switch active project                 |
| `/delete`   | Delete a chat session by number or ID         |
| `/flow`     | Show guided Plan → Execute → Orchestrate flow |
| `/exit`     | Exit the REPL                                 |

Aliases: `q→exit`, `?→help`, `s→sessions`, `a→agents`, `f→flow`, `p→project`.

### Session Persistence

Sessions are rows managed by `client.chat_sessions`:

- `MAX_STORED_SESSIONS = 30` — oldest pruned on save
- `MAX_STORED_MESSAGES = 300` — truncated to recent N
- `MAX_STORED_HISTORY = 120` — prompt-toolkit history lines

**Title generation** (`_title.py`): After first exchange, a lightweight ACP turn (no MCP, 30s timeout) generates the title. `_clean_generated_title()` strips reasoning tags, quotes, truncates to 80 chars.

### REPL (`repl.py`)

Interactive terminal interface:

- **Input:** `prompt_toolkit` with history, multiline editing
- **Output:** `Rich.Console` with markdown, syntax highlighting
- **Entry points:** `run_chat()` (one-shot), `run_chat_async()` (interactive loop)

______________________________________________________________________

## Orchestrator Turn Flow

```text
User input
   │
   ▼
ChatController.process_input()
   │
   ├─ slash command? → SlashCommandRegistry → execute handler
   │
   └─ text message
       │
       ▼
   client.chat.stream_assistant()
       │
       ├─ ChatEngine.push_user() ───────► persist user message
       ├─ LongLivedACPFactory ──────────► STDIO handshake/session
       ├─ prompt(...) ──────────────────► send message
       └─ stream loop
          ├─ AssistantChunk ────► CLIRenderer ─────────► MarkdownStreamingRegion
          ├─ ToolCallStart ──────► grouped tool status line
          ├─ ToolCallProgress ───► minimal live state label
          ├─ PermissionRequest ──► PermissionUI ───────► ChatEngine.resolve_permission()
          └─ session/end ────────► finalize
```

### ACP Integration

- `LongLivedACPFactory` — core-owned ACP session factory used by `ChatEngine`
- `_CaptureACPClient` — silent variant for title generation and helper turns
- `warm_orchestrator_backend()` — pre-warms agent to reduce latency
- `CLIRenderer` — converts chat events into console output, tool records, and toolbar state
- `MarkdownStreamingRegion` — writes text fragments immediately, flushes after streamed words, and keeps the final accumulated text available for session history
- Tool calls rendered with compact live indicators for thinking, commands, reads, searches, images, and generic tool activity

**Lightweight mode** (`run_orchestrator_turn(lightweight=True)`): No MCP server, no system prompt, sends prompt as-is for simple completions.

### Permission Flow

`kg chat` does not expose a startup bypass such as `--yolo`. Tool permission
requests are resolved per request through the inline approval panel:

- approve once
- approve tool for session
- allow all for session
- deny
- deny with feedback

The session trust choices are stored in the CLI permission cache for the life of
the REPL process. Kagan-owned MCP tools (`mcp__kagan*`) are auto-approved.

______________________________________________________________________

## Orchestrator System Prompt

Resolved via `resolve_orchestrator_prompt(settings, project_path)`:

1. **Dotfile override** — `.kagan/prompts/orchestrator.md` replaces default
1. **Code default** — `DEFAULT_ORCHESTRATOR_PROMPT` in `core/_prompts`
1. **Behavioral clauses** — compiled from settings (execution mode, review strictness, etc.)
1. **Additional instructions** — `additional_instructions` appended as `## Additional Instructions`

______________________________________________________________________

## Session Scoping

| Scope                | Settings Key                    |
| -------------------- | ------------------------------- |
| Task-scoped          | `chat_scope_state_{session_id}` |
| Project orchestrator | `chat_last_session_{scope}`     |

### Cross-Surface Visibility

All surfaces (CLI, TUI, web) share one session store. The `source` field (`"repl"`, `"tui-orchestrator"`, `"web"`) is creation metadata — every surface sees every session.

______________________________________________________________________

## Testing

- Mock ACP connection, not core
- Use `run_chat()` with fixed prompt for deterministic output
- Slash command handlers are pure functions — test directly
- Session persistence: use real `ChatSessions` storage in isolated test DBs

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted                   | Why                                          |
| ------------------------- | -------------------------------------------- |
| Separate chat database    | Chat sessions are core `ChatSession` rows    |
| SSE / HTTP transport      | REPL is local; STDIO + ACP is sufficient     |
| Message class hierarchy   | Messages are dicts (role, content)           |
| Multi-turn context window | Orchestrator manages context via ACP session |
