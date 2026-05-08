# Web Architecture -- `packages/web`

*Design principles: React 19 SPA, Jotai state, shadcn/Radix primitives, thin client over Kagan REST and SSE APIs.*

______________________________________________________________________

## Context

`packages/web` is the browser client for Kagan. It is a static React SPA built with Vite, bundled into the Python package, and served locally by `kagan web`.

______________________________________________________________________

## Design Principles

1. **Thin client** -- workflow logic stays in Python (`kagan.core`); the web app coordinates API calls and renders state.
1. **Owned primitives** -- shadcn/Radix components live in-repo and are styled through Kagan tokens in `src/app.css`.
1. **Dark-first IDE shell** -- the app uses a persistent activity bar, contextual header, Quick Actions, and workspace panels across routes.
1. **Single integration boundary** -- all server communication flows through `apiClient` (REST) and `streamSSE` (Server-Sent Events).
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
│   ├── workspace-page.tsx      # orchestrator-first workspace (session sidebar + conversation surface)
│   ├── task-detail-page.tsx    # unified task workspace (Overview, Changes, Review tabs)
│   ├── chat-page.tsx
│   ├── settings-page.tsx
│   ├── home-page.tsx
│   ├── welcome-page.tsx        # onboarding/project setup page
├── components/
│   ├── board/
│   ├── chat/
│   ├── layout/
│   ├── session/
│   ├── settings/
│   ├── shared/
│   ├── workspace/
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
- `board-filter-bar.tsx` -- search and status filters
- `agent-control.tsx` -- start/stop/attach controls; shows guidance before launching interactive sessions
- `create-task-dialog.tsx`, `edit-task-dialog.tsx`, `task-delete-dialog.tsx` -- task CRUD dialogs
- `diff-viewer.tsx` -- workspace diff renderer
- `review-panel.tsx` -- review approval surface
- `task-metadata-panel.tsx` -- metadata inspector section
- `backlog-list-view.tsx` -- list view for backlog lane
- `integration-import-dialog.tsx` -- integration import flow dialog
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

### `chat/`

- `streaming-glyph.tsx` -- shared animated wave glyph used by chat, session streams, and tool renderers
- `streaming-status.tsx` -- shared status label for thinking, tool, command, read, search, image, and generic streaming states
- `chat-input-bar.tsx` -- reusable chat composer with send/interrupt affordances
- `chat-stream-entries.tsx` -- orchestrator stream entry renderer

### `layout/`

- `context-bar.tsx` -- active project/repo selector; guarantees an active repo when possible and prompts for Add Repository when required

### `workspace/`

- `workspace-sidebar.tsx` -- orchestrator session list with search, create, and delete actions

______________________________________________________________________

## Right Rail

The app shell owns one right rail. It hosts exactly one of two surfaces:

- `SessionOverlay` for task worker/reviewer streams, keyed by `rightRailTaskIdAtom`.
- `OrchestratorChatPanel` for project orchestrator sessions, keyed by
  `rightRailChatSessionIdAtom`.

`rightRailModeAtom` controls layout only: `none`, `chat-right`, `chat-bottom`,
or `chat-fullscreen`. `Cmd/Ctrl+.` toggles the rail; `Cmd/Ctrl+K` opens the
session picker. Task streams use `/task/:id?lane=worker|reviewer` for deep
links. Orchestrator sessions use `/chat/:id` or the workspace route.

______________________________________________________________________

## Hooks

Custom hooks in `src/lib/hooks/`:

- `use-event-stream.ts` -- connects SSE event stream to the Jotai atom graph
- `use-task-events.ts` -- subscribes to task-scoped session events via CustomEvent dispatch
- `use-board-dnd.ts` -- drag-and-drop state and handlers for the kanban board
- `use-board-keyboard.ts` -- keyboard navigation and shortcuts for the board
- `use-follow-up-queue.ts` -- manages the follow-up message queue for a task session
- `use-mobile.ts` -- responsive breakpoint detection

______________________________________________________________________

## State Architecture

- **Jotai atoms** in `src/lib/atoms/` hold authentication, board, chat, connection, theme, and UI shell state.
- **ContextBar** coordinates active project/repo selection and seeds `boardRepoFilterAtom`; if repos exist it keeps one selected, and if none exist it opens the Add Repository dialog.
- **Route-local state** handles page-specific loading, tab selection, and transient form state.
- **SSE sync** lives in `use-event-stream.ts` and feeds board/task updates into the atom graph. Chat streaming uses per-turn SSE via `POST /api/chat/{id}/stream`.

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
- `/workspace` -- orchestrator-first workspace with session sidebar and full-width conversation surface
- `/task/:id` -- unified task workspace with 3 tabs: **Overview**, **Changes**, **Review**
- `/task/:id?lane=worker|reviewer` -- deep-link that opens the task stream rail
- `/chat/:id` -- orchestrator conversation
- `/settings` -- categorized system configuration
- `/welcome` -- onboarding/project setup page

Global overlays in app layout include Session Switcher (`Cmd/Ctrl+Shift+K`) and Help (`?`/`F1`).

`Cmd/Ctrl+Shift+W` toggles between `/board` and `/workspace`. On `/workspace`, the route itself is the orchestrator surface, so the app-level AI rail stays hidden.

The app is SPA-only and configured through `src/routes.tsx`.

### Task detail tab selection

The task detail page (`/task/:id`) selects its initial tab based on task state:

| Task state                        | Default tab  |
| --------------------------------- | ------------ |
| Status is `REVIEW` with workspace | **Review**   |
| Status is `BACKLOG`               | **Overview** |
| Has workspace (other statuses)    | **Changes**  |
| Fallback                          | **Overview** |

When a task has an active session, `SessionOverlay` opens in the right rail.
The Worker/Reviewer lane toggle selects a task session, and the panel filters
events by that session ID. `?lane=worker|reviewer` controls the initial lane.

______________________________________________________________________

## API Layer

- **`src/lib/api/client.ts`**
  - owns base URL, bundled-web mode, and REST helpers
  - unwraps `WireEnvelope<T>` responses and normalizes API errors
- **`src/lib/api/sse.ts`**
  - `streamSSE<T>()` — async generator over `fetch` + `ReadableStream` for SSE parsing
  - supports `POST` (unlike native `EventSource`), custom headers, `AbortController`
- **`src/lib/hooks/use-event-stream.ts`**
  - connects to `GET /api/events/stream` for board + session events
  - passes a stable `client_id` so server-side presence can survive SSE reconnects
  - auto-reconnects with exponential backoff (1s → 30s)
  - dispatches `SESSION_EVENT` via `CustomEvent('kagan:session-event')` for component-level subscription
  - refreshes `/api/presence` and posts presence heartbeats so task cards can show live watchers
- **Chat streaming** uses per-turn SSE (`POST /api/chat/{id}/stream`) — `OrchestratorChatPanel` manages streaming state locally, syncs session summary changes back to `/workspace`, and passes `disableSend` to `ChatInputBar`
- **Commands** (run, cancel, follow-up, interrupt) use REST endpoints via `apiClient`

Bundled web mode talks to the same local server instance that serves the SPA. It does not perform QR pairing or token auth.

______________________________________________________________________

## Testing

- **Vitest** for component, hook, and atom tests
- **Playwright** for task flow, navigation, board, and chat E2E coverage
- **TypeScript build** via the root pnpm workspace scripts: `pnpm run web:typecheck` and `pnpm run web:build`
