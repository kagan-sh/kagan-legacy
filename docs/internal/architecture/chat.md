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
1. **Session persistence** — conversation history in core settings
1. **Orchestrator turns** — ACP-based streaming execution

**Dependency direction:**

```text
kagan.cli.chat ──► kagan.core   (agent spawning, events, tasks)
kagan.tui  ──► kagan.cli.chat   (ChatController, slash commands)
kagan.cli  ──► kagan.cli.chat   (run_chat for REPL)
kagan.core ──✘► kagan.cli.chat  NEVER
```

______________________________________________________________________

## Package Layout

```text
src/kagan/cli/chat/
├── __init__.py        # Public API exports
├── _completion.py     # Slash command completion
├── _title.py          # Session title generation
├── controller.py      # ChatController, _OrchestratorACPClient
├── acp.py             # run_orchestrator_turn, ACP bridge
├── agents.py          # Agent backend selection
├── commands.py        # SlashCommandSpec, SlashCommandRegistry
├── prompt.py          # Orchestrator system prompt
├── repl.py            # run_chat, run_chat_async
├── sessions.py        # Session CRUD, persistence
└── tool_runs.py       # Tool execution tracking
```

______________________________________________________________________

## Core Components

### ChatController

Main orchestrator for REPL interaction:

- Manages orchestrator agent lifecycle via ACP
- Processes user input (text or slash commands)
- Streams agent output to Rich console
- Maintains conversation state

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

Sessions stored in `client.settings` under `chat_sessions_v1`:

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
   run_orchestrator_turn()
       │
       ├─ build_orchestrator_prompt() ──► system + context
       ├─ acp.connect_to_agent() ───────► STDIO handshake
       ├─ prompt(session/new) ──────────► send message
       └─ stream loop
           ├─ AgentMessageChunk ──► Rich console
           ├─ ToolCallStart ──────► print tool name
           ├─ ToolCallProgress ───► update status
           └─ session/end ────────► finalize
```

### ACP Integration

- `_OrchestratorACPClient` — implements `ACPClientBase`
- `_CaptureACPClient` — silent variant for title generation
- `warm_orchestrator_backend()` — pre-warms agent to reduce latency
- Tool calls rendered with status indicators (pending ✓/✗)

**Lightweight mode** (`run_orchestrator_turn(lightweight=True)`): No MCP server, no system prompt, sends prompt as-is for simple completions.

______________________________________________________________________

## Orchestrator System Prompt

Resolved via `resolve_orchestrator_prompt(settings, project_path)`:

1. **Dotfile override** — `.kagan/prompts/orchestrator.md` replaces default
1. **Code default** — `DEFAULT_ORCHESTRATOR_PROMPT` in `core/_prompts.py`
1. **Behavioral clauses** — compiled from settings (execution mode, review strictness, etc.)
1. **Additional instructions** — `additional_instructions` appended as `## Additional Instructions`

______________________________________________________________________

## Session Scoping

| Scope                | Settings Key                    |
| -------------------- | ------------------------------- |
| Task-scoped          | `chat_scope_state_{session_id}` |
| Project orchestrator | `chat_sessions_v1`              |

### Cross-Surface Visibility

All surfaces (CLI, TUI, web) share one session store. The `source` field (`"repl"`, `"tui-orchestrator"`, `"web"`) is creation metadata — every surface sees every session.

______________________________________________________________________

## Testing

- Mock ACP connection, not core
- Use `run_chat()` with fixed prompt for deterministic output
- Slash command handlers are pure functions — test directly
- Session persistence: use in-memory settings, not real DB

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted                   | Why                                                     |
| ------------------------- | ------------------------------------------------------- |
| Separate chat database    | Sessions in core `settings` table — one source of truth |
| SSE / HTTP transport      | REPL is local; STDIO + ACP is sufficient                |
| ChatSession domain model  | Session is a dict in settings, not an entity            |
| Message class hierarchy   | Messages are dicts (role, content)                      |
| Multi-turn context window | Orchestrator manages context via ACP session            |
