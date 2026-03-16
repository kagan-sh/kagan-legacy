---
title: ACP session lifecycle
description: How orchestrator ACP sessions start, persist state, and close in chat and TUI
icon: material/connection
tags:
  - acp
  - sessions
  - chat
---

# ACP session lifecycle

Use this page when you need exact session behavior for `kagan chat` and TUI orchestrator chat.

## Two session layers

| Layer                   | Purpose                                                | Lifetime                              |
| ----------------------- | ------------------------------------------------------ | ------------------------------------- |
| **Chat session**        | Your conversation history + preferred backend          | Persistent (saved in Kagan settings)  |
| **ACP runtime session** | Live transport (`initialize -> new_session -> prompt`) | Ephemeral while one ACP run is active |

Important: chat session ID and ACP runtime session ID are different.

## `kagan chat` (REPL)

1. Kagan loads or creates a persisted chat session (`source: repl`).
1. It spawns one ACP agent process for the REPL runtime.
1. It handshakes once, then reuses that ACP connection for each prompt.
1. It persists history after each turn (`/sessions` and `--session-id` reattach).
1. On normal exit (`Ctrl+D`, `/exit`), ACP is closed, temporary `.mcp.json` is removed, and process resources are released.
1. If you switch backend in-session, Kagan restarts the ACP runtime but keeps the same persisted chat session.

## TUI orchestrator chat (`Space` split cycle / `Ctrl+F` fullscreen while open)

1. TUI keeps a persisted orchestrator chat session list (`source: tui-orchestrator`).
1. Each orchestrator message runs as a fresh ACP turn (`run_orchestrator_turn`).
1. A turn writes `.mcp.json`, handshakes, streams updates, then removes `.mcp.json`.
1. History is persisted after orchestrator messages and when switching/creating orchestrator sessions.

## What happens when clients close

| Client close                | ACP runtime session                                                 | Persisted chat session                                          |
| --------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------- |
| Close `kagan chat` normally | Closed immediately with process/context teardown                    | Kept; reopen with `/sessions` or `kagan chat --session-id <id>` |
| Quit TUI normally           | In-flight orchestrator turn is interrupted; runtime ACP is not kept | Kept; TUI restores last orchestrator session                    |
| Force-kill client process   | No graceful ACP shutdown path                                       | Last persisted checkpoint is kept                               |

Notes:

- Persistence is checkpoint-based (after sends and session switches). Abrupt process kill can lose unsaved in-memory UI state.
- Stored chat history is bounded (sessions/messages/history are capped) so storage does not grow unbounded.

______________________________________________________________________

[:octicons-arrow-right-24: Quickstart](../quickstart.md) · [:octicons-arrow-right-24: AUTO vs PAIR](modes-auto-vs-pair.md) · [:octicons-arrow-right-24: CLI reference](../reference/cli.md)
