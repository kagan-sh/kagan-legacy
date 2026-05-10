# Web Features

Observable behaviors of the React web client.

______________________________________________________________________

## 1. Boot & Onboarding

- the shipped web app runs in bundled mode against the same-origin Kagan server
- onboarding state is local to the browser and does not require a separate pairing route
- startup verifies same-origin server health before entering the board workspace
- `/welcome` hosts the onboarding/project setup page; first-run users land here before the board
- `first-boot-tutorial-dialog.tsx` surfaces an in-board tutorial overlay on first launch

______________________________________________________________________

## 2. App Shell

- single 44 px title bar with traffic-light chrome, sidebar toggle, history nav, project glyph, search trigger, daemon pill, settings link, theme toggle
- title-bar segmented control switches between **Workspace** (`/chat`) and **Kanban** (`/board`); animated indicator slides between the two
- 252 px sidebar (collapsible via `Cmd/Ctrl+\\`) with primary actions (`New task`, `New session`, `Board`, `Agents`; `Agents` opens a popover, not a route), a collapsible **Sessions** section, a collapsible **Tasks** section (active project tasks grouped by status), and a footer with Settings + version chip
- **Spotlight** (`Cmd/Ctrl+K` or sidebar search trigger or `/`) is the single command surface — searches tasks, runs registered commands, switches sessions
- canonical status display labels across the shell: `Backlog`, `In Progress`, `Review`, `Done` (never `RUN` or other variants)

______________________________________________________________________

## 3. Board Workspace

- four-lane kanban board: `Backlog`, `In Progress`, `Review`, `Done` (display labels — DB enum stays `BACKLOG | IN_PROGRESS | REVIEW | DONE`)
- search plus structured status/mode filters
- advisory WIP warnings from resolved workflow settings
- richer task cards with review state, acceptance-criteria count, last activity, workspace state, and live session telemetry
- task cards can show lightweight watcher counts from live client presence when another web or editor client is actively focused on that task
- desktop right rail supports task inspection and related chat preview
- repo selection lives inside Welcome / Add-Repo flows — the shell title bar no longer hosts a project switcher
- title-bar tab segmented control switches between Workspace and Kanban; `Cmd/Ctrl+1` / `Cmd/Ctrl+2` are keyboard equivalents

______________________________________________________________________

## 3a. Workspace View

- the Workspace tab (`/chat`) is the conversation-first surface; sessions live in the shell sidebar
- selecting a session navigates to `/chat/:id` and renders the conversation full-width inside the shell
- session creation goes through the **New session** modal (orchestrator vs general kind picker, agent backend dropdown, optional name)
- session labels and backend changes propagate back into the sidebar list after turns complete or metadata changes

______________________________________________________________________

## 4. Task Workspace

- `/task/:id` renders inside the shell with a back-button to whichever tab the user came from
- three tabs: **Overview**, **Changes**, and **Review**
- tab auto-selection: `REVIEW` with workspace opens Review; `BACKLOG` opens Overview; workspace present opens Changes; otherwise Overview
- live execution streaming surfaces inline within the task content area when a task has an active session (deep-link via `?lane=worker|reviewer`)
- "Watch stream" on the board inspector opens `/task/:id?lane=worker`
- sticky action bar keeps lifecycle controls and run controls visible
- summary rail surfaces metadata, runtime telemetry, workspace state, and review approval

______________________________________________________________________

## 5. Live Streaming

- live task event updates flow over SSE through `useEventStream` and `useTaskEvents`
- AGENT_STATUS events with usage data render an inline metrics row: context window fill bar, percentage, and cost
- the legacy right-rail SessionOverlay was removed; streams render inline within the active session/task surface

______________________________________________________________________

## 6. Chat & Sessions

- **Per-session streaming state** — orchestrator/general chat panels use `useChatSession(sessionId)` with hook-local buffers and queues so multiple sessions cannot overwrite each other.
- **Spotlight** (`Cmd/Ctrl+K`) is the unified switcher: tasks, commands, and sessions in one fuzzy list; the legacy multi-shortcut split is gone.
- `/chat/:id` shows orchestrator conversation history, streaming output, slash commands, and backend metadata.
- Task-specific quick-jump entry points navigate to `/task/:id?lane=worker|reviewer` so the relevant session renders inline within the task content area.
- during streaming, the shared animated wave glyph and `esc interrupt` hint appear below the chat input; space is always reserved to prevent layout shift (shape language matches the chat REPL and TUI).
- session titles are auto-generated after the first exchange via a lightweight ACP call and pushed to the client via `CHAT_SESSION_UPDATED` SSE event.

______________________________________________________________________

## 7. Settings

- categorized settings surface: `Orchestration`, `Appearance`, `Delivery Automation`, `Workspace`, `Identity & Models`, and `Additional Instructions`
- orchestration section exposes typed behavioral controls: execution mode, review strictness, planning depth, auto-confirm
- additional instructions section provides a single text field for user-specific guidance (additive, never replaces defaults)
- dotfile override status shown when `.kagan/prompts/` files are detected
- resolved workflow settings expose advisory WIP limits to both settings and board UI

______________________________________________________________________

## 8. Realtime & Accessibility

- board, task content area, and chat views react to SSE updates
- visible keyboard focus, strong border contrast, skip link support, and reduced-motion respect
- typography is split between UI and code surfaces for readability in long work sessions

______________________________________________________________________

## 8a. Shell Sessions Surface

- sessions live in the shell **Sidebar**, not in a docked overlay
- `useSessionList` polls `GET /api/v1/sessions`; the sidebar Sessions section shows orchestrator and general kinds only; task-bound sessions are nested under their parent task row in the Tasks section, not listed here
- the Sessions section is collapsible; an eyebrow label acts as the collapse toggle
- search input appears inside the Sessions section when session count > 8
- **"View all sessions"** link (opens `SessionPicker`) is visible only when session count > 4; it does not render for small session lists
- each session row carries a status dot that reflects live streaming state (idle / running / in-review)
- hovering a session row reveals a delete button; clicking it enters a 2 s confirm mode before calling `apiClient.closeSession` — pressing elsewhere or waiting reverts to idle
- the Tasks section is collapsible; each task row has a chevron that expands inline to reveal nested worker (`W` badge) and reviewer (`R` badge) session sub-rows; badge colours match the lane colour for the session kind
- hovering a task row reveals a Run / Open action at the right edge
- task-bound sessions are reached through expanded task rows in the sidebar or through `/task/:id?lane=…` deep-links
- workspace and task routes render their respective session bodies through the same components consumed by Spotlight navigation

*Tests:* `packages/web/src/components/shell/title-bar.test.tsx`,
`packages/web/src/components/shell/sidebar.test.tsx`,
`packages/web/src/components/shell/spotlight.test.tsx`,
`packages/web/src/lib/sessions/kind.test.ts`.

### Preflight gate

- `components/welcome/preflight-gate.tsx` mirrors the TUI doctor flow on
  Welcome: hard `fail` checks block the dashboard with a setup dialog,
  pure `warn` checks render a dismissible "Degraded configuration" banner
- the banner suppresses purely-optional backend warnings the same way the
  TUI does — when at least one backend is installed, missing non-default
  backends do not flip the boot state to degraded

______________________________________________________________________

## 9. Interactive Session Launch

- when launching an interactive session, a guidance dialog appears before the session launches
- dialog content adapts by launcher backend: tmux (attach command), nvim (nvim launch command), IDE (editor deep link)
- terminal backends (tmux, nvim) copy a runnable command to clipboard
- "Do not show this guidance again" toggle persists the `skip_attached_instructions_popup` setting
- task-level launcher override (`task.launcher`) takes priority over global `settings.attached_launcher`
- if a managed run is active when Attach is clicked, the dialog warns that the background agent will be stopped; on confirmation the managed run is cancelled before the interactive session starts

______________________________________________________________________

## 10. Design System

The canonical design system bundle lives at `/Users/aorumbayev/Downloads/kagan-design-system/` (not in version control). Token source of truth: `packages/web/src/app.css`.

### Content rules (behavioral)

- **Sentence case** everywhere: page headings, buttons, menu items, dialog titles, tooltips. Examples: "New task", "Create task", "Edit task", "Open session switcher".
- **UPPERCASE** only for terminal-style column headers (`BACKLOG`, `IN PROGRESS`, `REVIEW`, `DONE`), eyebrow tags, section labels, and mode badges (`AUTO`, `PAIR`, `ORCH`).
- **Lowercase** for inline keyboard hints (`press / to open spotlight`, `esc to close`).
- **No emoji.** Unicode geometric glyphs (`✓ ✗ ↗ ∿ ▸ ●`) or Lucide icons only.
- **No hype words.** No exclamation marks. No first-person plural except in legal/credit copy.
- Agent lifecycle messages use: "started", "finished", "stopped", "failed" — never "thinking" or "feeling".

### Icon and stroke rules

- Lucide icons: `strokeWidth={1.75}` for all UI affordances. Raw inline SVGs: `strokeWidth="1.75"`.

### Radius rules

- `rounded-full` is correct only for: status dot indicators, traffic-light chrome, avatar images, toggle thumb, scroll-area thumb.
- All other chips and label pills use `rounded` (4px) or no class.

### Primitives added

- `src/components/ui/eyebrow.tsx` — uppercase section label. Collapses repeated `font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted-foreground)]` patterns.
- `src/components/ui/industrial-frame.tsx` — optional amber L-bracket corner decorator (12×12 px). Maximum one per screen. Does not render automatically anywhere — expose for future use.
