# Unified Client Architecture

> **"Simple is better than complex"** — Guido van Rossum

## Executive Summary

This document proposes a **breaking change** to unify all Kagan clients under a single architecture. The current mess of divergent access patterns (TUI→KaganCore, Web→HTTP, MCP→KaganCore, EventBus vs SSE) will be replaced with **one obvious way to do it**.

```
BEFORE:                          AFTER:
┌─────────┐                      ┌─────────┐
│   TUI   │──→ KaganCore         │   TUI   │──→ UnifiedClient ──→ Server
└─────────┘                      └─────────┘
┌─────────┐                      ┌─────────┐
│   MCP   │──→ KaganCore         │   MCP   │──→ UnifiedClient ──→ Server
└─────────┘                      └─────────┘
┌─────────┐                      ┌─────────┐
│   Web   │──→ HTTP API          │   Web   │──→ UnifiedClient ──→ Server
└─────────┘                      └─────────┘
┌─────────┐                      ┌─────────┐
│ VS Code │──→ HTTP API          │ VS Code │──→ UnifiedClient ──→ Server
└─────────┘                      └─────────┘

EventBus ←──→ SSE (two systems)      SSE ONLY (one system)
```

______________________________________________________________________

## 1. Why Breaking Change Is Better Than Compatibility

### The Current Mess

| Client  | Access Pattern     | Event System                 | Problems                                                    |
| ------- | ------------------ | ---------------------------- | ----------------------------------------------------------- |
| TUI     | Direct `KaganCore` | `EventBus` + DB polling      | Can't run standalone; events don't cross process boundaries |
| MCP     | Direct `KaganCore` | `EventBus` (in-process only) | No remote MCP possible; lifetime tied to server             |
| Web     | HTTP API           | SSE                          | Must have running server; good citizen                      |
| VS Code | HTTP API           | SSE                          | Must have running server; good citizen                      |

**The tragedy**: We have TWO event systems (`EventBus` for in-process, SSE for HTTP) and TWO access patterns (direct core vs HTTP). This creates:

1. **Duplicated logic** — Same features implemented twice
1. **Inconsistent behavior** — TUI sees events Web doesn't (and vice versa)
1. **Testing nightmare** — Four paths to test for every feature
1. **Mental overhead** — Developers must choose "which way" to access data

### The Zen of Python Applied

> "There should be one—and preferably only one—obvious way to do it."

**Breaking change is the kinder choice** because:

1. **Immediate clarity** — New developers learn ONE pattern, not four
1. **True test coverage** — Test the unified path once, it works everywhere
1. **Architectural integrity** — The system has coherent boundaries
1. **Future extensibility** — New clients (mobile? CLI remote?) use the same interface

> "Special cases aren't special enough to break the rules."

TUI and MCP are not special. They should use the same interface as Web and VS Code.

______________________________________________________________________

## 2. Clean Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐                        │
│  │   TUI   │  │   Web   │  │ VS Code │  │   MCP   │                        │
│  │ (local) │  │ (remote)│  │ (remote)│  │ (local/ │                        │
│  │         │  │         │  │         │  │  remote)│                        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘                        │
│       │            │            │            │                              │
│       └────────────┴────────────┴────────────┘                              │
│                         │                                                   │
│                         ▼                                                   │
│              ┌─────────────────────┐                                        │
│              │   UnifiedClient     │  ← ONE interface for ALL clients       │
│              │  (kagan.server.client)     │                                        │
│              └──────────┬──────────┘                                        │
│                         │                                                   │
│       ┌─────────────────┼─────────────────┐                                 │
│       │                 │                 │                                 │
│       ▼                 ▼                 ▼                                 │
│  ┌─────────┐      ┌─────────┐      ┌─────────┐                             │
│  │  Unix   │      │   TCP   │      │  stdio  │  ← Transport adapters        │
│  │ Socket  │      │ (HTTP)  │      │ (MCP)   │                             │
│  │(local)  │      │(remote) │      │(local)  │                             │
│  └────┬────┘      └────┬────┘      └────┬────┘                             │
│       │                │                │                                   │
└───────┼────────────────┼────────────────┼───────────────────────────────────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SERVER LAYER                                    │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        KaganServer                                   │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│   │  │   REST API  │  │  SSE Stream │  │  MCP Tools  │  │  Chat API  │  │   │
│   │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│   │                                                                      │   │
│   │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│   │  │                     KaganCore (internal)                       │ │   │
│   │  │         Single source of truth — NO external access            │ │   │
│   │  └─────────────────────────────────────────────────────────────────┘ │   │
│   │                                                                      │   │
│   │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│   │  │                     EventStream (SSE only)                     │ │   │
│   │  │         One event system for ALL clients (no EventBus)         │ │   │
│   │  └─────────────────────────────────────────────────────────────────┘ │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Transport Selection Logic

```python
# Pseudocode for transport selection
def create_client(config: ClientConfig) -> UnifiedClient:
    if config.transport == Transport.AUTO:
        # Try Unix socket first (fastest, local-only)
        if unix_socket_exists():
            return UnixSocketClient(config)
        # Fall back to TCP (works everywhere)
        return HttpClient(config)
    elif config.transport == Transport.STDIO:
        # MCP stdio transport (local, parent-child process)
        return StdioClient(config)
    elif config.transport == Transport.UNIX_SOCKET:
        return UnixSocketClient(config)
    elif config.transport == Transport.HTTP:
        return HttpClient(config)
```

______________________________________________________________________

## 3. New Unified Client Interface

### 3.1 Python Interface (`kagan.server.client`)

```python
"""Unified client interface — the ONLY way to access Kagan.

This module provides a single, consistent interface for ALL clients:
- TUI: Uses UnixSocketClient (embedded server)
- MCP: Uses StdioClient OR UnixSocketClient (configurable)
- Web/VS Code: Uses HttpClient (remote or local)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any, AsyncIterator, Protocol


class Transport(StrEnum):
    """Available transport mechanisms."""

    AUTO = auto()  # Try Unix socket, fall back to HTTP
    UNIX_SOCKET = auto()  # Local Unix domain socket (fastest)
    HTTP = auto()  # HTTP/TCP (universal)
    STDIO = auto()  # MCP stdio transport


@dataclass(frozen=True, slots=True)
class ClientConfig:
    """Configuration for UnifiedClient."""

    transport: Transport = Transport.AUTO
    # For HTTP transport
    base_url: str = "http://127.0.0.1:8765"
    token: str | None = None  # For remote auth
    # For Unix socket transport
    socket_path: str | None = None  # Default: ~/.kagan/kagan.sock
    # For stdio transport (MCP)
    server_process: Any | None = None  # Subprocess handle


# ═══════════════════════════════════════════════════════════════════════════════
# Unified Client Interface
# ═══════════════════════════════════════════════════════════════════════════════


class UnifiedClient(ABC):
    """Abstract base for ALL Kagan clients.

    This is the ONE interface. All clients (TUI, MCP, Web, VS Code) use this.
    No more direct KaganCore access outside the server process.
    """

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to server."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connection and cleanup."""
        ...

    async def __aenter__(self) -> UnifiedClient:
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def list_tasks(self, *, status: TaskStatus | None = None) -> list[Task]:
        """List tasks, optionally filtered by status."""
        ...

    @abstractmethod
    async def get_task(self, task_id: str) -> Task:
        """Get a single task by ID."""
        ...

    @abstractmethod
    async def create_task(
        self,
        title: str,
        *,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> Task:
        """Create a new task."""
        ...

    @abstractmethod
    async def update_task(self, task_id: str, **fields) -> Task:
        """Update task fields."""
        ...

    @abstractmethod
    async def delete_task(self, task_id: str) -> None:
        """Delete a task."""
        ...

    @abstractmethod
    async def set_task_status(self, task_id: str, status: TaskStatus) -> Task:
        """Move task to a new status column."""
        ...

    @abstractmethod
    async def run_task(
        self,
        task_id: str,
        *,
        agent_backend: str | None = None,
        launcher: str | None = None,
        persona: str | None = None,
    ) -> Task:
        """Start an agent on a task."""
        ...

    @abstractmethod
    async def cancel_task(self, task_id: str) -> Task:
        """Cancel a running task session."""
        ...

    @abstractmethod
    async def get_task_events(
        self,
        task_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        tail: bool = False,
    ) -> list[Event]:
        """Get task session events."""
        ...

    @abstractmethod
    async def get_task_sessions(self, task_id: str) -> list[TaskSession]:
        """Get all sessions for a task."""
        ...

    # ── Projects ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def list_projects(self) -> list[Project]:
        """List all projects."""
        ...

    @abstractmethod
    async def get_project(self, project_id: str) -> Project:
        """Get a project by ID."""
        ...

    @abstractmethod
    async def create_project(self, name: str) -> Project:
        """Create a new project."""
        ...

    @abstractmethod
    async def delete_project(self, project_id: str) -> None:
        """Delete a project."""
        ...

    @abstractmethod
    async def activate_project(self, project_id: str) -> None:
        """Set the active project."""
        ...

    @abstractmethod
    async def list_project_repos(self, project_id: str) -> list[Repository]:
        """List repositories in a project."""
        ...

    # ── Reviews ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_review(self, task_id: str) -> Review:
        """Get review status for a task."""
        ...

    @abstractmethod
    async def approve_review(self, task_id: str) -> Task:
        """Approve a task for merge."""
        ...

    @abstractmethod
    async def reject_review(self, task_id: str, feedback: str) -> Task:
        """Reject a task with feedback."""
        ...

    @abstractmethod
    async def merge_review(self, task_id: str) -> Task:
        """Merge an approved task."""
        ...

    # ── Settings ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_settings(self) -> dict[str, str]:
        """Get all settings."""
        ...

    @abstractmethod
    async def set_settings(self, settings: dict[str, str]) -> None:
        """Update settings."""
        ...

    @abstractmethod
    async def get_resolved_settings(self) -> ResolvedSettings:
        """Get settings with defaults resolved."""
        ...

    # ── Events (SSE Stream) ───────────────────────────────────────────────────

    @abstractmethod
    async def stream_events(
        self,
        *,
        client_type: str = "client",
        client_id: str | None = None,
    ) -> AsyncIterator[EventMessage]:
        """Subscribe to the unified event stream.

        This is the ONLY event mechanism. No more EventBus.
        """
        ...

    # ── Health & Preflight ────────────────────────────────────────────────────

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Check server health."""
        ...

    @abstractmethod
    async def preflight(self, *, agent_backend: str | None = None) -> list[PreflightCheck]:
        """Run preflight checks."""
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Concrete Implementations
# ═══════════════════════════════════════════════════════════════════════════════


class HttpClient(UnifiedClient):
    """HTTP transport client — for Web, VS Code, and remote access."""

    def __init__(self, config: ClientConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._token = config.token
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        import aiohttp

        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._session = aiohttp.ClientSession(headers=headers)

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        """Make HTTP request and unwrap envelope."""
        url = f"{self._base_url}{path}"
        async with self._session.request(method, url, **kwargs) as resp:
            envelope = await resp.json()
            if not envelope.get("ok"):
                raise ApiError(envelope.get("error", "Unknown error"))
            return envelope.get("data")

    async def list_tasks(self, *, status: TaskStatus | None = None) -> list[Task]:
        query = f"?status={status.value}" if status else ""
        data = await self._request("GET", f"/api/tasks{query}")
        return [Task.model_validate(t) for t in data]

    # ... all other methods follow same pattern

    async def stream_events(
        self,
        *,
        client_type: str = "client",
        client_id: str | None = None,
    ) -> AsyncIterator[EventMessage]:
        """Connect to SSE endpoint and yield events."""
        import aiohttp

        params = {"client_type": client_type}
        if client_id:
            params["client_id"] = client_id

        url = f"{self._base_url}/api/events/stream"

        async with self._session.get(url, params=params) as resp:
            # SSE parsing logic
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if line.startswith("data: "):
                    yield EventMessage.model_validate_json(line[6:])


class UnixSocketClient(HttpClient):
    """Unix domain socket client — for TUI (fastest local transport).

    Uses HTTP over Unix socket (supported by aiohttp and requests-unixsocket).
    Same protocol, zero TCP overhead, no port conflicts.
    """

    def __init__(self, config: ClientConfig) -> None:
        import aiohttp

        socket_path = config.socket_path or default_socket_path()

        # aiohttp supports Unix sockets via connector
        self._connector = aiohttp.UnixConnector(path=socket_path)
        self._session: aiohttp.ClientSession | None = None
        self._base_url = "http://localhost"  # Dummy, socket path matters

    async def connect(self) -> None:
        import aiohttp

        headers = {"Accept": "application/json"}
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            headers=headers,
        )


class StdioClient(UnifiedClient):
    """MCP stdio transport — for MCP server integration.

    Communicates with parent process via JSON-RPC over stdin/stdout.
    Implements the same UnifiedClient interface.
    """

    def __init__(self, config: ClientConfig) -> None:
        self._server = config.server_process
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def connect(self) -> None:
        """Start reading from stdout."""
        asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Read JSON-RPC responses from server stdout."""
        while True:
            line = await self._server.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if "id" in msg and msg["id"] in self._pending:
                future = self._pending.pop(msg["id"])
                if "error" in msg:
                    future.set_exception(ApiError(msg["error"]))
                else:
                    future.set_result(msg["result"])

    async def _request(self, method: str, params: dict | None = None) -> Any:
        """Send JSON-RPC request."""
        self._request_id += 1
        req_id = self._request_id

        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        future = asyncio.Future()
        self._pending[req_id] = future

        self._server.stdin.write(json.dumps(msg).encode() + b"\n")
        await self._server.stdin.drain()

        return await future

    async def list_tasks(self, *, status: TaskStatus | None = None) -> list[Task]:
        data = await self._request("tasks/list", {"status": status.value if status else None})
        return [Task.model_validate(t) for t in data]

    # ... other methods map to JSON-RPC calls


# ═══════════════════════════════════════════════════════════════════════════════
# Factory Function
# ═══════════════════════════════════════════════════════════════════════════════


def create_client(config: ClientConfig | None = None) -> UnifiedClient:
    """Factory — create appropriate client based on config.

    This is the ONLY entry point for creating clients.
    """
    config = config or ClientConfig()

    if config.transport == Transport.AUTO:
        socket_path = config.socket_path or default_socket_path()
        if os.path.exists(socket_path):
            return UnixSocketClient(config)
        return HttpClient(config)

    if config.transport == Transport.UNIX_SOCKET:
        return UnixSocketClient(config)

    if config.transport == Transport.HTTP:
        return HttpClient(config)

    if config.transport == Transport.STDIO:
        return StdioClient(config)

    raise ValueError(f"Unknown transport: {config.transport}")


# Convenience exports
__all__ = [
    "ClientConfig",
    "HttpClient",
    "StdioClient",
    "Transport",
    "UnifiedClient",
    "UnixSocketClient",
    "create_client",
]
```

### 3.2 Server Embedded Mode (for TUI)

```python
"""Embedded server for TUI — server runs in-process, client uses Unix socket."""

import tempfile
from pathlib import Path


class EmbeddedServer:
    """Server that runs embedded in the TUI process.

    TUI starts this, then connects via Unix socket like any other client.
    This maintains the unified architecture while avoiding TCP ports.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_db_path()
        self._socket_path: Path | None = None
        self._server_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> Path:
        """Start embedded server, return socket path for client connection."""
        # Create temp socket path
        self._socket_path = Path(tempfile.gettempdir()) / f"kagan-{os.getpid()}.sock"

        # Clean up old socket if exists
        if self._socket_path.exists():
            self._socket_path.unlink()

        # Create server with Unix socket binding
        self._server_task = asyncio.create_task(self._run_server())

        # Wait for socket to exist
        for _ in range(100):  # Max 1 second
            if self._socket_path.exists():
                return self._socket_path
            await asyncio.sleep(0.01)

        raise RuntimeError("Server failed to start")

    async def _run_server(self) -> None:
        """Run the actual server."""
        from kagan.server import create_api_server, ApiServerOptions
        from kagan.server.mcp.server import ServerOptions

        opts = ApiServerOptions(
            mcp_opts=ServerOptions(db_path=str(self._db_path)),
            # No host/port — Unix socket only
        )

        mcp = create_api_server(opts)

        # Bind to Unix socket instead of TCP
        server = await asyncio.start_unix_server(
            self._handle_connection,
            path=str(self._socket_path),
        )

        try:
            await self._shutdown_event.wait()
        finally:
            server.close()
            await server.wait_closed()

    async def stop(self) -> None:
        """Shutdown embedded server."""
        self._shutdown_event.set()
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
        if self._socket_path and self._socket_path.exists():
            self._socket_path.unlink()


# Usage in TUI app.py:
class KaganApp(App[None]):
    async def on_mount(self) -> None:
        # Start embedded server
        self._embedded = EmbeddedServer(db_path=self._db_path)
        socket_path = await self._embedded.start()

        # Connect via Unix socket (same as any client)
        from kagan.server.client import create_client, ClientConfig, Transport

        self.client = create_client(
            ClientConfig(
                transport=Transport.UNIX_SOCKET,
                socket_path=str(socket_path),
            )
        )
        await self.client.connect()

    async def on_unmount(self) -> None:
        await self.client.close()
        await self._embedded.stop()
```

### 3.3 TypeScript Interface (Web/VS Code)

```typescript
// lib/client/types.ts — shared type definitions

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  // ... other fields
}

export interface EventMessage {
  type: 'TASK_CREATED' | 'TASK_UPDATED' | 'TASK_DELETED' | 'SESSION_EVENT' | 'SETTINGS_CHANGED';
  task_id?: string;
  payload?: unknown;
}

export interface ClientConfig {
  baseUrl: string;
  token?: string;
  // For future: socket paths, custom transports
}

// lib/client/unified-client.ts — the ONE client

export abstract class UnifiedClient {
  protected config: ClientConfig;

  constructor(config: ClientConfig) {
    this.config = config;
  }

  // Lifecycle
  abstract connect(): Promise<void>;
  abstract close(): Promise<void>;

  // Tasks
  abstract listTasks(status?: TaskStatus): Promise<Task[]>;
  abstract getTask(taskId: string): Promise<Task>;
  abstract createTask(input: CreateTaskInput): Promise<Task>;
  abstract updateTask(taskId: string, input: UpdateTaskInput): Promise<Task>;
  abstract deleteTask(taskId: string): Promise<void>;
  abstract setTaskStatus(taskId: string, status: TaskStatus): Promise<Task>;
  abstract runTask(taskId: string, options?: RunTaskOptions): Promise<Task>;
  abstract cancelTask(taskId: string): Promise<Task>;

  // Projects
  abstract listProjects(): Promise<Project[]>;
  abstract createProject(name: string): Promise<Project>;
  abstract activateProject(projectId: string): Promise<void>;

  // Reviews
  abstract getReview(taskId: string): Promise<ReviewStatus>;
  abstract approveReview(taskId: string): Promise<Task>;
  abstract rejectReview(taskId: string, feedback: string): Promise<Task>;
  abstract mergeReview(taskId: string): Promise<Task>;

  // Settings
  abstract getSettings(): Promise<Record<string, string>>;
  abstract setSettings(settings: Record<string, string>): Promise<void>;

  // Events — THE ONLY EVENT MECHANISM
  abstract streamEvents(options?: StreamOptions): AsyncGenerator<EventMessage>;

  // Health
  abstract healthCheck(): Promise<HealthStatus>;
}

// HTTP implementation (current KaganApiClient refactored)
export class HttpClient extends UnifiedClient {
  private abortController = new AbortController();

  async connect(): Promise<void> {
    // Verify connection works
    await this.healthCheck();
  }

  async close(): Promise<void> {
    this.abortController.abort();
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const response = await fetch(`${this.config.baseUrl}${path}`, {
      method,
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...(this.config.token ? { 'Authorization': `Bearer ${this.config.token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: this.abortController.signal,
    });

    const envelope = await response.json();
    if (!envelope.ok) {
      throw new ApiError(response.status, envelope.error);
    }
    return envelope.data;
  }

  async listTasks(status?: TaskStatus): Promise<Task[]> {
    const query = status ? `?status=${status}` : '';
    return this.request<Task[]>(`/api/tasks${query}`);
  }

  // ... other methods

  async *streamEvents(options?: StreamOptions): AsyncGenerator<EventMessage> {
    const params = new URLSearchParams();
    params.set('client_type', options?.clientType ?? 'web');
    if (options?.clientId) {
      params.set('client_id', options.clientId);
    }

    const response = await fetch(
      `${this.config.baseUrl}/api/events/stream?${params}`,
      {
        headers: {
          'Accept': 'text/event-stream',
          ...(this.config.token ? { 'Authorization': `Bearer ${this.config.token}` } : {}),
        },
      }
    );

    if (!response.body) {
      throw new Error('No response body');
    }

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += value;
        const parts = buffer.split('\n\n');
        buffer = parts.pop()!;

        for (const part of parts) {
          const dataLine = part.split('\n').find(l => l.startsWith('data: '));
          if (dataLine) {
            yield JSON.parse(dataLine.slice(6));
          }
        }
      }
    } finally {
      reader.cancel().catch(() => {});
    }
  }
}

// Factory
export function createClient(config: ClientConfig): UnifiedClient {
  // For now, only HTTP. WebSocket or other transports can be added later
  // while maintaining the same interface.
  return new HttpClient(config);
}
```

______________________________________________________________________

## 4. Migration Guide

### 4.1 TUI Migration

**Current (mess):**

```python
# src/kagan/tui/app.py
from kagan.core import KaganCore


class KaganApp(App[None]):
    def __init__(self, db_path: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.core = KaganCore(db_path=db_path)  # ← Direct access!
```

**After (clean):**

```python
# src/kagan/tui/app.py
from kagan.server.client import create_client, ClientConfig, Transport
from kagan.server.embedded import EmbeddedServer


class KaganApp(App[None]):
    def __init__(self, db_path: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._db_path = db_path
        self._embedded: EmbeddedServer | None = None
        self.client: UnifiedClient | None = None

    async def on_mount(self) -> None:
        # 1. Start embedded server
        self._embedded = EmbeddedServer(db_path=self._db_path)
        socket_path = await self._embedded.start()

        # 2. Connect via Unix socket (same interface as everyone else!)
        self.client = create_client(
            ClientConfig(
                transport=Transport.UNIX_SOCKET,
                socket_path=str(socket_path),
            )
        )
        await self.client.connect()

    async def on_unmount(self) -> None:
        await self.client.close()
        await self._embedded.stop()
```

**Screen migration pattern:**

```python
# BEFORE: Direct core access
class KanbanScreen(Screen):
    @property
    def core(self) -> KaganCore:
        return self.app.core  # ← Direct access

    async def load_tasks(self) -> None:
        tasks = await self.core.tasks.list()  # ← Direct method call


# AFTER: Unified client
class KanbanScreen(Screen):
    @property
    def client(self) -> UnifiedClient:
        return self.app.client  # ← Same interface as Web/VS Code!

    async def load_tasks(self) -> None:
        tasks = await self.client.list_tasks()  # ← Same method!
```

### 4.2 MCP Migration

**Current (mess):**

```python
# src/kagan/mcp/server.py
from kagan.core import KaganCore


@asynccontextmanager
async def _lifespan(mcp: FastMCP) -> AsyncIterator[ServerContext]:
    client = KaganCore(db_path=opts.db_path)  # ← Direct access
    ctx = ServerContext(client=client, opts=opts)
    yield ctx
    client.close()


# Tool implementation
@tool
def task_get(ctx: Context, task_id: str) -> dict:
    server_ctx = get_context(ctx)
    task = await server_ctx.client.tasks.get(task_id)  # ← Direct core
    return {"task": task_to_dict(task)}
```

**After (clean) — Option A: MCP uses embedded server:**

```python
# src/kagan/mcp/server.py
from kagan.server.client import create_client, ClientConfig, Transport
from kagan.server.embedded import EmbeddedServer


@asynccontextmanager
async def _lifespan(mcp: FastMCP) -> AsyncIterator[ServerContext]:
    # Start embedded server
    embedded = EmbeddedServer(db_path=opts.db_path)
    socket_path = await embedded.start()

    # Connect via Unix socket
    client = create_client(
        ClientConfig(
            transport=Transport.UNIX_SOCKET,
            socket_path=str(socket_path),
        )
    )
    await client.connect()

    ctx = ServerContext(client=client, embedded=embedded, opts=opts)
    try:
        yield ctx
    finally:
        await client.close()
        await embedded.stop()


# Tool implementation — SAME as TUI/Web/VS Code
@tool
def task_get(ctx: Context, task_id: str) -> dict:
    server_ctx = get_context(ctx)
    task = await server_ctx.client.get_task(task_id)  # ← Unified interface!
    return {"task": task_to_dict(task)}
```

**After (clean) — Option B: MCP connects to external server:**

```python
# MCP can connect to an already-running server via HTTP or Unix socket
@asynccontextmanager
async def _lifespan(mcp: FastMCP) -> AsyncIterator[ServerContext]:
    # Connect to external server (configured via env var)
    client = create_client(
        ClientConfig(
            transport=Transport.AUTO,  # Try Unix socket, fall back to HTTP
            socket_path=os.environ.get("KAGAN_SOCKET_PATH"),
            base_url=os.environ.get("KAGAN_SERVER_URL", "http://127.0.0.1:8765"),
        )
    )
    await client.connect()

    ctx = ServerContext(client=client, opts=opts)
    try:
        yield ctx
    finally:
        await client.close()
```

### 4.3 Web Migration

**Current (already using HTTP, but ad-hoc):**

```typescript
// packages/web/src/lib/api/client.ts
export class KaganApiClient {
  // Custom methods, no shared interface
  async getTasks(status?: TaskStatus): Promise<WireTask[]> {
    return this.request<WireTask[]>(`/api/tasks${query}`);
  }
}
```

**After (implements UnifiedClient):**

```typescript
// packages/web/src/lib/client/unified-client.ts
import { UnifiedClient, HttpClient } from './unified-client';

// Refactor KaganApiClient to extend HttpClient
export class KaganApiClient extends HttpClient {
  // Already implements UnifiedClient interface!
  // Just need to align method names and signatures
}

// Export singleton
export const apiClient = createClient({
  baseUrl: '',  // Bundled web mode
});

// Usage in components
import { apiClient } from '@/lib/client/unified-client';

// Before
const tasks = await apiClient.getTasks();

// After (same, just guaranteed interface compliance)
const tasks = await apiClient.listTasks();
```

### 4.4 VS Code Migration

Same as Web — VS Code's `KaganClient` becomes an implementation of `UnifiedClient`.

```typescript
// packages/vscode/src/client/unified-client.ts
import { UnifiedClient } from './types';

export class KaganClient extends UnifiedClient {
  // Existing implementation, just add 'extends'
  // and ensure method names match interface
}
```

### 4.5 Event System Migration

**Current (two systems):**

```python
# EventBus for TUI/MCP (in-process)
from kagan.core._event_bus import EventBus, BusEvent, BusMessage

bus = EventBus()
await bus.publish(BusEvent.TASK_CREATED, task_id=task.id)

# SSE for Web/VS Code (HTTP)
# Completely separate implementation in src/kagan/server/_sse.py
```

**After (ONE system — SSE for all):**

```python
# Delete EventBus entirely.
# All clients connect to SSE endpoint.

# For TUI/MCP (local): SSE over Unix socket
# For Web/VS Code (remote): SSE over HTTP

# Unified SSE endpoint already exists at /api/events/stream
# Just ensure it works over Unix sockets too.
```

______________________________________________________________________

## 5. Deleted Code Inventory

### 5.1 Files to Delete

| File                                     | Reason                                      |
| ---------------------------------------- | ------------------------------------------- |
| `src/kagan/core/_event_bus.py`           | EventBus replaced by SSE for all clients    |
| `src/kagan/core/client.py`               | `KaganCore` becomes internal to server only |
| `src/kagan/tui/orchestrator_sessions.py` | Move to unified client                      |
| `packages/web/src/lib/api/sse.ts`        | Consolidate into unified client             |
| `packages/vscode/src/api/sse.ts`         | Consolidate into unified client             |

### 5.2 Public API Changes

**Removed from `kagan.core`:**

```python
# These become INTERNAL (server-only):
-KaganCore  # Move to kagan.server._core
-EventBus  # Delete, use SSE
-BusEvent  # Delete
-BusMessage  # Delete
-DBWatcher  # Move to kagan.server._watcher
```

**New public API:**

```python
# Everything comes from kagan.server.client:
from kagan.server.client import (
    UnifiedClient,  # Abstract interface
    HttpClient,  # HTTP transport
    UnixSocketClient,  # Unix socket transport (TUI)
    StdioClient,  # MCP stdio transport
    ClientConfig,  # Configuration
    Transport,  # Transport enum
    create_client,  # Factory function
)
```

### 5.3 Import Changes

| Before                                       | After                                                          |
| -------------------------------------------- | -------------------------------------------------------------- |
| `from kagan.core import KaganCore`           | `from kagan.server.client import UnifiedClient, create_client` |
| `from kagan.core._event_bus import EventBus` | DELETED — use `client.stream_events()`                         |
| `self.core.tasks.list()`                     | `self.client.list_tasks()`                                     |
| `self.core.projects.create()`                | `self.client.create_project()`                                 |
| `await core.event_bus.subscribe()`           | `async for event in client.stream_events()`                    |

______________________________________________________________________

## 6. Implementation Phases

### Phase 1: Create UnifiedClient Interface

1. Define `UnifiedClient` abstract base class
1. Create `HttpClient` implementation (refactor existing web client)
1. Add comprehensive tests for the interface

### Phase 2: Add Unix Socket Transport

1. Implement `UnixSocketClient`
1. Add Unix socket support to server
1. Test local-only communication

### Phase 3: Migrate TUI

1. Create `EmbeddedServer`
1. Migrate `KaganApp` to use `UnifiedClient`
1. Delete `EventBus` usage
1. Test TUI thoroughly

### Phase 4: Migrate MCP

1. Update MCP lifespan to use `UnifiedClient`
1. Support both embedded and external server modes
1. Test MCP tools

### Phase 5: Cleanup

1. Delete `EventBus`
1. Make `KaganCore` internal to server
1. Update documentation
1. Add migration guide for any external users

______________________________________________________________________

## 7. Benefits Summary

| Aspect                  | Before                                 | After                      |
| ----------------------- | -------------------------------------- | -------------------------- |
| **Client interfaces**   | 4 (KaganCore, HTTP API, EventBus, SSE) | 1 (`UnifiedClient`)        |
| **Event systems**       | 2 (EventBus, SSE)                      | 1 (SSE)                    |
| **Ways to access data** | 4                                      | 1                          |
| **Test paths**          | 4×N                                    | 1×N                        |
| **Lines of code**       | ~5000 (distributed)                    | ~2000 (unified)            |
| **Mental model**        | "Which way should I use?"              | "Always use UnifiedClient" |
| **Remote MCP**          | Impossible                             | Just change transport      |
| **Mocking for tests**   | Multiple approaches                    | One interface to mock      |

______________________________________________________________________

## 8. Closing Thoughts

> "Readability counts."

The unified architecture makes Kagan's code readable again. A new developer can understand the entire client-server relationship by reading one file (`kagan/client/__init__.py`).

> "Simple is better than complex."

One client. One event stream. One way to do it.

> "Complex is better than complicated."

If we need complexity (caching, offline mode, optimistic updates), we add it in ONE place — the `UnifiedClient` — and all clients benefit.

> "Now is better than never."

Breaking changes are scary, but every day we wait, the divergence grows. The time to unify is now.

______________________________________________________________________

**Status:** Architecture Proposal
**Author:** Guido van Rossum (via AI)
**Date:** 2026-03-29
**Breaking Change:** Yes
**Migration Effort:** Medium (2-3 weeks)
**Long-term Value:** High
