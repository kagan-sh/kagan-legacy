# Server Features — `kagan.server`

*The Kagan API server provides the bundled dashboard surface plus optional API-client access via REST and WebSockets.*

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

## Pairing Remote Clients

Kagan uses a secure pairing mechanism to authorize remote API clients:

1. Start the server. A QR code and pairing URI will be printed to the terminal.
1. Pair the client against `/auth/pair` using the printed secret or URI.
1. The client receives a long-lived auth token for subsequent REST and WebSocket calls.

### Security

The pairing secret is generated at startup and is valid for a single session. Authorization is managed via `Bearer` tokens in the `Authorization` header.

______________________________________________________________________

## Using the REST API

The API provides endpoints for managing the board, projects, and task lifecycles.

### Health Check

```bash
curl http://localhost:8765/health
```

### Listing Tasks

```bash
curl -H "Authorization: Bearer <TOKEN>" http://localhost:8765/api/tasks
```

### Creating a Task

```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"title": "Implement feature X"}' \
     http://localhost:8765/api/tasks
```

### Updating a Task

```bash
curl -X PATCH -H "Authorization: Bearer <TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"priority": "HIGH"}' \
     http://localhost:8765/api/tasks/<TASK_ID>
```

### Moving a Task

```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"status": "IN_PROGRESS"}' \
     http://localhost:8765/api/tasks/<TASK_ID>/status
```

______________________________________________________________________

## WebSocket Connection

The WebSocket stream provides real-time updates for the board and agent executions.

### Handshake

Clients must authenticate immediately after connecting:

```json
{ "t": "AUTH", "token": "<TOKEN>" }
```

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

### Invalid Token

If you see 401 Unauthorized errors, re-pair the device by restarting the server and scanning the new QR code. Tokens are stored locally on the device and validated against the current server instance.
