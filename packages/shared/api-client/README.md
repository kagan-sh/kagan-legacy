# @kagan/shared-api-client

Shared TypeScript API client for Kagan that works in both browser and VS Code extension contexts.

## Overview

This package consolidates the duplicated API client code from:

- `packages/web/src/lib/api/client.ts`
- `packages/vscode/src/api/client.ts`

## Features

- **Platform-agnostic**: Uses native `fetch` API (works in browsers and Node.js 18+)
- **Type-safe**: Full TypeScript support with comprehensive type definitions
- **SSE support**: Automatic reconnection with exponential backoff
- **Auth handling**: Bearer token authentication
- **Error handling**: Typed errors (`ApiError`, `SSEError`, `ConfigurationError`)

## Installation

```bash
pnpm add @kagan/shared-api-client
```

## Usage

### Basic API Client

```typescript
import { KaganApiClient, ApiError } from '@kagan/shared-api-client';

const client = new KaganApiClient({
  baseUrl: "localhost:8765",
  protocol: "http",
  token: "optional-auth-token",
  clientType: "vscode" // or "web"
});

// Get all tasks
const tasks = await client.getTasks();

// Create a task
const task = await client.createTask({
  title: "My new task",
  description: "Task description",
  priority: "HIGH"
});

// Run a task
await client.runTask(task.id);
```

### SSE Event Streaming

```typescript
import { SSEManager } from '@kagan/shared-api-client';

const sse = new SSEManager({
  baseUrl: "localhost:8765",
  protocol: "http",
  token: "my-auth-token",
  clientType: "vscode"
});

sse.connect({
  onMessage: (message) => {
    console.log("Received:", message);
  },
  onConnected: (connected) => {
    console.log("Connected:", connected);
  },
  onError: (error) => {
    console.error("SSE error:", error);
  },
  onPollingFallback: () => {
    // Triggered when SSE disconnects - can poll manually
  }
});

// Cleanup when done
sse.dispose();
```

### Streaming Chat

```typescript
// Stream chat events as async generator
for await (const event of client.streamChat(sessionId, "Hello")) {
  if (event.t === "CHAT_CHUNK") {
    console.log(event.content);
  } else if (event.t === "CHAT_DONE") {
    console.log("Full response:", event.full_response);
  }
}
```

### Error Handling

```typescript
import { ApiError } from '@kagan/shared-api-client';

try {
  await client.getTask("invalid-id");
} catch (error) {
  if (ApiError.isApiError(error)) {
    console.log("Status:", error.status);
    console.log("Detail:", error.detail);
    console.log("Error code:", error.errorCode);

    if (error.isNotFound()) {
      console.log("Task not found");
    }
    if (error.isAuthError()) {
      console.log("Authentication failed");
    }
  }
}
```

## API Reference

### `KaganApiClient`

The main API client class with methods for:

- Tasks: `getTasks`, `createTask`, `updateTask`, `deleteTask`, `runTask`, `cancelTask`
- Projects: `getProjects`, `createProject`, `activateProject`, `deleteProject`
- Repos: `getProjectRepos`, `addProjectRepo`, `deleteProjectRepo`
- Reviews: `getReview`, `reviewDecide`, `getConflicts`
- Chat: `getChatSessions`, `createChatSession`, `streamChat`
- Settings: `getSettings`, `updateSettings`, `getResolvedSettings`
- Filesystem: `browsePath`
- Health: `ping`, `getHealth`, `verifyApi`

### `SSEManager`

Manages Server-Sent Events connection with:

- Automatic reconnection with exponential backoff
- Auth token support
- Polling fallback
- Graceful shutdown

### `streamSSE<T>`

Async generator for one-off SSE streaming:

```typescript
for await (const event of streamSSE<ChatStreamEvent>(url, options)) {
  console.log(event);
}
```

## Differences from Legacy Clients

| Feature           | Web Client    | VS Code Client | Shared Client              |
| ----------------- | ------------- | -------------- | -------------------------- |
| `fetch` API       | ✅            | ✅             | ✅                         |
| Bundled web mode  | ✅            | ❌             | Via config                 |
| Protocol handling | Base URL only | Separate       | Separate (configurable)    |
| SSE reconnection  | Basic         | Advanced       | Advanced (same as VS Code) |
| Error codes       | Basic         | Detailed       | Detailed                   |
| Typed errors      | Partial       | Full           | Full                       |

## Migration Guide

### From Web Client

```typescript
// Before
import { apiClient } from '@/lib/api/client';

// After
import { KaganApiClient } from '@kagan/shared-api-client';
const apiClient = new KaganApiClient({ baseUrl: "" });
```

### From VS Code Client

```typescript
// Before
import { KaganClient } from './api/client';
const client = new KaganClient("localhost:8765", "http", token);

// After
import { KaganApiClient } from '@kagan/shared-api-client';
const client = new KaganApiClient({
  baseUrl: "localhost:8765",
  protocol: "http",
  token,
  clientType: "vscode"
});
```

## License

MIT
