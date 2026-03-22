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

| `type` field     | Description                                       |
| ---------------- | ------------------------------------------------- |
| `TASK_UPDATED`   | A task was created, updated, or deleted            |
| `SESSION_EVENT`  | Agent session event (output, tool call, status)    |

Keepalive comments (`: keepalive`) are sent every 25 seconds.

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

## Plugin Routes

Plugins can be synced and checked via REST without restarting the server.

### Syncing plugins

Triggers discovery and registration of all installed plugins:

```bash
curl -X POST http://localhost:8765/api/plugins/sync
```

### Preflight check

Returns readiness status for each registered plugin:

```bash
curl http://localhost:8765/api/plugins/preflight
```

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
