# VS Code Extension Features -- `packages/vscode`

*Native VS Code client for Kagan -- board, agent output, diffs, reviews, and terminal.*

______________________________________________________________________

## Chat Participant (`@kagan`)

Open the VS Code Chat panel (`Cmd+Shift+I` or the chat icon in the sidebar), then type `@kagan`.

**Default: Orchestrator chat.** Type `@kagan <message>` to talk to the Kagan orchestrator. It creates tasks, answers questions about the board, and coordinates agents. The session persists across turns -- follow-up messages continue the same conversation.

**Commands:**

- `@kagan /watch` or `@kagan /watch <task name>` -- Stream a task's live agent output. Shows brief recent history then streams in real-time until the agent completes. For non-running tasks, shows the most recent events. Plain follow-up messages in that same chat conversation are sent back to the watched task.
- `@kagan /status` -- Board summary table + running tasks.
- `@kagan /attach <session-id|task-id>` -- Attach the chat panel to a running worker or reviewer session. Accepts a full UUID or 8-char prefix.
- `@kagan /detach` -- Return the chat panel to orchestrator mode.
- `@kagan` with no message -- Shows board status.

**Quick access from the board:** Click the chat icon ($(comment-discussion)) on any IN_PROGRESS or REVIEW task in the sidebar tree to open the Chat panel pre-filled with `/watch <task>`.

**Action buttons** appear after streaming: Approve, Reject, Merge, View Diff, or Run Task, depending on the task's status.

The participant is `isSticky` -- once selected, follow-up messages stay in the `@kagan` context. Starting a fresh conversation clears both the orchestrator session handle and any watched-task follow-up routing.

______________________________________________________________________

## Kanban Board (TreeView)

The sidebar shows a collapsible tree: **Backlog**, **In Progress**, **Review**, **Done**.

- Each task shows its title, priority icon, and active agent backend.
- Click a task to open it. Right-click for context actions.
- The tree auto-refreshes on SSE events.

______________________________________________________________________

## Task Commands

All commands are available via the Command Palette (`Cmd+Shift+P`) and right-click context menus.

| Command           | Scope       | Description                         |
| ----------------- | ----------- | ----------------------------------- |
| Create Task       | Board       | Title, description, priority        |
| Run Task          | Backlog     | Starts an agent session             |
| Cancel Task       | In Progress | Stops the running agent             |
| Edit Task         | Any         | Update title, description, priority |
| Move Task         | Any         | Change column                       |
| Delete Task       | Any         | Permanent delete (confirmation)     |
| View Diff         | Review/Done | Opens SCM diff view                 |
| Show Agent Output | Any         | Opens diagnostic log channel        |
| Attach Terminal   | In Progress | Opens agent terminal                |

______________________________________________________________________

## Task Diffs (SCM Provider)

When viewing a task diff, Kagan registers as a Source Control provider:

- Lists changed files with status icons and insertion/deletion stats.
- Click a file to open a side-by-side diff view using VS Code's native diff editor.
- Patches are extracted per-file from the task's unified diff.

______________________________________________________________________

## Review Verdicts (Comments)

For tasks in Review status:

- Opens a virtual document listing acceptance criteria.
- Each criterion shows a PASS/FAIL verdict as a VS Code comment thread.
- Commands: **Approve**, **Reject** (requires feedback), **Merge** (requires confirmation).

______________________________________________________________________

## Agent Terminal

For running tasks, "Attach Terminal" opens the agent's working environment:

- Supports launchers: tmux, nvim, vscode, cursor, windsurf, kiro, antigravity.
- Opens the worktree directory and start prompt in a new terminal or editor window.

______________________________________________________________________

## Agent Attach

The `@kagan` chat panel can attach to any running worker or reviewer session.

- **Tree view.** A new "Running Agents" view (`kagan.agents`) sits alongside
  the board tree. Each node shows a worker / reviewer session with role,
  elapsed time, and token totals. Clicking a node runs
  `kagan.attachToSession`.
- **`@kagan /attach <id>`.** Accepts either a full UUID or an 8-char prefix,
  matching by session id, session-id prefix, task id, or task-id prefix
  (`resolveAgentSessionId`). Plain follow-up turns in the same conversation
  are then routed through the attached session tail.
- **`@kagan /detach`.** Clears the attach for the current conversation and
  returns the panel to orchestrator mode.
- **Commands.** `kagan.attachToSession` and `kagan.detachFromSession` are
  available from the tree-view inline icons, the command palette (when
  `kagan.connected`), and the `kagan.chat.open` entry point with
  `{kind: "attach", sessionId, taskTitle}`.
- **Shared state.** `providers/attach-state.ts` is a small in-memory registry
  keyed by VS Code chat conversation id (with a `"global"` sentinel) so the
  tree view and chat participant agree on which session is attached without
  importing each other.

*Tests:* `packages/vscode/src/providers/chat.participant.helpers.test.ts`
(prompt parsing + session resolution), `packages/vscode/test/integration/chat-attach.test.ts`
(extension-host attach / detach through the chat participant). Real UI smoke
coverage belongs in `packages/vscode/test/e2e/`.

______________________________________________________________________

## Auto-Watch on Attach

When you attach to a task from the TUI, web dashboard, or CLI, and the task opens in VS Code (or Cursor, Windsurf, Kiro, Antigravity), the extension automatically opens the Chat panel streaming that task's live agent output. Zero extra clicks.

This works because the server writes a small context file (`.kagan/attach_context.json`) into the worktree when launching the IDE. The extension detects it on activation, verifies the task is still running, and opens `@kagan /watch`.

Disable with `kagan.autoWatchOnAttach: false` if you prefer the old behavior.

______________________________________________________________________

## Connection

- **Auto-connect** on startup (configurable via `kagan.autoConnect`).
- **Auto-start** local server when `serverUrl` is localhost and no server is running.
- **Status bar** shows connection state and task counts. Click to reconnect.
- **SSE reconnect** with exponential backoff (1s to 30s).

______________________________________________________________________

## Settings

| Setting                   | Default                 | Description                           |
| ------------------------- | ----------------------- | ------------------------------------- |
| `kagan.serverUrl`         | `http://localhost:8765` | Kagan server URL                      |
| `kagan.autoConnect`       | `true`                  | Connect on startup                    |
| `kagan.autoStartServer`   | `true`                  | Start local server if none is running |
| `kagan.serverCommand`     | `kagan`                 | CLI command for local auto-start      |
| `kagan.autoWatchOnAttach` | `true`                  | Auto-open Chat on attach              |
