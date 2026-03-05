# TUI Architecture

> Thin presentation shell over `kagan.core`. No business logic, no DB, no agents.
> Core calls TUI back via events in DB. TUI pulls them with workers.

______________________________________________________________________

## References

| Package     | Repo                                                        | Use                                                                                                     |
| ----------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Textual** | [Textualize/textual](https://github.com/Textualize/textual) | TUI framework: App, Screen, Widget, reactive, CSS, workers, message passing.                            |
| **Toad**    | [anthropics/toad](https://github.com/anthropics/toad)       | AI agent TUI reference: agent chat, terminal integration, ACP patterns.                                 |
| **Loguru**  | [Delgan/loguru](https://github.com/Delgan/loguru)           | Structured logging. Config and sink setup in core — see `docs/internal/architecture/core.md` § Logging. |

______________________________________________________________________

## Design Principles

- **Thin shell**: TUI calls core's async API, observes progress via `task.events.stream()`. Zero business logic in `kagan.tui`.
- **Compose over inherit**: Build screens from small widgets, not deep class trees.
- **Reactive state**: Textual's `reactive`/`var` for all mutable state. Watch methods drive re-renders, never manual refresh.
- **Message-driven**: Widgets communicate via Textual messages, not direct method calls. Data binding flows down, messages bubble up.
- **Flat structure**: `screens/` and `widgets/` each one file per concept. No sub-sub-directories.
- **CSS for layout**: All visual concerns in `.tcss` files, not Python.

______________________________________________________________________

## Core Integration

### How TUI uses core

`KaganApp` holds a `KaganCore` instance, created during `on_mount`. No adapter,
no protocol wrapper — screens and widgets call core's namespaced API directly through
`self.app.core`.

| Namespace        | Example operations                                     |
| ---------------- | ------------------------------------------------------ |
| `core.tasks`     | `list`, `create`, `set_status`, `run`, `events.stream` |
| `core.projects`  | `list`, `create`, `set_active`                         |
| `core.worktrees` | `diff`                                                 |
| `core.reviews`   | `approve`, `merge`                                     |
| `core.settings`  | `get`, `set`                                           |

### Observing progress — workers, not callbacks

Core writes events to the `run_events` table. TUI consumes them in exclusive Textual

workers that iterate over `core.tasks.events.stream(task_id)`. The stream uses reactive
`asyncio.Event` signaling — when core's `_emit()` fires, the stream wakes immediately
with near-zero latency and zero idle cost.

Each worker posts Textual messages for every event it receives. No `CoreHooks`,
no `call_from_thread`, no callback bridging. One pattern:
**worker pulls `tasks.events.stream()`, posts Textual messages.**

### Testing

Real database, real git, real services. The only fake is the agent (`FakeAgentFactory`).
Tests flow through the `KaganDriver` DSL — they never import TUI widgets or screens
directly. See the Testing Philosophy section below for full details.

### Dependency Direction

```
kagan.tui ──► kagan.core    (KaganCore: task ops, project ops, event streaming)
kagan.tui ──► kagan.chat    (ChatSession: slash commands, conversation state)

kagan.core ──✘──► kagan.tui   NEVER
kagan.chat ──✘──► kagan.tui   NEVER
kagan.mcp  ──✘──► kagan.tui   NEVER
kagan.cli  ──✘──► kagan.tui   NEVER
```

______________________________________________________________________

## App & Screen Hierarchy

```
KaganApp (Textual App)
│
├── WelcomeScreen            # Logo, CWD banner (conditional), project OptionList
│   └── OnboardingFlow          # Modal: default agent backend, default launcher, auto-review

│
├── KanbanScreen             # Main screen after project selected
│   ├── BoardView            # 4-column kanban (BACKLOG → DONE)
│   ├── TaskInspector        # Docked details panel opened from board selection
│   ├── ChatPanel            # Docked / fullscreen AI chat overlay
│   └── PeekOverlay          # Task preview on Space
│
├── KanbanChatScreen         # Dedicated kanban + chat (orchestrator / task chat modes)
│
├── TaskScreen              # Pushed from kanban for AUTO tasks (idle / past runs)
│
├── SessionDashboardScreen   # Pushed from kanban for running AUTO tasks
│   ├── AgentStatusPanel     # Backend, status, elapsed, run ID, PID
│   ├── PersonaPipelineMap   # Horizontal persona sequence with current step
│   ├── LiveOutputPanel      # Latest agent output + tool calls (auto-scroll)
│   ├── WorktreePanel        # File-level diff stats per modified file
│   ├── CommitsPanel         # Task-branch commits since base
│   ├── DiffPreviewPanel     # Unified diff of selected file
│   └── ChatPanel            # Docked / fullscreen overlay streaming from agent
│
├── ReviewModal              # Pushed when task enters REVIEW
│
├── RepoPickerModal          # Ctrl+R — switch project / repo
│
├── TmuxGatewayModal             # Pre-launch backend readiness check

│
├── AgentPickerModal         # Select agent backend for task execution
│
├── ConfirmModal             # Generic confirmation dialog
│
├── HelpScreen               # Keybinding reference
│
├── SessionPickerModal       # Session list / switch
│
├── SettingsScreen           # User preferences
│
├── TaskEditorModal          # Inline task create/edit form
│
└── RejectionInputModal      # Review rejection feedback input
```

### Screen Transitions

```
WelcomeScreen ──select project──→ KanbanScreen (switch)
KanbanScreen  ──Enter──────────────────→ Open/refresh TaskInspector (in-place)
KanbanScreen  ──O/P on selected task──→ TaskScreen or PAIR attach flow (push/attach)
KanbanScreen  ──r on REVIEW───→ ReviewModal (push)
KanbanScreen  ──Ctrl+R────────→ RepoPickerModal (push)
Any screen    ──Escape─────────→ pop (back to previous)
```

Screens are lazy — instantiated on first navigation via a `SCREENS` map of names to
factory callables.

______________________________________________________________________

## Widget Composition

Key composition (the primary screen):

```
KanbanScreen
├── Header              # project name, connection status
├── BoardView + TaskInspector (horizontal pane)
│   └── Column × 4      → [TaskCard, ...]
├── PeekOverlay         # hidden by default, shown on Space
├── ChatPanel           # toggleable, docked right or fullscreen
│   ├── MessageList / ChatInput / SlashComplete
│   ├── PlanDisplay / PermissionPrompt
└── Footer              # keybinding hints
```

Other screens follow the same pattern — Header, content area, Footer.
Full widget-to-file mapping is in the File Layout section below.

______________________________________________________________________

## State Management

### Reactive Declarations

| Owner        | Name           | Type                        | Purpose                    |
| ------------ | -------------- | --------------------------- | -------------------------- |
| KaganApp     | `project`      | `reactive[Project \| None]` | Currently active project   |
| KanbanScreen | `tasks`        | `reactive[list[Task]]`      | Tasks for the board        |
| KanbanScreen | `selected`     | `var[str \| None]`          | Selected task ID           |
| KanbanScreen | `filter_text`  | `var[str]`                  | Search filter              |
| KanbanScreen | `chat_visible` | `var[bool]`                 | Chat panel toggle          |
| TaskScreen   | `run`          | `reactive[Session \| None]` | Active execution run       |
| TaskScreen   | `running`      | `var[bool]`                 | Whether agent is executing |

### Data Flow Direction

- **Down** — parent to child via `data_bind`. Parent composes a child widget and binds a
  reactive property to it. When the parent's value changes, the child updates automatically.
- **Up** — child to parent via Textual message bubbling. Widgets define `Message` subclasses;
  parent screens handle them with `@on()` decorators.

### Watch Methods

Watch methods fire automatically when a reactive or var changes value:

| Owner        | Watches        | Effect                                     |
| ------------ | -------------- | ------------------------------------------ |
| KanbanScreen | `tasks`        | Refreshes BoardView columns                |
| KanbanScreen | `chat_visible` | Toggles CSS class to show/hide ChatPanel   |
| KanbanScreen | `filter_text`  | Filters `_all_tasks` and reassigns `tasks` |
| TaskScreen   | `session`      | Updates header status badge                |

______________________________________________________________________

## Navigation & Keybindings

Bindings are declared as static `BINDINGS` lists on each screen class. Shown bindings
appear in the footer; hidden bindings (vim motions) work but don't clutter the UI.

Full keybinding tables are in `docs/internal/features/tui.md`.

______________________________________________________________________

## Chat Integration

### ChatSession lives in `kagan.chat`

`ChatSession` is a conversational abstraction over core's agent streaming. It lives in
`kagan.chat`, not in core or TUI. Both TUI and CLI import it.

ChatSession wraps core primitives:

- Agent spawning via `core.task.run()`
- Event consumption via `core.task.events.stream()` (reactive signaling)
- Slash command parsing
- Plan mode state machine

| Member     | Type                | Purpose                                   |
| ---------- | ------------------- | ----------------------------------------- |
| `messages` | `list[ChatMessage]` | Conversation history                      |
| `mode`     | `ChatMode`          | NORMAL or PLAN                            |
| `plan`     | `Plan \| None`      | Current plan proposal (when in PLAN mode) |

| Method                      | Description                        |
| --------------------------- | ---------------------------------- |
| `send(text)`                | Send a user message to the agent   |
| `send_slash(command, args)` | Execute a slash command            |
| `approve_plan()`            | Approve the current plan proposal  |
| `reject_plan(feedback?)`    | Reject plan with optional feedback |
| `cancel()`                  | Cancel the current agent execution |

### TUI Chat Binding

ChatPanel holds a `ChatSession` as a reactive `var`. An exclusive worker iterates over
the session's stream and posts `NewChatMessage` Textual messages for each incoming event.
The stream uses the same reactive `asyncio.Event` signaling as `task.events.stream()`.

Slash commands and plan/permission flows are behavioral — see `docs/internal/features/tui.md`.

______________________________________________________________________

## Styling Strategy

Three TCSS layers, ascending specificity:

1. **Widget `DEFAULT_CSS`** — scoped to widget class, lowest specificity.
1. **`app.tcss`** — global variables, base layout, theme.
1. **Screen-specific** (`kanban.tcss`, `chat.tcss`) — highest, only where needed.

```
styles/
├── app.tcss        # theme vars ($primary, $surface, etc.), global layout
├── kanban.tcss     # board columns, card styles, peek overlay
└── chat.tcss       # chat panel, messages, input, plan display
```

Visibility toggles use CSS classes (e.g., `.chat-hidden` hides ChatPanel, `.peek-visible`
shows PeekOverlay). Responsive breakpoints handle narrow terminals — columns stack
vertically below 80 columns.

______________________________________________________________________

## File Layout

```
src/kagan/tui/
├── __init__.py              # re-exports KaganApp
├── app.py                   # KaganApp — top-level Textual App
├── messages.py              # all custom Message classes
├── keybindings.py           # binding tables per screen
├── types.py                 # shared type aliases
│
├── screens/
│   ├── __init__.py           # screen exports
│   ├── welcome.py           # WelcomeScreen
│   └── setup.py             # OnboardingFlow (modal)
│   ├── kanban.py            # KanbanScreen
│   ├── kanban_chat.py       # KanbanChatScreen (orchestrator/task chat modes)
│   ├── task_screen.py        # TaskScreen
│   ├── review.py            # ReviewModal
│   ├── repo_picker.py       # RepoPickerModal
│   ├── gateway.py           # TmuxGatewayModal
│   ├── agent_picker.py      # AgentPickerModal
│   ├── confirm.py           # ConfirmModal
│   ├── help.py              # HelpScreen
│   ├── session_picker.py    # SessionPickerModal
│   ├── settings.py          # SettingsScreen
│   ├── task_editor_modal.py # TaskEditorModal
│   └── rejection_input.py   # RejectionInputModal
│   ├── session_dashboard.py # SessionDashboardScreen (running AUTO task monitor)
│
├── widgets/
│   ├── __init__.py           # widget exports
│   ├── board.py             # BoardView, Column
│   ├── card.py              # TaskCard
│   ├── peek.py              # PeekOverlay
│   ├── task_editor.py       # TaskEditor (create/edit form)
│   ├── chat.py              # ChatPanel, MessageList, ChatInput, SlashComplete
│   ├── streaming.py         # StreamingOutput, OutputChunk, ToolCallView

│   ├── diff.py              # DiffView, DiffStats
│   ├── plan.py              # PlanDisplay
│   ├── permission.py        # PermissionPrompt
│   ├── header.py            # Header
│   ├── hint_bar.py          # HintBar (contextual keybinding hints)
│   └── search_bar.py        # SearchBar (board filter input)
│   ├── agent_status.py      # AgentStatusPanel (backend, status, elapsed, PID)
│   ├── persona_pipeline.py  # PersonaPipelineMap (horizontal persona chain)
│   ├── worktree_panel.py    # WorktreePanel (file change stats table)
│   └── commits_panel.py     # CommitsPanel (task-branch commit log)
│
└── styles/
    ├── app.tcss             # global theme + layout
    ├── kanban.tcss          # board styles
    └── chat.tcss            # chat styles
    └── session_dashboard.tcss  # dashboard layout + panels
```

~43 files. Each file has one clear responsibility.

______________________________________________________________________

## Testing

See `docs/internal/testing.md` for the full testing guide.

TUI-specific:

- Use `app.run_test()` with `Pilot`, not manual event loops
- Use targeted waits (`wait_for_screen`, `pilot.pause()`), never `wait_for_workers()`

______________________________________________________________________

## Data Flow Summary

All screens/widgets call core's namespaced API directly via `self.app.core`.
Workers iterate `core.task.events.stream()` — reactive `asyncio.Event` signaling,
near-zero latency, zero idle cost. Data flows down via `data_bind`, messages
bubble up via Textual message passing. Watch methods fire on reactive changes.

______________________________________________________________________

## Session Dashboard Screen

### Purpose

A dedicated monitoring screen for running AUTO tasks. Shows all relevant
information about the active agent session: worktree changes, commits,
agent status, persona pipeline progress, live output, and unified diffs.
Supports chat overlay for streaming agent output and user interjection.

### Layout

Two-column, six-panel layout. Left column: agent status, persona pipeline,
live output. Right column: worktree changes, commits, diff preview.

```
SessionDashboardScreen
├── KaganHeader
├── DashboardStatusBar       # Task title, branch, compact status + persona
├── Horizontal (dashboard-body)
│   ├── Vertical (left-col)
│   │   ├── AgentStatusPanel     # Backend, status badge, elapsed, run ID, PID
│   │   ├── PersonaPipelineMap   # Horizontal ✓/●/○ persona chain
│   │   └── StreamingOutput      # Latest output + tool calls (reused widget)
│   └── Vertical (right-col)
│       ├── WorktreePanel        # File change summary table
│       ├── CommitsPanel         # Commit log since base branch
│       └── DiffView             # Unified diff (reused widget)
├── ChatPanel                # Overlay (hidden by default)
└── HintBar                  # Contextual keybinding hints
```

### Data Sources

| Panel              | Core API                                           | Refresh                  |
| ------------------ | -------------------------------------------------- | ------------------------ |
| AgentStatusPanel   | `tasks.get(id)` + Session query via DB             | 1s timer                 |
| PersonaPipelineMap | Session history for task + `Session.persona` field | On AGENT_COMPLETED event |
| StreamingOutput    | `tasks.events.stream(task_id)` (reactive)          | Real-time                |
| WorktreePanel      | `worktrees.diff_stats(task_id)`                    | 5s timer                 |
| CommitsPanel       | `worktrees.diff(task_id)` + git log                | 5s timer                 |
| DiffView           | `worktrees.diff(task_id)`                          | 5s timer                 |

### Chat Overlay Integration

Chat overlay follows the same pattern as `TaskScreen`:

- `Ctrl+O` opens docked overlay pre-connected to the running agent stream
- `Ctrl+P` opens fullscreen overlay
- `Tab` cycles between task agent and orchestrator sessions
- User messages sent via task chat interject with the running agent
  (cancel current run, append to description, restart)
- Orchestrator messages go through the separate orchestrator flow

When the chat overlay opens, the dashboard body gets a CSS class
`dashboard-chat-active` that collapses the six-panel layout into a
compact status bar, giving maximum vertical space to the chat.

### Persona Pipeline Visualization

The `PersonaPipelineMap` widget renders the persona execution plan as a
horizontal chain of steps:

```
✓ ANALYST  ─→  ✓ PLANNER  ─→  ● IMPLEMENTER  ─→  ○ REVIEWER
                                   (3/4)
```

State symbols: `✓` completed (dim green), `●` running (bright yellow,
animated), `○` pending (dim). The pipeline is derived from:

1. Query all `Session` records for the task, ordered by `started_at`
1. Each run with a non-null `persona` field maps to a step
1. The latest run's status determines the `●` running indicator
1. If no runs have `persona` set, the widget is hidden

### File Layout

```
src/kagan/tui/
  screens/
    session_dashboard.py     # SessionDashboardScreen
  widgets/
    agent_status.py          # AgentStatusPanel
    persona_pipeline.py      # PersonaPipelineMap
    worktree_panel.py        # WorktreePanel
    commits_panel.py         # CommitsPanel
  styles/
    session_dashboard.tcss   # Dashboard-specific styles
```

### Navigation

```
KanbanScreen
  │
  ├─ Enter ──────────────────────→ show TaskInspector (in place)
  ├─ O/P on AUTO task ───────────→ TaskScreen (push)
  └─ O/P on PAIR task ───────────→ Attach/launch session

SessionDashboardScreen
  ├─ Escape ──────────────────→ pop back to KanbanScreen
  ├─ Ctrl+O ──────────────────→ toggle docked chat overlay
  ├─ Ctrl+P ──────────────────→ toggle fullscreen chat
  └─ Ctrl+C ──────────────────→ cancel running agent
```
