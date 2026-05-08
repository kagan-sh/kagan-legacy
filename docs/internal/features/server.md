# Server Features — `kagan.server`

*The Kagan API server provides the bundled dashboard surface plus local REST and SSE access.*

______________________________________________________________________

## Starting the Server

The server is launched via the Kagan CLI:

```bash
kagan serve [--port 8765] [--host 127.0.0.1]
```

By default, the server binds to `127.0.0.1:8765`. To allow remote access from other devices, bind to `0.0.0.0`:

```bash
kagan serve --host 0.0.0.0
```

### Access Tiers

REST API endpoints use access tiers for HTTP-level authorization:

- **Standard** (default): Normal board management and run execution.
- **Readonly** (`--readonly`): No mutations allowed; only read access to projects and tasks.
- **Admin** (`--admin`): Enables destructive actions (delete task, create/delete project).

MCP tools use AgentRole (WORKER/REVIEWER/ORCHESTRATOR) instead of these tiers. See `docs/internal/architecture/mcp.md` for the role-based model.

______________________________________________________________________

## Using the REST API

The API provides endpoints for managing the board, projects, and task lifecycles.

### Health Check

```bash
curl http://localhost:8765/health
```

### Listing Tasks

```bash
curl http://localhost:8765/api/tasks
```

### Creating a Task

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"title": "Implement feature X"}' \
     http://localhost:8765/api/tasks
```

### Updating a Task

```bash
curl -X PATCH -H "Content-Type: application/json" \
     -d '{"priority": "HIGH"}' \
     http://localhost:8765/api/tasks/<TASK_ID>
```

### Moving a Task

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"status": "IN_PROGRESS"}' \
     http://localhost:8765/api/tasks/<TASK_ID>/status
```

______________________________________________________________________

## Real-time Event Stream

The SSE event stream provides real-time updates for board and agent executions.

### Subscribing to updates

Connect to the SSE endpoint to receive board and session events:

```bash
curl -N http://localhost:8765/api/events/stream
```

Event types pushed by the server:

| `type` field    | Description                                     |
| --------------- | ----------------------------------------------- |
| `TASK_UPDATED`  | A task was created, updated, or deleted         |
| `SESSION_EVENT` | Agent session event (output, tool call, status) |

Keepalive comments (`: keepalive`) are sent every 25 seconds.

Clients can also publish lightweight presence context:

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"client_id":"web-tab-1","client_type":"web","active_task_id":"task-123"}' \
     http://localhost:8765/api/presence/heartbeat
```

### Managing Runs

Start an agent run via REST:

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{}' \
     http://localhost:8765/api/tasks/<TASK_ID>/run
```

Cancel a running agent:

```bash
curl -X POST http://localhost:8765/api/tasks/<TASK_ID>/cancel
```

______________________________________________________________________

## Chat Streaming

Chat sessions are managed via REST and streamed in real time over SSE.

### Creating a session

```bash
curl -X POST http://localhost:8765/api/chat/sessions
```

### Sending a message (streamed response)

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"text": "Explain the auth flow"}' \
     http://localhost:8765/api/chat/<SESSION_ID>/stream
```

### Interrupting a turn

```bash
curl -X POST http://localhost:8765/api/chat/<SESSION_ID>/interrupt
```

### SSE events

Once a session is active, the server pushes streaming events over SSE:

| Event                     | Description                        |
| ------------------------- | ---------------------------------- |
| `CHAT_SUBSCRIBED`         | Client subscribed to the session   |
| `CHAT_CHUNK`              | Incremental text from the agent    |
| `CHAT_TOOL_START`         | Agent initiated a tool call        |
| `CHAT_TOOL_PROGRESS`      | Tool call status update            |
| `CHAT_DONE`               | Agent turn completed               |
| `CHAT_ERROR`              | Agent turn failed                  |
| `CHAT_INTERRUPTED`        | Turn stopped by user interrupt     |
| `CHAT_SESSION_UPDATED`    | Session title or metadata changed  |
| `CHAT_BUSY`               | Agent busy on another turn         |
| `TOOL_PERMISSION_REQUEST` | Agent is waiting for tool approval |

______________________________________________________________________

## Integration Routes

Integrations can be checked and imported via REST without restarting the server.

### List integrations

Returns all enabled integrations:

```bash
curl http://localhost:8765/api/integrations
```

### Preflight check (per integration)

Returns readiness status for a specific integration:

```bash
curl http://localhost:8765/api/integrations/{name}/preflight
```

### Preview

Preview items from a specific integration without importing:

```bash
curl "http://localhost:8765/api/integrations/{name}/preview?repo=owner/repo"
```

### Sync

Sync items from an integration into the active project:

```bash
curl -X POST "http://localhost:8765/api/integrations/{name}/sync?repo=owner/repo"
```

______________________________________________________________________

## Agent Stream Endpoints

The orchestrator-chat overlay is driven by four versioned routes (registered
in `src/kagan/server/_agent_routes.py`).

### Listing running agents

```bash
curl http://localhost:8765/api/v1/agents/running
curl "http://localhost:8765/api/v1/agents/running?project_id=<PROJECT_ID>"
```

Returns `RunningAgentsResponse` — an `agents` list of `ActiveAgentRowResponse`
entries (task / session join with timing and token counters), sorted by
`started_at` descending.

*Tests:* `tests/server/test_running_agents_route.py`.

### Replaying a session

```bash
curl "http://localhost:8765/api/v1/sessions/<SESSION_ID>/replay?limit=200&direction=forward"
curl "http://localhost:8765/api/v1/sessions/<SESSION_ID>/replay?cursor=<CURSOR>&direction=backward"
```

Returns `SessionReplayPage` — an ordered `events` list, a `next_cursor`
(format: `created_at|id`), and `has_more`. `direction` is `forward` (default)
or `backward`; `limit` is bounded at 1000.

*Tests:* `tests/server/test_session_replay_route.py`.

______________________________________________________________________

## Analytics Routes

Registered in `src/kagan/server/_analytics_routes.py`. All endpoints require an active project context — if none is set, they return an empty list or object rather than erroring. Used by backend selection, VS Code commands, and external clients.

| Endpoint                                                          | Purpose                                                                                             |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `GET /api/analytics/backend-stats`                                | Per-backend aggregates (sessions, success rate, duration) for the active project.                   |
| `GET /api/analytics/session-timeline?days=N`                      | Daily session counts over the last `N` days (default 30).                                           |
| `GET /api/analytics/timeline-summary?days=N`                      | Rolled-up timeline aggregates over `N` days (default 30).                                           |
| `GET /api/analytics/recommended-backend`                          | Simple recommendation: the backend with the highest success rate for this project.                  |
| `GET /api/analytics/export?days=N`                                | Combined export blob (backend stats + session timeline) over `N` days — used for download/share.    |
| `GET /api/analytics/by-role`                                      | Backend stats grouped by agent role (WORKER/REVIEWER/ORCHESTRATOR).                                 |
| `GET /api/analytics/by-task-type`                                 | Backend stats grouped by task type.                                                                 |
| `GET /api/analytics/by-role-and-task-type?role=&task_type=`       | 3D stats (backend × role × task type), optionally filtered by role and/or task type query params.   |
| `GET /api/analytics/recommend-for-task?title=&description=&role=` | Intelligent backend selection via `BackendSelector` — combines history with task title/description. |

`title` is required on `/recommend-for-task`; omitting it returns a default `claude-code` recommendation with zero confidence.

______________________________________________________________________

## Troubleshooting

### Port Conflicts

If the default port `8765` is in use, use the `--port` flag:

```bash
kagan serve --port 8420
```

### Network Issues

When connecting from another device, ensure both devices can reach each other on the network. Check firewall settings and allow incoming traffic on the configured port.

### Access Issues

If another device cannot reach the server, verify host binding, firewall settings, and the selected port.
