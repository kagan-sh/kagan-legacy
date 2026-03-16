# Server Architecture — `kagan.server`

*Design principles: FastMCP native, REST + WebSocket, bundled dashboard first.*

______________________________________________________________________

## References

| Package       | Use                                                              |
| ------------- | ---------------------------------------------------------------- |
| **FastMCP**   | MCP framework providing `custom_route()` for REST and WebSocket. |
| **Starlette** | Underlying ASGI framework for middleware and WebSocket handling. |
| **Pydantic**  | Wire-format models in `kagan.wire`.                              |

______________________________________________________________________

## Context

`kagan.server` extends the core MCP functionality to serve the bundled web dashboard and expose an HTTP API for integrations. It provides a full REST API and a real-time WebSocket event stream, layered on top of the standard Kagan MCP server.

______________________________________________________________________

## Design Principles

1. **FastMCP as Foundation** — Wraps `create_server()` from `kagan.mcp` and adds custom routes.
1. **Hybrid Transport** — Standard MCP (STDIO) + StreamableHTTP (REST/WS).
1. **Stateless REST** — Standard HTTP verbs for resource management.
1. **Reactive WebSocket** — Event-driven board synchronization and run management.
1. **Same-origin dashboard** — the bundled web app talks directly to the server that serves it.

______________________________________________________________________

## Internal Structure

```
src/kagan/server/
├── __init__.py        # re-export create_api_server
├── server.py          # ApiServer factory, entry point
├── _routes.py         # REST API implementation
└── _websocket.py      # WebSocket protocol and event broadcasting
```

### Dependency Direction

`kagan.server` ──► `kagan.mcp` ──► `kagan.core`

- `server` uses `mcp` to build the base server instance.
- `server` uses `core` (via `get_server_context`) for all business logic.
- `core` has zero knowledge of the server.

______________________________________________________________________

## API Server Factory

`server.py` defines `create_api_server(opts)`, which:

1. Calls `kagan.mcp.server.create_server(opts.mcp_opts)`.
1. Registers a `/health` endpoint.
1. Calls `register_routes(mcp)` to add the REST API.
1. Calls `register_websocket(mcp)` to add the real-time stream.

______________________________________________________________________

## REST API Reference

All responses are wrapped in a `WireEnvelope`: `{ ok: bool, data?: T, error?: string }`.

| Endpoint                           | Method | Description                           |
| ---------------------------------- | ------ | ------------------------------------- |
| `/health`                          | GET    | Service health check                  |
| `/api/tasks`                       | GET    | List tasks (optional `status` filter) |
| `/api/tasks`                       | POST   | Create a new task                     |
| `/api/tasks/counts`                | GET    | Get task counts grouped by status     |
| `/api/tasks/{id}`                  | GET    | Get task details                      |
| `/api/tasks/{id}`                  | PATCH  | Update task properties                |
| `/api/tasks/{id}`                  | DELETE | Delete a task (Admin tier)            |
| `/api/tasks/{id}/status`           | POST   | Transition task to new status         |
| `/api/tasks/{id}/events`           | GET    | Get event history for a task          |
| `/api/tasks/{id}/review`           | GET    | Get review status for a task          |
| `/api/tasks/{id}/review/decide`    | POST   | Approve, Reject, or Merge a task      |
| `/api/tasks/{id}/review/conflicts` | GET    | Get merge conflicts for a task        |
| `/api/tasks/{id}/diff`             | GET    | Get diff statistics                   |
| `/api/tasks/{id}/diff/files`       | GET    | Get list of modified files            |
| `/api/tasks/{id}/worktree`         | GET    | Get worktree and branch info          |
| `/api/projects`                    | GET    | List all projects                     |
| `/api/projects`                    | POST   | Create a new project (Admin tier)     |
| `/api/projects/{id}/activate`      | POST   | Set project as active                 |
| `/api/projects/{id}`               | DELETE | Delete a project (Admin tier)         |
| `/api/settings`                    | GET    | Get current server settings           |
| `/api/preflight`                   | GET    | Run preflight checks                  |

______________________________________________________________________

## WebSocket Protocol

Endpoint: `/ws`

### Client Messages

| Type              | Payload           | Description                |
| ----------------- | ----------------- | -------------------------- |
| `PING`            | {}                | Keep-alive                 |
| `BOARD_SUBSCRIBE` | {}                | Request initial board sync |
| `RUN_START`       | { task_id, mode } | Start an agent execution   |
| `RUN_CANCEL`      | { task_id }       | Cancel a running agent     |

### Server Messages

| Type            | Payload                 | Description                            |
| --------------- | ----------------------- | -------------------------------------- |
| `PONG`          | {}                      | Keep-alive response                    |
| `BOARD_SYNC`    | { tasks: [] }           | Initial board state                    |
| `TASK_UPDATED`  | { task_id }             | Notification that a task has changed   |
| `RUN_STARTED`   | { session_id, task_id } | Confirmation of execution start        |
| `RUN_CANCELLED` | { task_id }             | Confirmation of execution cancellation |
| `RUN_ERROR`     | { error }               | Error during run management            |

______________________________________________________________________

## Web UI Serving

When `kagan web` is used, the API server starts in `web_ui=True` mode and mounts the bundled SPA.

### Mount strategy

- `create_api_server()` registers REST/chat/websocket routes first.
- `register_web_ui(mcp)` is called last so SPA fallback has the lowest route priority.
- `_web_ui.py` mounts `_SPAStaticFiles` at `/`.

### SPA fallback behavior

`_SPAStaticFiles` serves static files directly and falls back to `index.html` for client routes.

Reserved prefixes bypass fallback and stay server-owned:

- `/api/`
- `/health`
- `/ws`
- `/mcp`
- `/sse`

### Build pipeline

Web assets are generated and copied into the Python package:

```bash
uv run poe web-build
```

This flows from `packages/web/build/` into `src/kagan/server/_web_static/` via `scripts/build_web_ui.sh`.

### Bundled mode behavior

- `kagan web` is the supported dashboard mode.
- Browser and API share origin, so the bundled dashboard bootstraps from `/health` and connects to `/ws` directly.
- `--host 0.0.0.0` allows LAN access to that same local dashboard server; there is no separate remote pairing flow.

For web-client internals (stores, routing, components), see `docs/internal/architecture/web.md`.
