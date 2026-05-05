---
title: Chat & REPL
description: Interactive orchestrator chat, slash commands, and session management
icon: material/chat
tags:
  - chat
  - repl
  - orchestrator
---

# Chat & REPL

Kagan includes an AI orchestrator chat that works in two places: the **CLI REPL** (`kagan chat`) and the **TUI AI Panel** (`F4` / `Ctrl+I` in Kanban/Task screens). Both share the same slash commands and session persistence.

______________________________________________________________________

## CLI REPL

```bash
kagan chat                         # interactive REPL
kagan chat --prompt "Plan a refactor"  # single-shot (send, print, exit)
kagan chat --session-id <id>       # resume a previous session
kagan chat --agent opencode        # override agent backend
kagan chat --yolo                  # auto-approve every tool call
```

The REPL persists conversation history across restarts. Type a message and press Enter to send. Agent responses stream into the terminal as chunks arrive, then the completed turn is kept in history. `Ctrl+D` or `/exit` to quit.

### Prompt and toolbar

The input prompt is pinned to the bottom of the terminal for the entire session. The leading glyph reflects state:

| Glyph             | State                      |
| ----------------- | -------------------------- |
| `❯` (teal)        | Idle, waiting for input    |
| `◐ ◓ ◑ ◒` (amber) | Streaming a model response |
| `◇`               | Plan mode (`/flow` plan)   |

The bottom toolbar shows the active backend, session, pending approval count, currently running tool, approximate token usage, and a git badge. The badge displays the current branch with `↑N` / `↓M` markers when the local branch is ahead of or behind its upstream.

A rotating tip line (eight tips, 30 s cadence; advances on submit) sits beneath the toolbar.

### Yolo mode

`--yolo` skips the per-tool-call permission prompt and auto-approves every request for the session. On boot it shows a disclaimer and requires you to type `I ACCEPT` exactly; anything else aborts. The boot banner border turns red and a `YOLO` badge appears in the bottom toolbar while it is active. Each auto-approved call is still logged as `● yolo auto-approve: <tool>` so you can see what ran. Use only inside disposable worktrees or sandboxes you trust the agent to operate on unattended.

### Approval panel

When the agent requests permission to run a tool, the REPL surfaces a yellow-bordered panel with the tool name, a short preview (syntax-highlighted for shell commands, key arguments otherwise), and four options:

| #   | Option                             | Effect                                                                |
| --- | ---------------------------------- | --------------------------------------------------------------------- |
| 1   | Approve once                       | Allow this single call.                                               |
| 2   | Approve for this session           | Allow this and any future call to the same tool until the REPL exits. |
| 3   | Reject                             | Deny without explanation.                                             |
| 4   | Reject — tell the model what to do | Deny and forward an inline feedback message back to the agent.        |

| Key                           | Action                                            |
| ----------------------------- | ------------------------------------------------- |
| ++up++ / ++down++             | Move selection                                    |
| ++1++ / ++2++ / ++3++ / ++4++ | Jump to option and confirm                        |
| ++enter++                     | Confirm the highlighted option                    |
| ++ctrl+e++                    | Open the full preview in a pager (when truncated) |
| ++esc++ / ++ctrl+c++          | Cancel (= reject)                                 |

Use `/approvals` to list session-granted approvals or revoke one (`/approvals revoke <name>`).

#### Batched approvals

When the agent issues several tool calls at once, the REPL collects them inside a 100 ms debounce window and renders a single combined panel listing every pending tool. Per-item options 1–4 work exactly as above; two extra options operate on the entire batch:

- Option 5 — **Approve all remaining**
- Option 6 — **Reject all remaining**

Use ++tab++ / ++shift+tab++ to move between items in the header.

Tune the debounce window and item cap via [`KAGAN_BATCH_APPROVAL_DEBOUNCE_MS` and `KAGAN_BATCH_APPROVAL_CAP`](../reference/configuration.md#environment-variables-passed-into-interactive-sessions).

______________________________________________________________________

## AI Panel

| Key                 | Action             |
| ------------------- | ------------------ |
| ++f4++ / ++ctrl+i++ | Toggle AI Panel    |
| ++space++           | Cycle split layout |
| ++ctrl+f++          | Fullscreen chat    |
| ++ctrl+k++          | Session Switcher   |
| ++esc++             | Close Panel        |

The AI Panel runs as an orchestrator session with access to all project tasks via MCP tools. Messages are persisted per-session.

In Kanban and Task screens, `F4` (or `Ctrl+I`) opens or closes the panel. `Space` cycles `vertical -> horizontal -> vertical` while the AI Panel stays open. Use `Esc` to close it.

______________________________________________________________________

## Slash commands

Type `/` followed by a command name. All commands work in both the CLI REPL and TUI overlay.

| Command      | Alias | Purpose                                                                |
| ------------ | ----- | ---------------------------------------------------------------------- |
| `/help`      | `/?`  | Command list and quick reference                                       |
| `/exit`      | `/q`  | Quit the REPL                                                          |
| `/clear`     |       | Clear scrollback                                                       |
| `/new`       |       | Start a fresh session, replacing the current one                       |
| `/sessions`  | `/s`  | List, attach, create, or delete sessions                               |
| `/agents`    | `/a`  | List installed agent backends or switch backend                        |
| `/approvals` |       | List session-granted approvals; revoke with `/approvals revoke <name>` |
| `/status`    |       | Backend, session, and runtime summary                                  |
| `/project`   | `/p`  | Show or switch the active Kagan project                                |
| `/repo`      |       | Show or switch the active git repo when the project spans many         |
| `/delete`    |       | Delete the current session                                             |
| `/tool`      |       | Inspect recent tool calls (`/tool <id>` for full input/output)         |
| `/flow`      | `/f`  | Toggle plan/execution flow modes                                       |
| `/analytics` |       | Print backend analytics for this project (mirrors the web tab)         |

### `/sessions` usage

```text
/sessions              # list all sessions
/sessions 2            # attach to session #2
/sessions new          # create a new session
/sessions delete 3     # delete session #3
```

### `/agents` usage

```text
/agents                # show agent picker
/agents claude-code    # switch to claude-code
```

### `/tool` usage

```text
/tool                  # list recent tool calls with IDs
/tool t007             # show full input/output for tool call t007
```

### `/approvals` usage

```text
/approvals             # list approvals granted this session
/approvals revoke <name>  # revoke a session-granted approval by tool name
```

### `/analytics` usage

```text
/analytics             # backend success rate / duration / retry summary
```

______________________________________________________________________

## Session management

### Session persistence

- Sessions are saved after each message exchange
- History is bounded: max 300 messages per session, max 30 sessions total
- Oldest sessions are pruned automatically when the limit is reached
- Session titles are auto-generated after the first exchange using a lightweight agent call (no tools, no orchestrator prompt). If generation fails or times out, the default title is kept

### Session scoping

| Mode            | Flag / Context           | Behavior                                                   |
| --------------- | ------------------------ | ---------------------------------------------------------- |
| **Global**      | No `--session-id`        | Orchestrator has access to all project tasks               |
| **Task-scoped** | `--session-id <task_id>` | Orchestrator sees task state, worktree diff, recent events |

### Session layers

Two layers exist per conversation:

| Layer                   | Purpose                               | Lifetime                             |
| ----------------------- | ------------------------------------- | ------------------------------------ |
| **Chat session**        | Conversation history + backend choice | Persistent (saved in Kagan settings) |
| **ACP runtime session** | Live agent transport                  | Ephemeral (one ACP run at a time)    |

Chat session ID and ACP runtime session ID are different. The chat session outlives individual ACP connections.

For detailed session lifecycle behavior, see [ACP session lifecycle](acp-session-lifecycle.md).

______________________________________________________________________

## Input behavior

| Key             | Action              |
| --------------- | ------------------- |
| ++enter++       | Send message        |
| ++shift+enter++ | Insert newline      |
| ++tab++         | Accept completion   |
| ++ctrl+j++      | Focus latest output |
| ++ctrl+c++      | Clear input         |
| ++esc++         | Stop agent          |
| ++ctrl+k++      | Session Switcher    |

______________________________________________________________________

[:octicons-arrow-right-24: CLI reference](../reference/cli.md) · [:octicons-arrow-right-24: Managed vs interactive](managed-vs-interactive.md) · [:octicons-arrow-right-24: Configuration](../reference/configuration.md)
