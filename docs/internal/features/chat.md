# Chat Behaviors — `kagan.chat`

*Observable behaviors for REPL, slash commands, and orchestrator turns.*
*Each section maps to test coverage in `tests/chat/`.*

______________________________________________________________________

## REPL Entry Points

### `run_chat` — One-shot CLI invocation

**Given** `kagan chat --prompt "Fix the bug"` is called
**When** the command executes
**Then** it creates a temporary ChatController, sends the prompt, streams output, and exits.

**Given** `kagan chat` is called without `--prompt`
**When** the command starts
**Then** it enters an interactive REPL loop that persists session history.

______________________________________________________________________

### `run_chat_async` — Stateful REPL loop

**Given** a project context is active
**When** `run_chat_async()` starts
**Then** it loads the last session for this scope, restores history, and waits for input.

**Given** the user types a message and presses Enter
**When** the message is processed
**Then** it either:

- Executes a slash command (starts with `/`), or
- Sends to the orchestrator agent, streams response, and appends to history.

**Given** the user types `/exit`
**When** the command is processed
**Then** the REPL exits and saves the session.

______________________________________________________________________

## Slash Commands

### `/help` — List available commands

**Given** the user types `/help`
**When** the command executes
**Then** it prints a table of all registered slash commands with descriptions.

______________________________________________________________________

### `/agents` — List and switch agent backends

**Given** the user types `/agents`
**When** the command executes
**Then** it opens agent selection UI (list in REPL, popup in TUI).

**Given** the user types `/agents claude-code`
**When** the command executes
**Then** it switches to `claude-code` for this session and confirms the change.

**Given** the user types `/agents invalid-backend`
**When** the command executes
**Then** it shows an error: "Unknown agent backend: invalid-backend".

______________________________________________________________________

### `/sessions` — Manage chat sessions

**Given** the user types `/sessions`
**When** the command executes
**Then** it lists all stored sessions with index, title, agent backend, and relative time.

**Given** the user types `/sessions 2`
**When** the command executes
**Then** it attaches to session #2, loads history, and continues that conversation.

**Given** the user types `/sessions delete 3`
**When** the command executes
**Then** it deletes session #3 and confirms removal.

**Given** there are more than 30 sessions
**When** a new session is created
**Then** the oldest session is automatically pruned.

______________________________________________________________________

### `/tool` — Inspect tool execution details

**Given** the user types `/tool`
**When** the command executes
**Then** it lists recent tool calls with stable IDs, status, and brief argument preview.

**Given** the user types `/tool t007`
**When** a matching tool call exists
**Then** it shows full input/output details for that tool call in pager mode.

**Given** the user types `/tool unknown`
**When** no tool call matches
**Then** it shows a clear not-found message without crashing the REPL.

______________________________________________________________________

### `/clear` — Clear current session

**Given** the user types `/clear`
**When** the command executes
**Then** it starts a fresh session with empty history, preserving session persistence settings.

______________________________________________________________________

### `/new` — Start a new chat session

**Given** the user types `/new`
**When** the command executes
**Then** it creates a fresh session, discards the current history view, and starts a blank conversation.

______________________________________________________________________

### `/session` — Show current session details

## **Given** the user types `/session` **When** the command executes **Then** it prints the current session’s ID, title, agent backend, message count, and creation time.

### `/exit` — Exit REPL

**Given** the user types `/exit` or `Ctrl+D`
**When** the command executes
**Then** it saves the current session and exits the REPL.

______________________________________________________________________

## Session Persistence

### Session creation

**Given** a new conversation starts
**When** the first message is sent
**Then** a session record is created with a unique ID, empty history, and default title.

**Given** the first agent response completes
**When** the session is saved
**Then** the orchestrator is asked to generate a short title from the exchange.

______________________________________________________________________

### Session storage limits

**Given** a session has >300 messages
**When** the session is saved
**Then** only the most recent 300 messages are kept.

**Given** there are >30 sessions in storage
**When** a new session is created
**Then** the oldest session is deleted to stay within the limit.

**Given** the prompt-toolkit history file has >120 lines
**When** a new line is added
**Then** the oldest lines are truncated.

______________________________________________________________________

### Title generation

**Given** an LLM generates a title with reasoning tags (e.g., `<think>...</think>`)
**When** `_clean_generated_title()` processes it
**Then** reasoning tags, quotes, and newlines are stripped, returning a clean one-line title.

**Given** the generated title is empty after cleaning
**When** the session is saved
**Then** a fallback title "New conversation" is used.

______________________________________________________________________

## Orchestrator Turn

### ACP handshake

**Given** an orchestrator turn starts
**When** `run_orchestrator_turn()` is called
**Then** it spawns the agent process, performs ACP handshake (`initialize` → `session/new`), and sends the user prompt.

______________________________________________________________________

### Streaming output

**Given** the agent sends `AgentMessageChunk` events
**When** `_OrchestratorACPClient` receives them
**Then** the chunks are printed to Rich console with streaming animation.

______________________________________________________________________

### Tool call rendering

**Given** the agent sends `ToolCallStart`
**When** `_OrchestratorACPClient` receives it
**Then** it prints the tool name and arguments.

**Given** the agent sends `ToolCallProgress` updates
**When** `_OrchestratorACPClient` receives them
**Then** it updates the status indicator (pending ✓/✗).

______________________________________________________________________

### Turn completion

**Given** the agent sends `session/end` notification
**When** the orchestrator turn completes
**Then** the response is finalized, history is updated, and the session is saved.

______________________________________________________________________

## Error Handling

### Agent spawn failure

**Given** the selected agent backend executable is not on PATH
**When** `run_orchestrator_turn()` tries to spawn it
**Then** it shows an error: "Agent backend 'foo' not found. Install it or select another with /agents."

______________________________________________________________________

### ACP connection failure

**Given** the agent process exits during handshake
**When** ACP handshake fails
**Then** it shows an error with the agent's stderr output and terminates the turn.

______________________________________________________________________

### Unknown slash command

**Given** the user types `/unknowncommand`
**When** the command is parsed
**Then** it shows: "Unknown command: /unknowncommand (type /help for list)".

______________________________________________________________________

## Scope Modes

### Task-scoped chat

**Given** `--session-id abc123` is passed
**When** the REPL starts
**Then** it binds to that task session, loading task context into the orchestrator prompt.

**Given** task-scoped chat is active
**When** the user sends a message
**Then** the orchestrator has access to task state, worktree diff, and recent events.

______________________________________________________________________

### Global orchestrator

**Given** no `--session-id` is passed
**When** the REPL starts
**Then** it uses project-level session storage and a global orchestrator prompt.

**Given** global orchestrator mode
**When** the user sends a message
**Then** the orchestrator has access to all project tasks via MCP tools.

______________________________________________________________________

## Integration with TUI

### ChatPanel widget

**Given** the TUI opens a ChatPanel
**When** it mounts
**Then** it creates a `ChatController` and binds to the current scope.

**Given** the user types in the ChatPanel input
**When** they press Enter
**Then** the message is processed by `ChatController.process_input()` and rendered in the panel.

**Given** the agent streams output
**When** chunks arrive via ACP
**Then** they're rendered in real-time in the ChatPanel output area.

______________________________________________________________________

## Test Coverage

| File                              | Tests                               |
| --------------------------------- | ----------------------------------- |
| `tests/chat/test_repl.py`         | REPL entry points, loop behavior    |
| `tests/chat/test_commands.py`     | Slash command parsing and execution |
| `tests/chat/test_sessions.py`     | Session CRUD, persistence limits    |
| `tests/chat/test_orchestrator.py` | ACP handshake, streaming, errors    |

**All tests use mocked ACP connections.** Real agent spawn is integration-level.
