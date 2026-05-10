# Web Architecture -- `packages/web`

*Design principles: React 19 SPA, Jotai state, shadcn/Radix primitives, thin client over Kagan REST and SSE APIs.*

______________________________________________________________________

## Context

`packages/web` is the browser client for Kagan. It is a static React SPA built with Vite, bundled into the Python package, and served locally by `kagan web`.

______________________________________________________________________

## Design Principles

1. **Thin client** -- workflow logic stays in Python (`kagan.core`); the web app coordinates API calls and renders state.
1. **Owned primitives** -- shadcn/Radix components live in-repo and are styled through Kagan tokens in `src/app.css`.
1. **Single shell, two tabs** -- the app shell is a 44 px title bar over a collapsible 252 px sidebar and a content surface. Title-bar tabs switch between `Workspace` (`/chat`) and `Kanban` (`/board`); task detail and settings render inside the same shell.
1. **Single integration boundary** -- all server communication flows through `apiClient` (REST) and `streamSSE` (Server-Sent Events).
1. **One command surface** -- `Spotlight` (Cmd/Ctrl+K) unifies task search, command-palette commands, and session switching. There is no separate command palette.
1. **Status terminology is canonical** -- display labels are exactly `Backlog`, `In Progress`, `Review`, `Done` across web/TUI/chat. Never rename to `RUN` or other variants from external mockups.

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
│   ├── chat-page.tsx           # workspace tab content (renders inside shell)
│   ├── task-detail-page.tsx    # task tab content (Overview, Changes, Review)
│   ├── settings-page.tsx
│   ├── welcome-page.tsx        # onboarding/project setup (rendered outside shell)
│   └── workspace-page.tsx      # legacy redirect → /chat
├── components/
│   ├── shell/                  # title bar, sidebar, spotlight, new-session dialog
│   ├── board/
│   ├── chat/
│   ├── layout/                 # remaining dialogs only (add-repo, create-project, help-overlay)
│   ├── session/                # session bodies + picker + commits panel
│   ├── settings/
│   ├── shared/
│   └── ui/
└── lib/
    ├── api/
    ├── atoms/                  # board, ui, theme, connection, presence, shell
    ├── commands/               # registry consumed by Spotlight
    ├── hooks/
    ├── sessions/               # type guards (SessionKind narrowing)
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

### `shell/`

- `shell-layout.tsx` — root layout: 44 px title bar + 252 px collapsible sidebar + outlet. Owns the project-active gate, global hotkeys (Cmd+K, Cmd+\\, Cmd+1/2, N, /), and dialog mounts (Spotlight, NewSessionDialog, SessionPicker, HelpOverlay, IntegrationImport).
- `title-bar.tsx` — window chrome (traffic lights), back/forward, sidebar toggle, project glyph, Workspace ↔ Kanban tabs, search trigger, daemon pill, settings link, theme toggle.
- `sidebar.tsx` — primary actions (`New task`, `New session`, `Board`, `Activity`), Sessions section (orchestrator + general from `useSessionList`), Projects section (active project tasks grouped by status), footer with Settings + version chip.
- `spotlight.tsx` — Cmd+K overlay: unified search across tasks, commands (from `lib/commands/registry`), and sessions. Replaces the legacy CommandPalette.
- `new-session-dialog.tsx` — modal that creates orchestrator or general sessions via `apiClient.createSession`.

### `session/`

- `GeneralSessionBody.tsx` / `OrchestratorSessionBody.tsx` / `TaskSessionBody.tsx` — route the active row to `ChatView` + `useChatSession`
- `session-picker.tsx` — session switcher chrome (kept for the `nav-session-switcher` command; sessions are also reachable through the shell sidebar)
- `event-stream.tsx` — event list renderer for task-scoped output
- `follow-up-queue.tsx` — queued follow-up messages for a task session
- `task-commits-panel.tsx` — commit history panel for a task workspace
- `chat-overlay-empty-state.tsx` — empty state when no session is selected

### `chat/`

- `streaming-glyph.tsx` -- shared animated wave glyph used by chat, session streams, and tool renderers
- `streaming-status.tsx` -- shared status label for thinking, tool, command, read, search, image, and generic streaming states
- `chat-input-bar.tsx` -- reusable chat composer with send/interrupt affordances
- `chat-stream-entries.tsx` -- orchestrator stream entry renderer

### `layout/`

- `add-repo-dialog.tsx` — repo-add modal triggered by ContextBar successor flows (creation/import paths)
- `create-project-dialog.tsx` — project-create modal
- `help-overlay.tsx` — keyboard shortcuts overlay reachable via `?` / commands
- `resize-handle.tsx` — generic horizontal resize handle (used by chat-page sidebar)

> Legacy shell pieces (`activity-bar.tsx`, `context-bar.tsx`, `header-bar.tsx`, `mobile-tabs.tsx`, `palette.tsx`, `app-layout.tsx`) were removed when `components/shell/` landed. Project switching now lives inside Welcome and Settings flows; sidebar primary actions cover the rest.

______________________________________________________________________

## Sessions Surface

Sessions are first-class in the shell sidebar, not in a docked overlay.

`useSessionList` polls `GET /api/v1/sessions` and seeds the **Sessions** section in `Sidebar`. Orchestrator and general sessions show up directly; task-bound sessions are reached through the relevant task on the Kanban tab. Clicking a session navigates to `/chat/:id`, which renders inside the Workspace tab. The legacy `SessionOverlay` was removed; `selectedSessionAtom` and `sessionOverlayLayoutAtom` are kept only as compatibility shims and are not consumed by the shell.

`Spotlight` (Cmd/Ctrl+K) provides a session group alongside tasks and commands so any session is one keystroke away from any view. The `nav-session-switcher` command opens `SessionPicker`, retained for users who prefer the modal switcher.

______________________________________________________________________

## Hooks

Custom hooks in `src/lib/hooks/`:

- `use-chat-session.ts` — **per-session** streaming, interrupt, queue, and slash-command state for one chat id (hook-local `useState`; live events from `GET /api/chat/sessions/{id}/watch` via `useChatWatch`)
- `use-chat-watch.ts` — subscribes to `GET /api/chat/sessions/{id}/watch` for live `ChatWatchEvent` envelopes
- `use-session-overlay.ts` — compatibility shim over `selectedSessionAtom`/`sessionOverlayLayoutAtom`; preserved for chat panels but no longer drives a docked rail
- `use-session-list.ts` — polls unified session list for the overlay/workspace
- `use-session-actions.ts` — stop/close session helpers
- `use-event-stream.ts` — connects `GET /api/events/stream` to the Jotai atom graph (board + task events)
- `use-task-events.ts` — subscribes to task-scoped session events via `CustomEvent` dispatch
- `use-board-dnd.ts` — drag-and-drop state and handlers for the kanban board
- `use-board-keyboard.ts` — keyboard navigation and shortcuts for the board
- `use-follow-up-queue.ts` — manages the follow-up message queue for a task session
- `use-mobile.ts` — responsive breakpoint detection

______________________________________________________________________

## State Architecture

- **Jotai atoms** in `src/lib/atoms/` hold authentication, board, connection, theme, UI shell, and session-overlay chrome (open/layout/selection). **Chat streaming buffers, pending queues, and stream entries are not global atoms** — they live inside `useChatSession` (hook-local state) so concurrent sessions cannot race.
- **`src/lib/atoms/chat.ts`** exports **types and constants** only (`ChatStreamEntry`, pending-queue types, `PENDING_QUEUE_MAX`), not writable singleton atoms.
- **`shell-layout.tsx`** runs the project-active gate on mount; if no active project exists it redirects to `/welcome`. Active-repo selection now lives inside Welcome and Settings flows (the title bar no longer hosts a project/repo switcher).
- **Route-local state** handles page-specific loading, tab selection, and transient form state.
- **SSE sync** lives in `use-event-stream.ts` and feeds board/task updates into the atom graph. **Live chat UI** consumes `GET /api/chat/sessions/{id}/watch` via `useChatWatch` + `useChatSession`; sending a turn still opens `POST /api/chat/{id}/stream` (per-turn SSE body drained for backpressure; the watch stream carries decoded `ChatWatchEvent` frames).

______________________________________________________________________

## Design System

The canonical design system bundle lives at `/Users/aorumbayev/Downloads/kagan-design-system/` (not in version control). The source of truth for web tokens is `packages/web/src/app.css`.

### Token source of truth

`src/app.css` holds all CSS custom properties — color, type, spacing, radius, shadow, motion, and A11y tokens. Do not add color literals inline; always use a named token (`var(--card)`, `var(--primary)`, etc.). The canonical palette is:

- **Amber primary:** `#d4a84b` (`--primary`, `--ring`)
- **Warm-black foundation** in light: `#f2eee5` (page) / `#ece5d8` (card)
- **Slate near-black** in dark: `hsl(240 6% 6%)` (page) / `hsl(240 5% 9%)` (card)
- **Semantic:** danger `#b93125` (light) / `#ef4444` (dark), review `#a8653a` / `#c27c4e`

### Content rules

- **Sentence case** for all UI copy: page headings, buttons, menu items, dialog titles, tooltips.
- **UPPERCASE only** for terminal-style labels: column headers (`BACKLOG`, `IN PROGRESS`, `REVIEW`, `DONE`), eyebrow tags, section labels (`CHANGES`, `AGENT LOG`), mode badges (`AUTO`, `PAIR`).
- **Lowercase** for inline TUI-style hints in the web (`press / to open spotlight`, `esc to close`).
- **No emoji.** Use unicode geometric glyphs (`✓ ✗ ↗ ∿ ▸ ●`) or Lucide icons.
- **Editorial-technical voice:** no exclamation marks, no hype words, no first-person plural except legal/credit.

### Iconography

Lucide icons at `strokeWidth={1.75}` for all UI affordances. The send button is the sole exception (`strokeWidth={1.75}` maintained). Raw inline SVGs also use `strokeWidth="1.75"`.

### Radius, borders, shadows

- Base radius `--radius: 0.5rem` (8px). Chips: `--radius-sm: 0.375rem` (6px).
- `rounded-full` is legitimate only for dot indicators, traffic-light chrome, avatar circles, toggle thumbs, and scroll-area thumbs. All other chips and labels use `rounded` or no radius class.
- Borders are 1 px hairline. No thick borders. No bluish-purple gradients (warm/amber vertical fades on surfaces are acceptable).

### Primitives

- `src/components/ui/eyebrow.tsx` — uppercase eyebrow label (`font-code text-[10px] font-semibold uppercase tracking-[0.22em]`). Use for section labels, column heads, mode badges.
- `src/components/ui/industrial-frame.tsx` — 12×12 amber L-bracket corner pinning for CRT-viewport framing. At most one per screen.

### UI library

shadcn/ui + Radix primitives (owned in-repo under `src/components/ui/`). Radix a11y coverage (focus traps, keyboard nav, screen readers) is load-bearing — do not replace with custom implementations.

### Typography

`IBM Plex Sans` for UI; `JetBrains Mono` for code, IDs, diffs, telemetry, and eyebrow labels. The `ᘚᘛ` logo glyph is set in `font-family: var(--font-mono)`, `font-weight: 600`, `letter-spacing: -0.04em`, `font-feature-settings: "liga" 0`.

### Animation

Origami-style transitions only: `perspective(800px) rotateX(-3deg)→0` fades. No bounce, spring, or rubber-band. All animations disable cleanly under `prefers-reduced-motion` (global override in `src/app.css`).

______________________________________________________________________

## Routing

All authenticated routes mount inside `components/shell/shell-layout.tsx`.

- `/welcome` -- onboarding/project setup (rendered **outside** the shell)
- `/board` -- Kanban tab (selected by `title-bar.tsx`)
- `/chat`, `/chat/:id` -- Workspace tab; `/chat/:id` scopes to a session
- `/task/:id` -- inline task detail (Overview, Changes, Review tabs)
- `/task/:id?lane=worker|reviewer` -- deep-link that opens a task session in the conversation surface
- `/settings` -- categorized system configuration; reached from sidebar footer or Spotlight
- `/workspace`, `/analytics` -- legacy redirects (`→ /chat`)

Global hotkeys (handled in `shell-layout.tsx`):

| Combo            | Action                                    |
| ---------------- | ----------------------------------------- |
| Cmd/Ctrl+K       | Open Spotlight                            |
| Cmd/Ctrl+\\      | Toggle sidebar                            |
| Cmd/Ctrl+1       | Workspace tab                             |
| Cmd/Ctrl+2       | Kanban tab                                |
| Cmd/Ctrl+Shift+L | Toggle theme (handled in `title-bar.tsx`) |
| `N`              | New task (when no field is focused)       |
| `/`              | Open Spotlight                            |

The app is SPA-only and configured through `src/routes.tsx`.

### Task detail tab selection

The task detail page (`/task/:id`) selects its initial tab based on task state:

| Task state                        | Default tab  |
| --------------------------------- | ------------ |
| Status is `REVIEW` with workspace | **Review**   |
| Status is `BACKLOG`               | **Overview** |
| Has workspace (other statuses)    | **Changes**  |
| Fallback                          | **Overview** |

When a task has an active session, the inline conversation surface inside
the task content renders the agent stream. `?lane=worker|reviewer` controls
which session lane is selected on first paint.

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
- **Chat streaming** — `useChatSession` posts turns to `POST /api/chat/{id}/stream` and listens on `GET /api/chat/sessions/{id}/watch` for `ChatWatchEvent` frames (chunks, tools, done, permission requests). Stream/buffer state is **per hook instance**, not global Jotai.
- **Commands** (run, cancel, follow-up, interrupt) use REST endpoints via `apiClient`

Bundled web mode talks to the same local server instance that serves the SPA. It does not perform QR pairing or token auth.

______________________________________________________________________

## Testing

- **Vitest** for component, hook, and atom tests
- **Playwright** for task flow, navigation, board, and chat E2E coverage
- **TypeScript build** via the root pnpm workspace scripts: `pnpm run web:typecheck` and `pnpm run web:build`
