# TUI Features

Observable behaviors of `kagan.tui`. Each section maps to tests in `tests/tui/`.
Implementation details live in `docs/internal/architecture/tui.md`.

______________________________________________________________________

## 1. Welcome & Onboarding

- App launches to Welcome with project list and CWD suggestion banner
- `Enter` opens selected project, `n` starts new project flow, `o` opens folder flow
- Optional startup routing can skip Welcome and open last active project

______________________________________________________________________

## 2. Kanban Board

- Four columns: BACKLOG, IN_PROGRESS, REVIEW, DONE
- Vim + arrow navigation across cards/columns
- `Enter` is two-step: first open the inspector for the selected card, then open the full task screen
- `w` switches from Kanban into the orchestrator-first Workspace screen
- `Space` cycles AI split overlay, `/` toggles search
- `p` opens task peek overlay without changing chat layout
- `x` deletes selected task (with confirm), `s` starts agent, `Shift+S` stops agent
- `Shift+Left/Right` moves task between workflow columns
- `Ctrl+R` opens repo picker; Quick Actions (`Ctrl+Shift+P`) handles rare actions

______________________________________________________________________

## 3. Workspace

- The TUI Workspace is a dedicated screen, not an overlay
- Left sidebar lists orchestrator sessions only; search filters by title, session id, and backend
- The right pane shows a compact active-conversation header above the full chat surface
- Focus enters on the session list by default so `n`, `x`, `/`, and `Enter` always target the sidebar first
- `n` creates a new orchestrator session, `x` deletes the selected session, `Enter` opens the highlighted session
- `Ctrl+I` explicitly moves focus into the chat input; opening or creating a session also moves focus into chat
- `Esc` is layered: in search it clears the filter first, from chat it returns to the sidebar, and from the sidebar it returns to Kanban
- `w` always switches back to Kanban directly
- Footer hints are focus-aware: sidebar, search, and chat each show different next actions
- Session titles are persisted through the shared orchestrator session store, matching the web workspace model

______________________________________________________________________

## 4. Task Authoring

- `n` opens create flow; `e` edits selected task
- Save/cancel behavior in editor follows `Ctrl+S`/`Esc`

______________________________________________________________________

## 5. Task Screen

- Shows task context, diff, stream, and AI Panel
- Agent status panel displays backend, status, elapsed time, run ID, PID, context window usage, and cumulative cost
- AGENT_STATUS events update context window and cost metrics in real-time
- `a` approve, `x` reject, `m` merge, `b` rebase
- AI review is Quick Actions first on task screen (`Ctrl+Shift+P` -> `review.ai`)
- `Esc` returns to board

______________________________________________________________________

## 6. AI Panel

- Two modes: orchestrator and task session
  - `Ctrl+I` toggles AI Panel, `Space` cycles split layout, `Ctrl+F` fullscreen while open, `Ctrl+K` Session Switcher, `Esc` close
- `Enter` send, `Shift+Enter` newline, `Tab` accept completion
- `Ctrl+C` clears input text; `Esc` stops the active agent

______________________________________________________________________

## 7. Session & Backend

- TaskScreen is the default TUI route for task inspection and follow-up work
- WorkspaceScreen is the default TUI route for orchestrator-first conversation work
- Session Dashboard exists in the codebase for dedicated run monitoring, but is not the default board navigation target today
- Backend selection and session switching are available from overlays and pickers

______________________________________________________________________

## 8. Keybindings Snapshot

### Global

| Key            | Action              |
| -------------- | ------------------- |
| `?` / `F1`     | Help                |
| `Ctrl+Shift+P` | Quick Actions       |
| `Ctrl+O`       | Project selector    |
| `Ctrl+R`       | Repository selector |
| `Ctrl+,`       | Settings            |
| `Ctrl+Q`       | Quit                |

### Kanban

| Key                | Action                                               |
| ------------------ | ---------------------------------------------------- |
| `n`                | New task                                             |
| `Enter`            | Open task flow                                       |
| `w`                | Switch to workspace                                  |
| `a`                | Attach interactive run (stops managed run if active) |
| `Space`            | Cycle AI split                                       |
| `p`                | Peek                                                 |
| `e`                | Edit                                                 |
| `x`                | Delete (confirm)                                     |
| `s` / `Shift+S`    | Start managed run / stop active run                  |
| `Shift+Left/Right` | Move task                                            |
| `/`                | Search                                               |

### Workspace

| Key      | Action                                                         |
| -------- | -------------------------------------------------------------- |
| `Enter`  | Open highlighted session                                       |
| `n`      | New session                                                    |
| `x`      | Delete selected session                                        |
| `/`      | Focus search                                                   |
| `Ctrl+I` | Focus chat input                                               |
| `Ctrl+K` | Session Switcher                                               |
| `w`      | Return to board                                                |
| `Esc`    | Step back: clear search, then leave chat, then return to board |

### Task Screen

| Key                   | Action                            |
| --------------------- | --------------------------------- |
| `1` / `2`             | Switch tabs                       |
| `a` / `x` / `m` / `b` | Approve / reject / merge / rebase |
| `Ctrl+F`              | Fullscreen AI chat (when open)    |
| `Esc`                 | Back                              |
