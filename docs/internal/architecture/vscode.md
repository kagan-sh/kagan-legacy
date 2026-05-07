# VS Code Extension Architecture -- `packages/vscode`

*Design principles: native VS Code APIs, thin client over Kagan REST and SSE, one provider per concern.*

______________________________________________________________________

## Context

`packages/vscode` is the VS Code client for Kagan. It connects to the same HTTP server used by the web dashboard (`kagan web`) and surfaces the board, agent output, diffs, and reviews through native VS Code primitives.

______________________________________________________________________

## Design Principles

1. **Platform-native first** -- every feature uses the most idiomatic VS Code API available. Chat Participant for agent output, TreeView for the board, SCM for diffs, Comments for reviews.
1. **Thin client** -- workflow logic stays in Python (`kagan.core`); the extension only coordinates API calls and renders state.
1. **Single integration boundary** -- all server communication flows through `KaganClient` (REST) and `SSEStream` (Server-Sent Events).
1. **One provider per concern** -- board, agent output, diffs, reviews, and terminal each have a dedicated provider. No god objects.
1. **Auto-start local server** -- when `serverUrl` points at localhost and nothing is listening, the extension spawns `kagan serve` automatically.

______________________________________________________________________

## Internal Structure

```text
packages/vscode/src/
├── extension.ts                    # Activation, wiring, SSE dispatch
├── api/
│   ├── client.ts                   # KaganClient — REST wrapper
│   ├── sse.ts                      # SSEStream — EventSource over fetch
│   └── types.ts                    # Shared types, EVENT_TYPE / SSE_TYPE consts
├── providers/
│   ├── chat.participant.ts         # @kagan chat participant (agent output, /attach, /detach)
│   ├── attach-state.ts             # In-memory attach registry shared by chat + tree view
│   ├── board.tree.ts               # Kanban board TreeView
│   ├── running-agents.tree.ts      # "Running Agents" TreeView (polls /api/v1/agents/running)
│   ├── events.output.ts            # Agent diagnostic log (OutputChannel)
│   ├── review.comments.ts          # Review verdicts (Comments API)
│   ├── tasks.scm.ts                # Task diffs (SCM / TextDocumentContentProvider)
│   ├── tasks.scm.helpers.ts        # Diff parsing helpers
│   ├── tasks.terminal.ts           # Terminal attach (tmux, nvim, IDE launchers)
│   ├── tasks.terminal.helpers.ts   # Launcher normalization, deep links
│   ├── mention-link-provider.ts    # @task / @session links in editor docs
│   └── mention-completion-provider.ts # @ typeahead for tasks/sessions
├── commands/
│   ├── tasks.ts                    # Task CRUD, run, cancel, move, edit
│   └── review.ts                   # Approve, reject, merge
├── server/
│   └── supervisor.ts               # Local server auto-start lifecycle
└── status/
    └── bar.ts                      # Connection + task count status bar
```

______________________________________________________________________

## VS Code API Surface Map

Each Kagan concern maps to a specific VS Code API:

| Concern         | VS Code API                 | Provider              |
| --------------- | --------------------------- | --------------------- |
| Agent output    | Chat Participant            | `chat.participant.ts` |
| Kanban board    | TreeView                    | `board.tree.ts`       |
| Task diffs      | TextDocumentContentProvider | `tasks.scm.ts`        |
| Review verdicts | Comments Controller         | `review.comments.ts`  |
| Agent terminal  | Terminal API                | `tasks.terminal.ts`   |
| Diagnostics     | OutputChannel               | `events.output.ts`    |
| Connection      | StatusBarItem               | `bar.ts`              |

______________________________________________________________________

## Data Flow

```text
Kagan Server (Python)
  │
  ├── REST API ──── KaganClient ──── Commands / Providers
  │
  └── SSE stream ── SSEStream ──┬── BoardTreeProvider (refresh)
                                ├── ChatParticipant  (stream markdown)
                                ├── AgentOutputProvider (diagnostic log)
                                └── extension.ts (task count refresh)
```

SSE messages are two types: `TASK_UPDATED` (board-level) and `SESSION_EVENT` (agent-level). Both types and all event subtypes are defined once in `types.ts` as `SSE_TYPE` and `EVENT_TYPE` const objects.

______________________________________________________________________

## Chat Participant (`@kagan`)

Registered as `kagan.agent` with `isSticky: true`. Three modes:

| Command     | Behavior                                                              |
| ----------- | --------------------------------------------------------------------- |
| *(default)* | Orchestrator chat -- proxies messages to `POST /api/chat/{id}/stream` |
| `/watch`    | Stream task agent output via SSE                                      |
| `/status`   | Board summary table + running task list                               |

**Orchestrator chat** creates a server-side session (`POST /api/chat/sessions`) and streams each turn via SSE. The session ID persists across turns within the same VS Code chat conversation. A new conversation resets both the orchestrator session and any sticky `/watch` follow-up state.

**Watch pipeline:**

1. Fetch tail of recent events via `GET /api/tasks/{id}/events?tail=1&limit=10`
1. Coalesce OUTPUT_CHUNK tokens into flowing markdown
1. Render tool calls as inline code, status changes as rules
1. If IN_PROGRESS, subscribe to live SSE until AGENT_COMPLETED/FAILED
1. Append action buttons based on final task state
1. Route later plain messages in that same chat conversation to `POST /api/tasks/{id}/follow-up`

**`kagan.chat.open` command** accepts a tree item or string and opens the Chat panel pre-filled with `@kagan /watch <task>`.

______________________________________________________________________

## ACP Payload Extraction

Server event payloads nest ACP protocol data under `payload.acp`. Helper functions (`acpPayload`, `extractToolTitle`, `extractToolStatus`) mirror the web dashboard's `event-stream.tsx` to read fields correctly:

- Tool name: `payload.acp.title`
- Tool status: `payload.acp.status`
- Tool input: `payload.acp.rawInput`
- Task transitions: `payload.from` / `payload.to`
- Agent errors: `payload.error`

______________________________________________________________________

## Agent Attach

The chat panel can attach to any running worker or reviewer session. State and
plumbing:

- `packages/vscode/src/providers/running-agents.tree.ts` registers a
  `kagan.agents` tree view that polls `GET /api/v1/agents/running` every 5s
  (and refreshes whenever the global SSE stream emits `TASK_UPDATED`). Each
  node exposes `kagan.attachToSession` inline.
- `packages/vscode/src/providers/attach-state.ts` is a small in-memory registry
  keyed by VS Code chat conversation id (with a `"global"` sentinel). It is
  intentionally extracted so the tree-view can trigger an attach without
  importing the chat participant module.
- `chat.participant.helpers.ts` adds `parseAttachPrompt` (UUID or 8-char prefix
  validation) and `resolveAgentSessionId` (exact session id → session prefix →
  exact task id → task prefix matching against the running-agents list).
- `chat.participant.ts` handles `@kagan /attach <id>` and `@kagan /detach`,
  remembers `attachedSessionId` on the participant state, and routes plain
  follow-up turns through the attached session tail when a session is bound.
- Commands `kagan.attachToSession` and `kagan.detachFromSession` are
  registered in `extension.ts` and surfaced from the tree view, the command
  palette, and the `kagan.chat.open` entry point (`{kind: "attach"}`).

The legacy `attach_context.json` flow described below remains the entry point
for IDE-launch auto-watch; explicit `/attach` is the new in-chat path.

______________________________________________________________________

## Attach Context Detection

When the IDE is opened via "Attach to Task" (from TUI, web, or CLI), the server writes `.kagan/attach_context.json` into the worktree:

```json
{ "task_id": "abc123", "session_id": "def456" }
```

On activation, `detectAttachContext()` in `extension.ts`:

1. Checks `kagan.autoWatchOnAttach` setting (default `true`)
1. Looks for `.kagan/attach_context.json` in the workspace root
1. Waits for SSE connection to establish
1. Verifies the task is still `IN_PROGRESS` via the API
1. Executes `kagan.chat.open` with the task ID, opening the Chat panel

This works for all IDE launchers (vscode, cursor, windsurf, kiro, antigravity) since they all open the same worktree containing the context file. The extension also registers `workspaceContains:.kagan/attach_context.json` as an activation event for faster startup in the attach case.

**Server side:** `_launchers.py` writes the file via `_write_attach_context()`. The `task_id` is passed from `Sessions.run()` through `launch_kwargs`.

______________________________________________________________________

## Server Auto-Start

`LocalServerSupervisor` manages the local server lifecycle:

1. Check if `serverUrl` is localhost
1. If nothing responds to `/health`, spawn `<serverCommand> serve`
1. Poll `/health` every 250ms for up to 12 seconds
1. Pipe server stdout/stderr to the "Kagan Server" OutputChannel
1. On shutdown, send `SIGTERM`, wait for process exit, then escalate to `SIGKILL`
   only if the server does not exit within the grace window

______________________________________________________________________

## Testing

Three-layer split (see `docs/internal/testing.md` for conventions):

| Layer       | Tool                               | Scope                          |
| ----------- | ---------------------------------- | ------------------------------ |
| Unit        | Vitest                             | Pure helpers, API edge cases   |
| Integration | `@vscode/test-cli` + test-electron | Extension host, commands, docs |
| E2E         | WDIO + `wdio-vscode-service`       | Real VS Code UI smoke          |

```bash
pnpm run test:unit
pnpm run test:integration
pnpm run test:e2e
```
