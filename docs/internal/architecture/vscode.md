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
│   ├── chat.participant.ts         # @kagan chat participant (agent output, /switch)
│   ├── board.tree.ts               # Kanban board TreeView
│   ├── sessions.tree.ts            # "Sessions" TreeView (polls /api/v1/sessions)
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
| `/switch`   | Switch to a session by ID                                             |
| `/status`   | Board summary table + running task list                               |

**Orchestrator chat** creates a server-side session (`POST /api/chat/sessions`) and streams each turn via SSE. The session ID persists across turns within the same VS Code chat conversation. A new conversation resets the orchestrator session.

**Session switch pipeline:**

1. Resolve session ID via `GET /api/v1/sessions/{id}`
1. Update participant state with the selected session
1. Stream events via SSE for live sessions
1. Append action buttons based on final task state

**`kagan.chat.open` command** accepts a tree item or string and opens the Chat panel.

______________________________________________________________________

## ACP Payload Extraction

Server event payloads nest ACP protocol data under `payload.acp`. Helper functions (`acpPayload`, `extractToolTitle`, `extractToolStatus`) mirror the web dashboard's `event-stream.tsx` to read fields correctly:

- Tool name: `payload.acp.title`
- Tool status: `payload.acp.status`
- Tool input: `payload.acp.rawInput`
- Task transitions: `payload.from` / `payload.to`
- Agent errors: `payload.error`

______________________________________________________________________

## Sessions

The chat panel can switch to any running worker or reviewer session. State and
plumbing:

- `packages/vscode/src/providers/sessions.tree.ts` registers a
  `kagan.agents` tree view that polls `GET /api/v1/sessions` every 5s
  (and refreshes whenever the global SSE stream emits `TASK_UPDATED`). Each
  node exposes `kagan.switchSession` inline.
- `chat.participant.helpers.ts` adds `parseSwitchPrompt` (UUID or 8-char prefix
  validation) and `resolveSessionId` (exact session id → session prefix →
  exact task id → task prefix matching against the sessions list).
- `chat.participant.ts` handles `@kagan /switch <id>`, remembers
  `selectedSessionId` on the participant state, and routes plain follow-up
  turns through the selected session when a session is bound.
- Commands `kagan.switchSession`, `kagan.stopSession`, and `kagan.closeSession` are
  registered in `extension.ts` and surfaced from the tree view and the command
  palette.

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

## Design System

The extension applies the [Kagan Design System](../../../packages/web/../../../Downloads/kagan-design-system/project/README.md) within the constraints of the VS Code extension API.

### Theme color contributions

Seven Kagan-specific theme color tokens are declared in `package.json` under `contributes.colors`. Extensions and themes can override these; the defaults are calibrated for dark and light VS Code themes:

| Token               | Dark default | Light default | Usage                     |
| ------------------- | ------------ | ------------- | ------------------------- |
| `kagan.primary`     | `#d4a84b`    | `#b89154`     | Amber phosphor accent     |
| `kagan.railRunning` | `#3fb58e`    | `#1a8563`     | Connected / running state |
| `kagan.railWarning` | `#e6c07b`    | `#a87b25`     | Degraded / warning state  |
| `kagan.railReview`  | `#c27c4e`    | `#a8653a`     | Review column accent      |
| `kagan.railIdle`    | `#777777`    | `#8a7f72`     | Disconnected / idle state |
| `kagan.modeAuto`    | `#d4a84b`    | `#b89154`     | AUTO execution mode badge |
| `kagan.modePair`    | `#6fa3d4`    | `#6fa3d4`     | PAIR execution mode badge |

Usage in code:

```typescript
// Reference via ThemeColor — never hard-coded hex
item.color = new vscode.ThemeColor("kagan.railRunning");
```

### Casing rules

- **UPPERCASE:** TreeView section/column labels (`BACKLOG`, `IN PROGRESS`, `REVIEW`, `DONE`), mode badges.
- **Sentence case:** All command titles, tooltips, status bar text, notifications, button labels.
- **No emoji.** Use codicon syntax (`$(check)`, `$(pulse)`, etc.) in VS Code surfaces that support it.

### Status bar

The brand glyph `ᘚᘛ` (U+15DA U+15DB) prefixes all status bar states. Color is driven by `kagan.railRunning` (connected) and `kagan.railIdle` (disconnected).

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
