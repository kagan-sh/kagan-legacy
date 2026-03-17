# Web Architecture -- `packages/web`

*Design principles: React 19 SPA, Jotai state, shadcn/Radix primitives, thin client over Kagan REST and WebSocket APIs.*

______________________________________________________________________

## Context

`packages/web` is the browser client for Kagan. It is a static React SPA built with Vite, bundled into the Python package, and served locally by `kagan web`.

______________________________________________________________________

## Design Principles

1. **Thin client** -- workflow logic stays in Python (`kagan.core`); the web app coordinates API calls and renders state.
1. **Owned primitives** -- shadcn/Radix components live in-repo and are styled through Kagan tokens in `src/app.css`.
1. **Dark-first IDE shell** -- the app uses a persistent activity bar, contextual header, Quick Actions, and workspace panels across routes.
1. **Single integration boundary** -- all server communication flows through `apiClient` (REST) and `kaganWs` (WebSocket).
1. **Route-level workspaces** -- board, task, chat, and settings share common panel/header primitives instead of bespoke page chrome.

______________________________________________________________________

## Internal Structure

```text
packages/web/src/
├── app.css
├── app.tsx
├── main.tsx
├── routes.tsx
├── pages/
│   ├── board-page.tsx
│   ├── task-detail-page.tsx    # unified task workspace (Overview, Changes, Review tabs)
│   ├── session-page.tsx        # legacy redirect target for /session/:taskId
│   ├── chat-page.tsx
│   ├── settings-page.tsx
│   ├── welcome-page.tsx        # onboarding/project setup page
├── components/
│   ├── board/
│   ├── chat/
│   ├── layout/
│   ├── session/
│   ├── settings/
│   ├── shared/
│   └── ui/
└── lib/
    ├── api/
    ├── atoms/
    ├── hooks/
    └── utils/
```

______________________________________________________________________

## Components

### `board/`

- `kanban-board.tsx` -- four-lane board with DnD and filter bar
- `kanban-column.tsx` -- single lane with task card list
- `task-card.tsx` -- card with telemetry, review state, and session indicators
- `board-task-inspector.tsx` -- right-rail inspector panel
- `board-filter-bar.tsx` -- search and status/mode filters
- `agent-control.tsx` -- run/stop/interrupt controls; shows pair instruction dialog before launching PAIR sessions
- `create-task-dialog.tsx`, `edit-task-dialog.tsx`, `task-delete-dialog.tsx` -- task CRUD dialogs
- `diff-viewer.tsx` -- workspace diff renderer
- `review-panel.tsx` -- review approval surface
- `task-metadata-panel.tsx` -- metadata inspector section
- `backlog-list-view.tsx` -- list view for backlog lane
- `plugin-import-dialog.tsx` -- plugin import flow dialog
- `task-sidebar.tsx` -- collapsible task sidebar
- `board-dialogs.tsx` -- shared dialog orchestration for board actions
- `first-boot-tutorial-dialog.tsx` -- first-run onboarding tutorial dialog

### `session/`

- `chat-side-panel.tsx` -- right-rail streaming overlay with lane toggle and LIVE indicator
- `orchestrator-chat-panel.tsx` -- orchestrator conversation with streaming and interrupt
- `event-stream.tsx` -- event list renderer for session output
- `session-picker.tsx` -- global session switcher
- `follow-up-queue.tsx` -- queued follow-up message management
- `task-commits-panel.tsx` -- commit history panel for a task workspace
- `chat-overlay-empty-state.tsx` -- empty state for the chat overlay when no session is active

______________________________________________________________________

## Hooks

Custom hooks in `src/lib/hooks/`:

- `use-websocket-sync.ts` -- connects WebSocket events to the Jotai atom graph
- `use-task-events.ts` -- subscribes to task-scoped WebSocket events
- `use-board-dnd.ts` -- drag-and-drop state and handlers for the kanban board
- `use-board-keyboard.ts` -- keyboard navigation and shortcuts for the board
- `use-follow-up-queue.ts` -- manages the follow-up message queue for a task session
- `use-mobile.ts` -- responsive breakpoint detection

______________________________________________________________________

## State Architecture

- **Jotai atoms** in `src/lib/atoms/` hold authentication, board, chat, connection, theme, and UI shell state.
- **Route-local state** handles page-specific loading, tab selection, and transient form state.
- **WebSocket sync** lives in `use-websocket-sync.ts` and feeds board/task/chat updates into the atom graph.

______________________________________________________________________

## Design System

- **UI library:** shadcn/ui + Radix primitives (owned in-repo under `src/components/ui/`). No migration planned — Radix a11y coverage (focus traps, keyboard nav, screen readers) is load-bearing for complex interactive patterns.
- **Design direction:** Expressive Minimalism (Linear/Vercel-inspired). Monochrome dark base, warm gold primary (`#d4a84b`), generous whitespace, subtle borders via surface shade layers, quiet micro-animations, selective glassmorphism on overlays only, keyboard-first interaction.
- **Typography:** `IBM Plex Sans` is the UI font; `JetBrains Mono` is reserved for code, IDs, diffs, and telemetry labels.
- **Tokens:** Global tokens, motion defaults, and shell surfaces live in `src/app.css` (60+ CSS custom properties).
- **Shared primitives:** `src/components/shared/workspace.tsx` provides reusable headers, panels, sticky action bars, inspector sections, and action-oriented empty states.
- **Reference apps:** Linear, Vercel Dashboard, Raycast, Cursor, Supabase Dashboard.

______________________________________________________________________

## Routing

- `/board` -- kanban board and inspector/AI Panel rails
- `/task/:id` -- unified task workspace with 3 tabs: **Overview**, **Changes**, **Review**
- `/task/:id?lane=worker|reviewer` -- deep-link that auto-opens the ChatSidePanel overlay for live streaming
- `/session/:taskId` -- legacy redirect to `/task/:id?lane=worker`
- `/chat/:id` -- orchestrator conversation
- `/settings` -- categorized system configuration
- `/welcome` -- onboarding/project setup page

Global overlays in app layout include Session Switcher (`Cmd/Ctrl+Shift+K`) and Help (`?`/`F1`).

The app is SPA-only and configured through `src/routes.tsx`.

### Task detail tab selection

The task detail page (`/task/:id`) selects its initial tab based on task state:

| Task state                        | Default tab  |
| --------------------------------- | ------------ |
| Status is `REVIEW` with workspace | **Review**   |
| Status is `BACKLOG`               | **Overview** |
| Has workspace (other statuses)    | **Changes**  |
| Fallback                          | **Overview** |

When a task has an active session, the **ChatSidePanel** overlay auto-opens on the right rail. The overlay shows live streaming output with a Worker/Reviewer lane toggle in its header and a LIVE indicator. URL query parameter `?lane=worker|reviewer` controls which lane is active and triggers the overlay to open. The ChatSidePanel filters events by the active session ID.

______________________________________________________________________

## API Layer

- **`src/lib/api/client.ts`**
  - owns base URL, bundled-web mode, and REST helpers
  - unwraps `WireEnvelope<T>` responses and normalizes API errors
- **`src/lib/api/websocket.ts`**
  - manages connect/reconnect lifecycle
  - emits board, run, session, and chat events into the UI
  - chat events: `CHAT_CHUNK`, `CHAT_TOOL_START`, `CHAT_TOOL_PROGRESS`, `CHAT_DONE`, `CHAT_ERROR`, `CHAT_INTERRUPTED`, `CHAT_SESSION_UPDATED`, `CHAT_BUSY`
  - run events: `RUN_STARTED`, `RUN_CANCELLED`, `RUN_ERROR`
  - tool permission events: `TOOL_PERMISSION_REQUEST`
  - follow-up events: `FOLLOW_UP_QUEUED`, `FOLLOW_UP_SENT`, `TASK_FOLLOW_UP_ACK`, `TASK_FOLLOW_UP_ERROR`
  - `OrchestratorChatPanel` manages streaming state locally and passes `disableSend` to `ChatInputBar` for wave/interrupt indicator

Bundled web mode talks to the same local server instance that serves the SPA. It does not perform QR pairing or token auth.

______________________________________________________________________

## Testing

- **Vitest** for component, hook, and atom tests
- **Playwright** for task flow, navigation, board, and chat E2E coverage
- **TypeScript build** via `pnpm run typecheck` and `pnpm run build`
