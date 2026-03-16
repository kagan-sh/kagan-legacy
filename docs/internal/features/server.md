# Server Features — `kagan.server`

*The Kagan API server provides the bundled dashboard surface plus local REST and WebSockets access.*

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

The server supports the same access tiers as the MCP server:

- **Standard** (default): Normal board management and run execution.
- **Readonly** (`--readonly`): No mutations allowed; only read access to projects and tasks.
- **Admin** (`--admin`): Enables destructive actions (delete task, create/delete project).

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

## WebSocket Connection

The WebSocket stream provides real-time updates for the board and agent executions.

### Subscribing to Board Updates

To receive initial state and subsequent updates:

```json
{ "t": "BOARD_SUBSCRIBE" }
```

### Managing Runs

Start an agent run:

```json
{ "t": "RUN_START", "task_id": "<TASK_ID>", "mode": "AUTO" }
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
