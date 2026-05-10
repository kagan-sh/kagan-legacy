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
- `Ctrl+.` toggles the **Sessions** overlay (unified orchestrator/session chat), `/` toggles search
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
- `Ctrl+.` explicitly moves focus into the chat input; opening or creating a session also moves focus into chat
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

- Shows task context in header + Overview / Changes / Review tabs
- Agent status panel displays backend, status, elapsed time, run ID, PID, context window usage, and cumulative cost
- AGENT_STATUS events update context window and cost metrics in real-time
- `a` approve, `x` reject, `m` merge, `b` rebase
- AI review is Quick Actions first on task screen (`Ctrl+Shift+P` -> `review.ai`)
- `Esc` returns to board

______________________________________________________________________

## 6. Session Overlay

- Two modes: orchestrator and task session
  - `Ctrl+.` toggles Session Overlay, `Ctrl+F` / `Ctrl+Shift+F` expand and fullscreen the chat surface where bound, `Ctrl+K` Session Switcher, `Esc` close
- Streaming output appends fragments as they arrive, drains words on a short timer, and follows the newest content without duplicating finalized text
- `Enter` send, `Shift+Enter` newline, `Tab` accept completion
- `Ctrl+C` clears input text; `Esc` stops the active agent

______________________________________________________________________

## 7. Session & Backend

- TaskScreen is the default TUI route for task inspection and follow-up work
- WorkspaceScreen is the default TUI route for orchestrator-first conversation work
- Session Dashboard exists in the codebase for dedicated run monitoring, but is not the default board navigation target today
- Backend selection and session switching are available from overlays and pickers

## 7a. Diagnostics & Analytics Modals

- DoctorModal (`screens/doctor_modal.py`) — runs the same checks as `kagan doctor` from inside the TUI; supports `tldr`/`short`/`technical` verbosity views
- AnalyticsModal (`screens/analytics.py`) — surfaces backend success rates and session timeline data (read-only) without leaving the board

______________________________________________________________________

## 7b. Orchestrator Overlay

- `Ctrl+Space` opens or closes `OrchestratorOverlay` from any screen (APP binding **Orchestrator (toggle)**); pressing the chord again while the overlay is focused dismisses it.
  *Tests:* `tests/tui/test_orchestrator_overlay.py`.
- The overlay has two modes: orchestrator (talks to the project orchestrator
  chat session) and session (re-streams a worker / reviewer session from
  persisted events plus the core task event stream).
- `Esc` from a session stream returns back to orchestrator; `Esc` from
  orchestrator closes the overlay.
- A `SessionList` under the chat input lists active sessions; `↓` from
  the input focuses the list, `Enter` switches, `Esc` returns focus to the
  input. *Tests:* `tests/tui/test_session_list.py`.
- `Ctrl+Up` / `Ctrl+Down` cycle the attached stream through
  `[Orchestrator, ...running workers/reviewers]`. Selection is matched by
  `session_id`, so the choice is stable across polls even when the running
  set reorders.
- The overlay footer is mode-aware: when `ChatPanel` runs in `overlay`
  footer mode, hint keys that the parent screen would shadow (for example
  `Ctrl+.`) are dropped so the hint advertises only keys that
  fire inside the overlay.
- Replay of a finished agent session is rendered instantly — the typewriter
  animation runs only on live tokens. Reattaching to a closed session no
  longer re-animates its history.
- `TaskScreen` auto-pushes the overlay for `BACKLOG` tasks and auto-attaches
  to the resolved active session for in-progress tasks.
  *Tests:* `tests/tui/test_task_screen_auto_attach.py`.
- `TaskScreen` no longer embeds a chat panel — it is a header + Overview /
  Changes / Review tabs + `#ts-chat-hint` widget.
  *Tests:* `tests/tui/test_task_screen_no_embedded_chat.py`.

### Long-lived ACP factory

- `LongLivedACPFactory` (`src/kagan/core/chat/_factories.py`) auto-restarts
  once on `BrokenPipeError`, `ConnectionResetError`, or `acp.RequestError`,
  and probes process liveness before each prompt. After the second failure
  in a row the factory surfaces the underlying error.
- Empty turns no longer write a fabricated `"No response from orchestrator"`
  history row. If the agent produced no response, the turn is dropped from
  history rather than persisted as a placeholder.

### Degraded-mode boot warning

- `_is_optional_backend_warning` (`src/kagan/tui/app.py`) gates the boot
  toast: a `WARN` row is treated as informational when it is a per-backend
  check (`agent_backend:*`) **and** at least one other backend check is
  passing. The "Degraded mode" toast no longer appears when the only
  warnings are missing optional non-default backends.
- Telemetry (`emit_doctor_warned_telemetry_async`) still fires on raw
  counts so signal is preserved.

______________________________________________________________________

## 8. Keybindings Snapshot

### Global

| Key            | Action                |
| -------------- | --------------------- |
| `?` / `F1`     | Help                  |
| `Ctrl+Shift+P` | Quick Actions         |
| `Ctrl+O`       | Project selector      |
| `Ctrl+R`       | Repository selector   |
| `Ctrl+,`       | Settings              |
| `Ctrl+Q`       | Quit                  |
| `Ctrl+Space`   | Orchestrator (toggle) |

### Kanban

| Key                | Action                                               |
| ------------------ | ---------------------------------------------------- |
| `n`                | New task                                             |
| `Enter`            | Open task flow                                       |
| `w`                | Switch to workspace                                  |
| `a`                | Attach interactive run (stops managed run if active) |
| `Ctrl+.`           | Sessions overlay                                     |
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
| `Ctrl+.` | Focus chat input                                               |
| `Ctrl+K` | Session Switcher                                               |
| `w`      | Return to board                                                |
| `Esc`    | Step back: clear search, then leave chat, then return to board |

### Task Screen

| Key                   | Action                            |
| --------------------- | --------------------------------- |
| `1` / `2` / `3`       | Switch tabs                       |
| `a` / `x` / `m` / `b` | Approve / reject / merge / rebase |
| `Esc`                 | Back                              |

### Orchestrator Overlay

| Key                     | Action                                      |
| ----------------------- | ------------------------------------------- |
| `Ctrl+Up` / `Ctrl+Down` | Cycle through orchestrator + running agents |
| `↓` (from chat input)   | Move focus to running-agents bar            |
| `Enter` (from bar)      | Attach to highlighted agent                 |
| `Esc`                   | Detach (when attached) / close overlay      |

______________________________________________________________________

## 9. Design System Compliance

The TUI is the flagship surface and holds to the strictest interpretation of
the Kagan design system. Canonical spec:
`kagan-design-system/project/README.md` and `kagan-design-system/project/ui_kits/tui/`.

### Casing rules enforced in this codebase

| Surface                  | Rule          | Token examples                             |
| ------------------------ | ------------- | ------------------------------------------ |
| Column headers           | UPPERCASE     | `BACKLOG` `IN PROGRESS` `REVIEW` `DONE`    |
| Eyebrow / section labels | UPPERCASE     | `CHANGES` `AGENT LOG` `PLAN` `SESSIONS`    |
| Mode badges              | UPPERCASE     | `AUTO` `PAIR`                              |
| Modal titles             | Sentence case | `Delete task` `Approve task?` `Kagan help` |
| Toast / notify text      | Sentence case | `Merged and moved to done`                 |
| Keybinding descriptions  | lowercase     | `new task` `open` `back` `approve`         |

### Forbidden content

- No emoji (`📋`, etc.). Use `✓` `✗` `▸` `●` or plain ASCII `!` instead.
- `⚠` (U+26A0) is replaced with `!` throughout.
- No exclamation marks in toasts or modal copy.
- No hype words ("blazing", "super-charged", etc.).

### Motion preference

Set `REDUCED_MOTION=1` in the environment to disable spinner / pulse animations.
`MOTION_REDUCED` in `src/kagan/tui/theme.py` is the authoritative flag; `StatusBar`
consults it before starting its wave-frame timer.
