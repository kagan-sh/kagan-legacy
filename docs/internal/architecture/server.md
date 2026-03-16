# Server Architecture — `kagan.server`

*Design principles: FastMCP native, REST + WebSocket, bundled dashboard first, optional API auth.*

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
1. **Optional API Auth** — Pairing and bearer tokens exist for non-bundled API clients only.

______________________________________________________________________

## Internal Structure

```
src/kagan/server/
├── __init__.py        # re-export create_api_server
├── server.py          # ApiServer factory, entry point
├── _auth.py           # Pairing and Bearer token middleware
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
1. Calls `register_auth(mcp)` to install security middleware for non-bundled API clients.
1. Calls `register_websocket(mcp)` to add the real-time stream.

______________________________________________________________________

## Authentication Flow

Kagan uses a two-stage pairing process for non-bundled API clients:

1. **Pairing**:
   - Server generates a one-time `_pairing_secret` at startup.
   - CLI displays a QR code containing the server URI and secret.
   - API client scans QR or submits credentials and POSTs to `/auth/pair`.
   - Server validates secret and returns a long-lived `token`.
1. **Authorization**:
   - `BearerAuthMiddleware` (Starlette) intercepts all API requests (except `/health`, `/auth/pair`).
   - Clients must provide `Authorization: Bearer <token>`.
   - WebSocket handshake also requires an `AUTH` message with the token.

______________________________________________________________________

## REST API Reference

All responses are wrapped in a `WireEnvelope`: `{ ok: bool, data?: T, error?: string }`.

| Endpoint                           | Method | Description                           |
| ---------------------------------- | ------ | ------------------------------------- |
| `/health`                          | GET    | Service health check                  |
| `/auth/pair`                       | POST   | Pair a new API client with secret     |
| `/auth/verify`                     | GET    | Verify validity of bearer token       |
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

### Handshake

1. Client sends: `{ "t": "AUTH", "token": "..." }`
1. Server responds: `{ "t": "AUTH_OK" }` or `{ "t": "AUTH_FAIL" }`

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

- `create_api_server()` registers REST/chat/auth/websocket routes first.
- `register_web_ui(mcp)` is called last so SPA fallback has the lowest route priority.
- `_web_ui.py` mounts `_SPAStaticFiles` at `/`.

### SPA fallback behavior

`_SPAStaticFiles` serves static files directly and falls back to `index.html` for client routes.

Reserved prefixes bypass fallback and stay server-owned:

- `/api/`
- `/auth/`
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

### Bundled mode auth behavior

- In bundled mode, `register_websocket(mcp, require_auth=not opts.web_ui)` disables token handshake.
- Browser and API share origin, so the bundled dashboard bootstraps from `/health` and skips pairing.

For web-client internals (stores, routing, components), see `docs/internal/architecture/web.md`.
