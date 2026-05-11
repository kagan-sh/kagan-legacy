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
**When** `ChatEngine` emits assistant chunk events
**Then** `CLIRenderer` prints each chunk to the Rich console immediately with streaming animation, and turn finalization closes the live line without replaying the response.

**Given** the user reattaches to a finished agent session in the
orchestrator overlay
**When** replay events arrive from `/api/v1/sessions/{id}/replay`
**Then** the panel renders the recorded transcript instantly — the
typewriter animation is reserved for live tokens and never replays history.

______________________________________________________________________

### Tool call rendering

**Given** the agent sends `ToolCallStart`
**When** `ChatEngine` emits it
**Then** it prints the tool name and arguments.

**Given** the agent sends `ToolCallProgress` updates
**When** `ChatEngine` emits them
**Then** it updates the status indicator (pending ✓/✗).

______________________________________________________________________

### Permission requests

**Given** the agent requests permission for a tool call
**When** `ChatEngine` emits a `PermissionRequest`
**Then** `PermissionUI` presents the inline trust-tier panel and resolves the request with `allow_once`, `allow_always`, `deny`, or `deny_feedback`.

**Given** the user tries the removed `kagan chat --yolo` flag
**When** Click parses the command
**Then** the command exits with usage code 2 and points the user to valid options.

**Given** the user wants permissive behavior for the current REPL session
**When** a permission request appears
**Then** they choose "Allow all for session" in the approval panel instead of setting a startup flag.

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

### ACP factory reconnect

**Given** the long-lived ACP factory raises `BrokenPipeError`,
`ConnectionResetError`, or `acp.RequestError` mid-conversation
**When** the next prompt is dispatched
**Then** the factory is restarted once in place (tear-down + respawn) and
the prompt is retried. A second consecutive failure is surfaced as an
error rather than retried again.

**Given** the agent subprocess has exited between turns
**When** the next prompt is dispatched
**Then** the factory detects the dead process via a liveness check before
sending and rebuilds the connection rather than writing into a closed pipe.

**Given** the orchestrator turn produces no assistant text
**When** the turn finalizes
**Then** no synthetic `"No response from orchestrator"` row is appended to
chat history. Empty turns are dropped from the persisted transcript.

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
**Then** it binds to `app.orchestrator_sessions` and the shared TUI chat runner.

**Given** the user types a slash command
**When** they press Enter
**Then** the widget uses the shared slash parser from `kagan.cli.chat.commands`
and handles the TUI action locally.

**Given** the user sends a normal message
**When** the turn runs
**Then** `_chat_runner.py` drives `ChatEngine` / ACP helpers and renders
`ChatEvent` updates into the widget.

______________________________________________________________________

## Resume Behavior

The frame-stream subsystem (`event_log` table + `Last-Event-ID` SSE endpoints)
provides durable resume across the following failure modes.

### Window / tab close mid-turn

Assistant text is persisted to `event_log` per token as `append` frames by
`ChatEngine`. On reopen, the browser `EventSource` connects fresh (no
`Last-Event-ID`), receives a full `snapshot` frame, and replays the complete
transcript including any partial assistant turn.

### Network drop

The browser `EventSource` sends the native `Last-Event-ID` header on automatic
reconnect. The server replays from `from_seq + 1`, emitting a catchup
`snapshot` + `ready` before resuming live tail. No manual backoff is needed
in the web client.

### Server restart mid-turn

`ChatEngine._TurnState` is in-process and is lost on restart. Partial assistant
text written to `event_log` before the crash survives. Clients see finalized
history on reload via the `snapshot` frame; the partial turn is presented as
whatever was persisted (the `finalize` frame may be missing, leaving the entry
`finalized=False` — rendered as an incomplete response).

### Orphan reap on boot

`reap_orphan_sessions` runs at server startup for sessions whose process state
is stale:

- **Alive PID** — emits a `FrameResume` (`type="resume"`) into `event_log`.
  Connected clients see it as a `resume` SSE event and can surface an
  "agent resumed" notice.
- **Dead PID** — cascades the task to `BACKLOG` via `transition_task`, then
  emits a `FramePatch(op="finalize", reason="orphan_reap")`. The partial
  transcript is preserved up to that point.

### Single-flight semantics

`ChatEngine.try_claim_turn` / `_chat_routes._claim_turn_slot` enforce
single-flight per session. A concurrent POST to `/api/chat/{id}/stream`
returns 409 and presents the takeover UI. This behavior is unchanged by the
frame-stream work.

### Path-based idempotency

Patches are addressed by stable `idx` values, not by seq. Re-applying the
same patch (e.g., after a replay window overlap) is safe; no echo-suppression
logic is required in consumers.

______________________________________________________________________

## Test Coverage

| File                                           | Tests                                                 |
| ---------------------------------------------- | ----------------------------------------------------- |
| `tests/unit/test_chat_repl.py`                 | REPL entry points, loop behavior, scope binding       |
| `tests/unit/test_chat_commands.py`             | Slash command parsing and execution                   |
| `tests/unit/test_chat_policy.py`               | Authorization checks and session gating               |
| `tests/unit/test_chat_controller_streaming.py` | ACP streaming, chunk handling, error paths            |
| `tests/unit/test_chat_acp_warmup.py`           | Warmup handshake + prompt initialization              |
| `tests/cli/test_chat_sessions.py`              | `/switch`, `/stop`, `/close` through `ChatController` |
| `tests/unit/test_chat_picker_choice.py`        | `_resolve_picker_choice` boundary cases               |
| `tests/unit/test_chat_rail_rendering.py`       | Agents-rail formatting (header + detail rows)         |

**All tests use mocked ACP connections.** Real agent spawn is integration-level.
