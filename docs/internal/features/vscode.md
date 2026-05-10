# VS Code Extension Features -- `packages/vscode`

*Native VS Code client for Kagan -- board, agent output, diffs, reviews, and terminal.*

______________________________________________________________________

## Chat Participant (`@kagan`)

Open the VS Code Chat panel (`Cmd+Shift+I` or the chat icon in the sidebar), then type `@kagan`.

**Default: Orchestrator chat.** Type `@kagan <message>` to talk to the Kagan orchestrator. It creates tasks, answers questions about the board, and coordinates agents. The session persists across turns -- follow-up messages continue the same conversation.

**Commands:**

- `@kagan /status` -- Board summary table + running tasks.
- `@kagan /switch <session-id>` -- Switch the chat panel to a session.
- `@kagan /stop` -- Stop the selected session.
- `@kagan /close` -- Close the selected session.
- `@kagan` with no message -- Shows board status.

**Action buttons** appear after streaming: Approve, Reject, Merge, View Diff, or Run Task, depending on the task's status.

The participant is `isSticky` -- once selected, follow-up messages stay in the `@kagan` context. Starting a fresh conversation clears the orchestrator session handle.

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

## Sessions

The `@kagan` chat panel can switch to any running worker or reviewer session.

- **Tree view.** A "Sessions" view (`kagan.agents`) sits alongside the board tree.
  Each node shows a worker / reviewer session with role, elapsed time, and token
  totals. Clicking a node runs `kagan.switchSession`.
- **`@kagan /switch <id>`.** Accepts either a full UUID or an 8-char prefix.
- **Commands.** `kagan.switchSession`, `kagan.stopSession`, and `kagan.closeSession`
  are available from the tree-view inline icons and the command palette (when
  `kagan.connected`).

*Tests:* `packages/vscode/src/providers/chat.participant.helpers.test.ts`
(prompt parsing + session resolution). Real UI smoke coverage belongs in
`packages/vscode/test/e2e/`.

______________________________________________________________________

## Connection

- **Auto-connect** on startup (configurable via `kagan.autoConnect`).
- **Auto-start** local server when `serverUrl` is localhost and no server is running.
- **Status bar** shows connection state and task counts. Click to reconnect.
- **SSE reconnect** with exponential backoff (1s to 30s).

______________________________________________________________________

## Settings

| Setting                 | Default                 | Description                           |
| ----------------------- | ----------------------- | ------------------------------------- |
| `kagan.serverUrl`       | `http://localhost:8765` | Kagan server URL                      |
| `kagan.autoConnect`     | `true`                  | Connect on startup                    |
| `kagan.autoStartServer` | `true`                  | Start local server if none is running |
| `kagan.serverCommand`   | `kagan`                 | CLI command for local auto-start      |

______________________________________________________________________

## Design System

The extension applies the Kagan Design System within the constraints of the VS Code extension API.

### Kanban board TreeView

Column labels follow the canonical UPPERCASE taxonomy: **BACKLOG**, **IN PROGRESS**, **REVIEW**, **DONE**. Task item labels are sentence case (the task title as authored).

### Status bar

The brand glyph `ᘚᘛ kagan` is the status bar prefix. Connection state is color-coded via Kagan theme token contributions (`kagan.railRunning`, `kagan.railIdle`), which VS Code themes can override.

### Theme color tokens

Defined in `package.json` under `contributes.colors`. See `docs/internal/architecture/vscode.md` for the full token table and values.

### Voice

All user-facing strings (command titles, tooltips, notifications, button labels) use sentence case. No exclamation marks. No hype words. Declarative: "Task deleted", "Session stopped", not "Task successfully deleted!"
