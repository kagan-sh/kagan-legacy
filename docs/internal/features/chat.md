# Chat Behaviors — `kagan.cli.chat`

*Observable behaviors for REPL, slash commands, and orchestrator turns.*
*Each section maps to test coverage in `tests/unit/test_chat_*` and `tests/tui/test_chat_*`.*

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
**Then** it starts a fresh session by default and waits for input.

**Given** the user wants to continue an earlier conversation
**When** they use `/sessions` or pass `--session-id`
**Then** Kagan restores that explicit session and continues from its saved history.

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

### `/flow` — Guided Plan → Execute → Orchestrate flow

**Given** the user types `/flow`
**When** the command executes
**Then** it displays a guided walkthrough of the Plan → Execute → Orchestrate workflow steps.

**Given** `/flow` is invoked outside an orchestrator context
**When** the command is parsed
**Then** it is rejected with a message indicating it is only available in orchestrator mode.

______________________________________________________________________

### `/status` — Show current project, session, and agent

**Given** the user types `/status`
**When** the command executes
**Then** it prints the current project, active session, and agent backend info.

______________________________________________________________________

### `/project` — Show or switch active project

**Given** the user types `/project`
**When** the command executes
**Then** it shows the current project name and path.

**Given** the user types `/project <name>`
**When** the command executes
**Then** it switches to the named project if it exists.

______________________________________________________________________

### `/delete` — Delete a chat session

**Given** the user types `/delete <number|id>`
**When** the command executes and the session exists
**Then** it deletes the specified session and confirms removal.

**Given** the user types `/delete` with no argument
**When** the command is parsed
**Then** it shows usage guidance.

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

**Given** the user types `/session`
**When** the command executes
**Then** it prints the current session's ID, title, agent backend, message count, and creation time.

### `/attach` and `/detach` — Switch chat target

See [Attach + Detach](#attach--detach) below for full behaviours. In short:

- `/attach <task-id|session-id>` — attach to a running worker or reviewer
  session (full UUID or 8-char prefix; matches by session id or task id).
- `/detach` — return to orchestrator mode.

______________________________________________________________________

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

**Given** the first agent response completes in any surface (REPL, web, TUI)
**When** the session still has a default title
**Then** a background task calls `generate_session_title()` which runs a lightweight ACP turn — no MCP tools, no orchestrator system prompt — so the agent focuses purely on producing a title.

**Given** title generation succeeds
**When** the session is saved
**Then** the title is persisted and, on web, a `CHAT_SESSION_UPDATED` SSE event updates the UI.

**Given** title generation times out (30 s) or fails
**When** the error is caught
**Then** the default title is kept and the failure is logged at debug level. Title generation never blocks the chat flow.

**Given** an LLM generates a title with reasoning tags (e.g., `<think>...</think>`)
**When** `_clean_generated_title()` processes it
**Then** reasoning tags, quotes, and newlines are stripped, returning a clean one-line title (max 80 characters).

**Given** the generated title is empty after cleaning
**When** the session is saved
**Then** the default placeholder title is kept.

______________________________________________________________________

## Orchestrator Turn

### ACP handshake

**Given** an orchestrator turn starts
**When** `run_orchestrator_turn()` is called
**Then** it spawns the agent process, performs ACP handshake (`initialize` → `session/new`), and sends the user prompt.

**Given** `run_orchestrator_turn(lightweight=True)` is called (e.g. for title generation)
**When** the ACP session is created
**Then** no MCP servers are attached and the prompt is sent without the orchestrator system prompt or "User request:" wrapper.

______________________________________________________________________

### Streaming output

**Given** the agent sends `AgentMessageChunk` events
**When** `_OrchestratorACPClient` receives them
**Then** each chunk is printed to the Rich console immediately with streaming animation, and turn finalization closes the live line without replaying the response.

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
**Then** if ACP usage data is available, a compact metrics line is displayed: context window usage and cumulative cost (e.g., `ctx 45k/200k · $0.12`).

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

## Background Event Notifications

### Task agent lifecycle events

**Given** the REPL is running
**When** a task agent completes or fails (in any surface)
**Then** a one-line notification is printed to the console immediately.

**Given** the REPL exits
**When** the event watcher is running
**Then** the watcher is cancelled cleanly without error output.

**Given** the event stream encounters an unexpected error
**When** the watcher stops
**Then** the failure is logged at warning level. The REPL continues operating.

______________________________________________________________________

## Cross-Surface Session Visibility

### All sessions visible everywhere

**Given** a session was created in the web dashboard
**When** the user types `/sessions` in CLI chat
**Then** the web session appears in the list and can be resumed.

**Given** a session was created in TUI
**When** the user opens sessions in web or CLI
**Then** the TUI session appears and can be resumed.

**Given** a user resumes a session from a different surface
**When** the session loads
**Then** the original `source` tag is preserved (not overwritten).

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

## Attach + Detach

### `/attach <task-id|session-id>`

**Given** there is at least one running worker or reviewer session in the
active project
**When** the user types `/attach <id>` (full UUID or 8-char prefix; either a
session id or a task id)
**Then** the controller resolves the most relevant session via
`client.resolve_active_session` / `client.list_running_agents` and calls
`client.attach_chat`. Subsequent turns are observed read-only against that
session until `/detach`.

**Given** the argument does not match any running agent
**When** the command is processed
**Then** the REPL shows a not-found error and stays in orchestrator mode.

**Given** the command is invoked with no argument
**When** the command is parsed
**Then** the REPL prints `Usage: /attach <task-id|session-id>`.

### `/detach`

**Given** the chat is attached to an agent session
**When** the user types `/detach`
**Then** the controller calls `client.attach_chat(..., session_id=None)` and
the REPL returns to orchestrator mode.

### Post-turn agents rail

**Given** there is at least one active worker or reviewer session
**When** an orchestrator turn completes
**Then** the REPL prints a compact rail (`● N local agents · ↓ to manage`) plus
one detail line per agent (role, task title, elapsed, token total).

**Given** there are no active agents
**When** an orchestrator turn completes
**Then** the rail is suppressed entirely — no nag.

### `↓` picker

**Given** the user presses `↓` at the REPL prompt
**When** at least one agent is running
**Then** a one-shot Textual picker opens listing `main` (orchestrator / detach)
followed by every active session; selecting an entry attaches (or, for
`main`, detaches).

______________________________________________________________________

## Test Coverage

| File                                           | Tests                                                     |
| ---------------------------------------------- | --------------------------------------------------------- |
| `tests/unit/test_chat_repl.py`                 | REPL entry points, loop behavior, scope binding           |
| `tests/unit/test_chat_commands.py`             | Slash command parsing and execution                       |
| `tests/unit/test_chat_policy.py`               | Authorization checks and session gating                   |
| `tests/unit/test_chat_controller_streaming.py` | ACP streaming, chunk handling, error paths                |
| `tests/unit/test_chat_acp_warmup.py`           | Warmup handshake + prompt initialization                  |
| `tests/core/test_chat_attach_cli.py`           | `/attach` + `/detach` end-to-end through `ChatController` |
| `tests/unit/test_chat_picker_choice.py`        | `_resolve_picker_choice` boundary cases                   |
| `tests/unit/test_chat_rail_rendering.py`       | Agents-rail formatting (header + detail rows)             |

**All tests use mocked ACP connections.** Real agent spawn is integration-level.
