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

Kagan includes an AI orchestrator chat that works in two places: the **CLI REPL** (`kagan chat`) and the **TUI overlay** (`Space` split cycle in Kanban/Task screens). Both share the same slash commands and session persistence.

______________________________________________________________________

## CLI REPL

```bash
kagan chat                         # interactive REPL
kagan chat --prompt "Plan a refactor"  # single-shot (send, print, exit)
kagan chat --session-id <id>       # resume a previous session
kagan chat --agent opencode        # override agent backend
```

The REPL persists conversation history across restarts. Type a message and press Enter to send. `Ctrl+D` or `/exit` to quit.

______________________________________________________________________

## AI Panel

| Key        | Action             |
| ---------- | ------------------ |
| ++space++  | Cycle split layout |
| ++ctrl+f++ | Fullscreen chat    |
| ++ctrl+k++ | Session Switcher   |
| ++esc++    | Close Panel        |

The AI Panel runs as an orchestrator session with access to all project tasks via MCP tools. Messages are persisted per-session.

In Kanban and Task screens, `Space` cycles `vertical -> horizontal -> vertical` while the AI Panel stays open. Use `Esc` to close it.

______________________________________________________________________

## Slash commands

Type `/` followed by a command name. All commands work in both the CLI REPL and TUI overlay.

| Command     | Description |
| ----------- | ----------- |
| Command     | Alias       |
| ----------- | -----       |
| `/help`     | `/?`        |
| `/exit`     | `/q`        |
| `/clear`    |             |
| `/new`      |             |
| `/sessions` | `/s`        |
| `/agents`   | `/a`        |
| `/status`   |             |
| `/project`  | `/p`        |
| `/delete`   |             |
| `/tool`     |             |
| `/flow`     | `/f`        |

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
