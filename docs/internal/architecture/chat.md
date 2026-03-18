# Chat Architecture — `kagan.chat`

*Design principles: conversational layer over core, slash commands, session persistence.*

______________________________________________________________________

## References

| Package            | Repo                                                                                            | Use                                                                                                     |
| ------------------ | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **ACP SDK**        | [anthropics/agent-client-protocol](https://github.com/anthropics/agent-client-protocol)         | Agent Client Protocol: streaming agent output, tool calls, bidirectional communication.                 |
| **Prompt Toolkit** | [prompt-toolkit/python-prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) | REPL input with history, completion, editing.                                                           |
| **Rich**           | [Textualize/rich](https://github.com/Textualize/rich)                                           | Console output formatting, markdown rendering, syntax highlighting.                                     |
| **Loguru**         | [Delgan/loguru](https://github.com/Delgan/loguru)                                               | Structured logging. Config and sink setup in core — see `docs/internal/architecture/core.md` § Logging. |

______________________________________________________________________

## Context

`kagan.chat` provides conversational abstractions over `kagan.core`. It implements:

1. **REPL (Read-Eval-Print Loop)** — interactive terminal chat with an orchestrator agent
1. **Slash commands** — structured actions (`/agents`, `/sessions`, `/help`) within chat
1. **Session persistence** — conversation history stored in core settings, survives restart
1. **Orchestrator turns** — ACP-based agent execution for multi-step workflows

**Core does not know about chat.** The dependency direction is strictly one-way:

```text
kagan.chat ──► kagan.core   (agent spawning, event streaming, task ops)
kagan.tui  ──► kagan.chat   (ChatController, slash commands)
kagan.cli  ──► kagan.chat   (run_chat for REPL)
kagan.core ──✘► kagan.chat  NEVER
```

______________________________________________________________________

## Design Principles

1. **Chat is a frontend over core** — it uses the same async API that TUI/CLI use
1. **Sessions persist in core settings** — `client.settings` stores chat history, no separate DB
1. **Slash commands are declarative** — `SlashCommandSpec` + handler function
1. **One orchestrator agent per scope** — project-level orchestrator has its own session store
1. **ACP for streaming** — orchestrator turns use ACP over STDIO for bidirectional streaming

______________________________________________________________________

## Package Layout

```text
src/kagan/chat/
├── __init__.py        # re-exports public API
├── _completion.py     # fuzzy_match helper for slash command completion
├── _title.py          # session title generation (lightweight ACP turn)
├── controller.py      # ChatController, _OrchestratorACPClient
├── acp.py             # run_orchestrator_turn, ACP bridge utilities
├── agents.py          # agent backend selection, formatting utilities
├── commands.py        # SlashCommandSpec, SlashCommandRegistry, parsing
├── prompt.py          # orchestrator system prompt, request formatting
├── repl.py            # run_chat, run_chat_async, console setup
├── sessions.py        # session CRUD, history normalization, persistence
└── tool_runs.py       # ToolRunTracker for tracking tool execution during orchestrator turns
```

**11 files.** Flat, no sub-packages.

## Core Components

### ChatController

`ChatController` is the main orchestrator for REPL interaction. It:

- Manages the orchestrator agent lifecycle via ACP
- Processes user input (text or slash commands)
- Streams agent output to Rich console
- Maintains conversation state for the current session

#### Public API

| Method                                            | Description                      |
| ------------------------------------------------- | -------------------------------- |
| `run(prompt=None)`                                | Main orchestrator lifecycle loop |
| `hydrate_persistent_session(explicit_session_id)` | Load or create session           |

**Internal methods:** `_send(text)`, `_repl_loop()`, `_event_watcher()`, `_handle_slash(text)`, `_switch_agent(new_backend)`, `_open_sessions(query)`, `_create_new_session()`, `_persist_session()`

Note: `process_input()`, `run_orchestrator_turn()`, and `close()` do not exist as public methods.

### SlashCommandRegistry

Slash commands are declaratively registered:

```python
@dataclass(frozen=True, slots=True)
class SlashCommandSpec:
    name: str
    description: str
    orchestrator_only: bool = False


@dataclass(frozen=True, slots=True)
class SlashCommand:
    spec: SlashCommandSpec
    handler: Callable[[SlashCommandInvocation, _SlashCommandContext], SlashCommandOutcome]
```

#### Built-in commands

| Command     | Description                                                       |
| ----------- | ----------------------------------------------------------------- |
| `/help`     | List available commands                                           |
| `/agents`   | List and switch agent backends                                    |
| `/sessions` | List, attach, or delete chat sessions                             |
| `/tool`     | Inspect recent tool calls and full I/O by ID                      |
| `/clear`    | Clear the current session (start fresh)                           |
| `/new`      | Start a new chat session                                          |
| `/session`  | Show current session details                                      |
| `/flow`     | Show guided Plan → Execute → Orchestrate flow (orchestrator-only) |
| `/exit`     | Exit the REPL                                                     |

### Session Persistence

Chat sessions are stored in `client.settings` under the key `chat_sessions_v1`.

#### Key helpers from `sessions.py`

| Function                                                         | Description                                  |
| ---------------------------------------------------------------- | -------------------------------------------- |
| `create_chat_session(...)`                                       | Create a new session record                  |
| `get_chat_session(key)`                                          | Retrieve a session by ID                     |
| `list_chat_sessions()`                                           | List all sessions with metadata              |
| `save_chat_session(...)`                                         | Persist session with messages and title      |
| `delete_chat_session(key)`                                       | Remove a session                             |
| `set_last_session_id(...)`                                       | Remember last active session per scope       |
| `get_last_session_id(client, *, scope)`                          | Read last active session ID for a scope      |
| `get_scope_state(client, *, scope)`                              | Load full scope state dict from settings     |
| `save_scope_state(client, *, scope, state)`                      | Persist scope state dict to settings         |
| `resolve_task_session_binding(client, session_id)`               | Resolve task binding for a given session ID  |
| `list_chat_session_items(client, *, source, current_session_id)` | Build display list of sessions for a scope   |
| `resolve_chat_session_selector(items, query)`                    | Match a query string to a session list item  |
| `resolve_chat_session_id(items, query)`                          | Resolve query to a session ID                |
| `build_chat_session_list_items(sessions, *, current_session_id)` | Convert raw session records to display items |

#### Constants

| Name                        | Value / Purpose                              |
| --------------------------- | -------------------------------------------- |
| `CHAT_SESSIONS_SETTING_KEY` | Settings key for session storage             |
| `CHAT_SCOPE_PREFIX`         | Prefix for scope-keyed settings entries      |
| `CHAT_LAST_SESSION_PREFIX`  | Prefix for last-session-id entries per scope |
| `_SESSION_TITLE_MAX_LENGTH` | `80` — max characters for a generated title  |

#### Normalization

- `MAX_STORED_SESSIONS = 30` — oldest sessions pruned on save
- `MAX_STORED_MESSAGES = 300` — messages truncated to recent N
- `MAX_STORED_HISTORY = 120` — prompt-toolkit history lines

Title generation (`_title.py`): after the first exchange a background
task calls `generate_session_title()`, which runs a **lightweight ACP
turn** — no MCP tools, no orchestrator system prompt, 30 s timeout.
The agent receives only the title-generation prompt and the first
user/assistant exchange, keeping the call fast and focused. On success
the title is persisted; on failure (timeout or any error) the default
placeholder title is kept. `_clean_generated_title()` strips reasoning
tags (DeepSeek `<think>`), surrounding quotes, and newlines, truncating
to 80 characters.

### REPL (`repl.py`)

The REPL provides the interactive terminal interface:

- **Input:** `prompt_toolkit` session with history, multiline editing
- **Output:** `Rich.Console` with markdown rendering, syntax highlighting
- **Loop:** reads line → `ChatController.process_input()` → render response

#### Entry points

| Function           | Description                                           |
| ------------------ | ----------------------------------------------------- |
| `run_chat()`       | One-shot REPL call (used by `kagan chat --prompt`)    |
| `run_chat_async()` | Stateful REPL loop (used by interactive `kagan chat`) |

#### Scope modes

- **Project-scoped** — `--session-id` binds to a specific task session
- **Global orchestrator** — no session binding, uses project-level settings

### Agent Backend Selection (`agents.py`)

Helper functions for resolving which agent backend to use:

| Function                            | Description                             |
| ----------------------------------- | --------------------------------------- |
| `resolve_default_agent_backend()`   | Read from settings or environment       |
| `resolve_agent_backend_selection()` | Parse `/agents` argument or prompt user |
| `list_registered_agent_backends()`  | All backends from core registry         |
| `format_agent_backend_list()`       | Render list for REPL output             |

______________________________________________________________________

## Orchestrator Turn Flow

```text
User types "implement auth"
   │
   ▼
ChatController.process_input()
   │
   ├─ slash command? → SlashCommandRegistry.resolve() → execute handler
   │
   └─ text message
       │
       ▼
   run_orchestrator_turn()
       │
       ├─ build_orchestrator_prompt() ──► system + context + request
       │
       ├─ acp.connect_to_agent() ──────► STDIO handshake
       │
       ├─ prompt(session/new) ─────────► send user message
       │
       └─ stream loop
           │
           ├─ on AgentMessageChunk ──► print to Rich console
           ├─ on ToolCallStart ──────► print tool name/args
           ├─ on ToolCallProgress ───► update tool status
           └─ on session/end ────────► finalize response
```

### ACP integration

- Uses `agent-client-protocol` SDK for bidirectional streaming
- `_OrchestratorACPClient` (in `controller.py`) implements `ACPClientBase`
- `_CaptureACPClient` — ACP client variant that captures output instead of printing (used for title generation and other silent turns)
- `OrchestratorWarmupState` — dataclass holding pre-warmed ACP connection state
- `warm_orchestrator_backend()` — pre-warms the agent process before the first user message to reduce perceived latency
- `_acp_handshake_timeout_seconds()` — resolves the handshake timeout from settings or environment
- `_friendly_acp_error_message()` — formats ACP errors into human-readable REPL output
- Streams to `Rich.Console` with live updates
- Tool calls rendered with status indicators (pending ✓/✗)

**Lightweight mode** (`run_orchestrator_turn(lightweight=True)`):

- Skips MCP server creation (no `.mcp.json`, no tools exposed)
- Skips orchestrator system prompt and "User request:" wrapper
- Sends the prompt as-is for simple completions (title generation)
- Same ACP handshake and agent spawn, just a bare session

______________________________________________________________________

## Orchestrator System Prompt

The orchestrator prompt is resolved via `resolve_orchestrator_prompt(settings, project_path)`:

1. **Dotfile override** — if `.kagan/prompts/orchestrator.md` exists, it fully replaces the default
1. **Code default** — `DEFAULT_ORCHESTRATOR_PROMPT` in `core/_prompts.py`
1. **Behavioral clauses** — compiled from settings (execution mode, review strictness, planning depth, auto-confirm)
1. **Additional instructions** — `additional_instructions` setting appended as `## Additional Instructions`

See `core/_prompts.py` for the three-layer resolution pipeline.

______________________________________________________________________

## Session Scoping

Chat sessions can be scoped to:

- **Task session** — `--session-id {id}` binds chat to a task run
- **Project orchestrator** — no binding, shared across project

The session ID determines which `client.settings` key is used:

- Task-scoped: `chat_scope_state_{session_id}`
- Global: `chat_sessions_v1`

### Cross-Surface Session Visibility

All surfaces (CLI chat, TUI, web) share a single session store. Sessions are
tagged with a `source` field on creation (`"repl"`, `"tui-orchestrator"`,
`"web"`) but listing is **unfiltered** — every surface sees every session.

- `source` is **creation metadata**, not a partition key
- A session created in web appears in CLI `/sessions` and TUI session picker
- Resuming a session from a different surface preserves the original `source`
- The `source` field is useful for display (badge/icon showing origin)

**Session list command:** `/sessions` queries all sessions and shows:

```text
 1. "Fix login bug" (claude-code, 2h ago) ◀ current
 2. "Refactor API" (gemini-cli, yesterday)
 3. "Add tests" (claude-code, 3d ago)
```

User can attach: `/sessions 2` or delete: `/sessions delete 3`.

______________________________________________________________________

## Integration with TUI and CLI

| Frontend | How it uses chat                                     |
| -------- | ---------------------------------------------------- |
| **TUI**  | `ChatPanel` widget holds a `ChatController`          |
| **CLI**  | `kagan chat` calls `run_chat()` / `run_chat_async()` |

Both import from `kagan.chat.__init__`:

- `ChatController` — orchestrator lifecycle
- `run_chat`, `run_chat_async` — REPL entry points
- `SlashCommandRegistry` — for potential TUI slash commands
- Session CRUD helpers — for session management UI

______________________________________________________________________

## Testing

See `docs/internal/testing.md` for the full testing guide.

Chat-specific:

- Mock the ACP connection, not core
- Use `run_chat()` with a fixed prompt for deterministic output
- Slash commands are pure functions — test handlers directly
- Session persistence: use in-memory settings, not real DB

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted                    | Why                                                             |
| -------------------------- | --------------------------------------------------------------- |
| Separate chat database     | Sessions persist in core `settings` table — one source of truth |
| SSE / HTTP transport | REPL is local only. STDIO + ACP is sufficient.                  |
| ChatSession domain model   | Session is just a dict in settings, not an entity               |
| Message class hierarchy    | Messages are dicts (role, content). No validation needed.       |
| Multi-turn context window  | Orchestrator manages context via ACP session, not chat module   |
