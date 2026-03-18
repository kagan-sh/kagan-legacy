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
- `Enter` opens selected task workflow, `Space` cycles AI split overlay, `/` toggles search
- `p` opens task peek overlay without changing chat layout
- `x` deletes selected task (with confirm), `s` starts agent, `Shift+S` stops agent
- `Shift+Left/Right` moves task between workflow columns
- `Ctrl+R` opens repo picker; Quick Actions (`Ctrl+Shift+P`) handles rare actions

______________________________________________________________________

## 3. Task Authoring

- `n` opens create flow; `e` edits selected task
- Save/cancel behavior in editor follows `Ctrl+S`/`Esc`

______________________________________________________________________

## 4. Task Screen

- Shows task context, diff, stream, and AI Panel
- Agent status panel displays backend, status, elapsed time, run ID, PID, context window usage, and cumulative cost
- AGENT_STATUS events update context window and cost metrics in real-time
- `a` approve, `x` reject, `m` merge, `b` rebase
- AI review is Quick Actions first on task screen (`Ctrl+Shift+P` -> `review.ai`)
- `Esc` returns to board

______________________________________________________________________

## 5. AI Panel

- Two modes: orchestrator and task session
  - `Ctrl+I` toggles AI Panel, `Space` cycles split layout, `Ctrl+F` fullscreen while open, `Ctrl+K` Session Switcher, `Esc` close
- `Enter` send, `Shift+Enter` newline, `Tab` accept completion
- `Ctrl+C` clears input text; `Esc` stops the active agent

______________________________________________________________________

## 6. Session & Backend

- Session Dashboard shows runtime, pipeline, output, changes, commits, and diff preview
- Backend selection and session switching are available from overlays and pickers

______________________________________________________________________

## 7. Keybindings Snapshot

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

| Key                | Action               |
| ------------------ | -------------------- |
| `n` / `Shift+N`    | New PAIR / AUTO task |
| `Enter`            | Open task flow       |
| `Space`            | Cycle AI split       |
| `p`                | Peek                 |
| `e`                | Edit                 |
| `x`                | Delete (confirm)     |
| `s` / `Shift+S`    | Start / stop agent   |
| `Shift+Left/Right` | Move task            |
| `/`                | Search               |

### Task Screen

| Key                   | Action                            |
| --------------------- | --------------------------------- |
| `1` / `2`             | Switch tabs                       |
| `a` / `x` / `m` / `b` | Approve / reject / merge / rebase |
| `Space`               | Cycle AI split                    |
| `Ctrl+F`              | Fullscreen AI chat (when open)    |
| `Esc`                 | Back                              |
