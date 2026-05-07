# TUI Architecture

> Thin presentation shell over `kagan.core`. No business logic, no DB, no agents.
> Core calls TUI back via events in DB. TUI pulls them with workers.

______________________________________________________________________

## References

| Package     | Repo                                                        | Use                                                          |
| ----------- | ----------------------------------------------------------- | ------------------------------------------------------------ |
| **Textual** | [Textualize/textual](https://github.com/Textualize/textual) | TUI framework: App, Screen, Widget, reactive, CSS, workers   |
| **Loguru**  | [Delgan/loguru](https://github.com/Delgan/loguru)           | Structured logging. Config in core — see `core.md` § Logging |

______________________________________________________________________

## Design Principles

- **Thin shell**: TUI calls core's async API, observes progress via `task.events.stream()`
- **Compose over inherit**: Build screens from small widgets, not deep class trees
- **Reactive state**: Textual's `reactive`/`var` for mutable state; watch methods drive re-renders
- **Message-driven**: Widgets communicate via Textual messages; data flows down, messages bubble up
- **Flat structure**: One file per concept in `screens/` and `widgets/`
- **CSS for layout**: All visual concerns in `.tcss` files

______________________________________________________________________

## Core Integration

### How TUI uses core

`KaganApp` holds a `KaganCore` instance, created during `on_mount`. Screens/widgets call core's namespaced API directly via `self.app.core`:

| Namespace        | Operations                                             |
| ---------------- | ------------------------------------------------------ |
| `core.tasks`     | `list`, `create`, `set_status`, `run`, `events.stream` |
| `core.projects`  | `list`, `create`, `set_active`                         |
| `core.worktrees` | `diff`, `diff_stats`                                   |
| `core.reviews`   | `approve`, `merge`                                     |
| `core.settings`  | `get`, `set`                                           |

### Observing progress — workers

Core writes events to `run_events`. TUI consumes them in exclusive workers iterating over `core.tasks.events.stream(task_id)`. The stream uses reactive `asyncio.Event` signaling — when core's `_emit()` fires, the stream wakes immediately.

Each worker posts Textual messages for events. One pattern: worker pulls `tasks.events.stream()` and posts messages.

### Shutdown

`KaganApp.on_unmount()` awaits `core.aclose()` so active agent subprocess cleanup
finishes before Textual closes its event loop. Screens that own chat or event
stream tasks cancel and await those tasks in async `on_unmount()` handlers; do
not add fire-and-forget task cancellation paths on screen teardown.

### Dependency Direction

```text
kagan.tui ──► kagan.core    (KaganCore: task ops, project ops, event streaming)
kagan.tui ──► kagan.cli.chat    (ChatSession: slash commands, conversation state)

kagan.core ──✘──► kagan.tui   NEVER
kagan.cli.chat ──✘──► kagan.tui   NEVER
```

______________________________________________________________________

## App & Screen Hierarchy

```text
KaganApp (Textual App)
│
├── WelcomeScreen            # Logo, CWD banner, project OptionList
│   └── OnboardingFlow       # Modal: default agent backend, launcher, auto-review
│
├── KanbanScreen             # Main screen after project selected
│   ├── BoardView            # 4-column kanban (BACKLOG → DONE)
│   ├── TaskInspector        # Docked details panel
│   ├── ChatPanel            # Docked / fullscreen AI Panel
│   └── PeekOverlay          # Task preview on P
│
├── WorkspaceScreen          # Orchestrator-first workspace with session sidebar + full chat surface
│   ├── Session sidebar      # Searchable orchestrator conversation list
│   └── ChatPanel            # Full-width main conversation surface
│
├── (_chat_runner helpers)    # ACP payload extraction, stream chunk helpers (not a Screen)
│
├── TaskScreen               # Primary task detail screen pushed from kanban after inspector-open
│
├── SessionDashboardScreen   # Dedicated run-monitoring screen retained in the codebase but not on the default kanban navigation path
│   ├── AgentStatusPanel     # Backend, status, elapsed, run ID, PID
│   ├── PersonaPipelineMap   # Horizontal persona sequence with current step
│   ├── LiveOutputPanel      # Latest agent output + tool calls (auto-scroll)
│   ├── WorktreePanel        # File-level diff stats per modified file
│   ├── CommitsPanel         # Task-branch commits since base
│   ├── DiffPreviewPanel     # Unified diff of selected file
│   └── ChatPanel            # Docked / fullscreen AI Panel streaming from agent
│
├── RepoPickerModal          # Ctrl+R — switch project / repo
├── PairInstructionsModal    # Pre-launch backend readiness check
├── AgentPickerModal         # Select agent backend for task execution
├── GitHubImportModal        # GitHub issue/PR import flow
├── SessionPickerModal       # Session list / switch
├── SettingsModal            # User preferences
├── TaskEditorModal          # Inline task create/edit form
├── TutorialOverlay          # Interactive onboarding tutorial
├── ReviewNoCriteriaModal    # Shown when reviewers encounter tasks with no acceptance criteria
├── ConfirmModal             # Generic confirmation dialog
├── HelpModal                # Keybinding reference
├── MessageActionsModal      # Per-message action menu (copy, retry, etc.)
└── RejectionInputModal      # Review rejection feedback input
```

### Screen Transitions

```text
WelcomeScreen ──select project──→ KanbanScreen (switch)
KanbanScreen  ──Enter───────────→ TaskInspector (in-place)
KanbanScreen  ──Enter again────→ TaskScreen or attach flow (push)
KanbanScreen  ──w───────────────→ WorkspaceScreen (switch)
WorkspaceScreen ──w────────────→ KanbanScreen (switch)
WorkspaceScreen ──Esc──────────→ sidebar-first back flow, then KanbanScreen (switch)
KanbanScreen  ──Ctrl+R──────────→ RepoPickerModal (push)
Any modal/overlay ──Escape─────→ close overlay, then pop
```

10 screens are registered in `SCREENS` lazy-loading dict; modals are instantiated directly via `push_screen()`.

______________________________________________________________________

## Widget Composition

```text
KanbanScreen
├── KaganHeader              # Project name, connection status
├── BoardView + TaskInspector
│   └── Column × 4 → [TaskCard, ...]
├── PeekOverlay              # Hidden by default, shown on P
├── ChatPanel                # Toggleable, docked or fullscreen
│   ├── MessageList / ChatInput / SlashComplete
│   └── PermissionPrompt
└── KanbanHintBar            # Keybinding hints

SessionDashboardScreen
├── KaganHeader
├── DashboardStatusBar       # Task title, branch, status
├── Horizontal (dashboard-body)
│   ├── Vertical (left-col)
│   │   ├── AgentStatusPanel # Backend, status badge, elapsed, PID
│   │   ├── PersonaPipelineMap # Horizontal ✓/●/○ persona chain
│   │   └── StreamingOutput  # Latest output + tool calls
│   └── Vertical (right-col)
│       ├── WorktreePanel    # File change summary table
│       ├── CommitsPanel     # Commit log since base branch
│       └── DiffView         # Unified diff
├── ChatPanel                # Overlay (hidden by default)
└── HintBar                  # Contextual keybinding hints

WorkspaceScreen
├── KaganHeader
├── Vertical (workspace-sidebar; default focus target)
│   ├── Input                # Session search
│   └── OptionList           # Orchestrator sessions
├── Vertical (workspace-main)
│   ├── Workspace header     # Active conversation title + compact guidance
│   └── ChatPanel            # Main conversation surface (always visible; explicit focus via Ctrl+. or session open)
└── Footer hint row          # Workspace-specific navigation hints
```

______________________________________________________________________

## State Management

### Reactive Declarations

| Owner              | Name            | Type                        | Purpose                      |
| ------------------ | --------------- | --------------------------- | ---------------------------- |
| `KaganApp`         | `project`       | `reactive[Project \| None]` | Active project               |
| `KanbanScreen`     | `tasks`         | `reactive[list[Task]]`      | Board tasks                  |
| `KanbanScreen`     | `selected`      | `var[str \| None]`          | Selected task ID             |
| `KanbanScreen`     | `filter_text`   | `var[str]`                  | Search filter                |
| `KanbanScreen`     | `chat_visible`  | `var[bool]`                 | AI Panel open state          |
| `WorkspaceScreen`  | `session_items` | `list[ChatSessionListItem]` | Orchestrator session sidebar |
| `SessionDashboard` | `session`       | `reactive[Session \| None]` | Active execution run         |

WorkspaceScreen keeps navigation state intentionally simple:

- Sidebar focus is the entry point and safe default after screen switches
- `Ctrl+.` is the explicit handoff into chat input
- `Esc` unwinds focus in layers instead of jumping straight out of the screen

### Data Flow Direction

- **Down** — parent to child via `data_bind`. Parent composes child and binds reactive property.
- **Up** — child to parent via Textual message bubbling. Parent handles with `@on()` decorators.

### Watch Methods

| Owner              | Watches        | Effect                      |
| ------------------ | -------------- | --------------------------- |
| `KanbanScreen`     | `tasks`        | Refreshes BoardView columns |
| `KanbanScreen`     | `chat_visible` | Toggles ChatPanel CSS class |
| `KanbanScreen`     | `filter_text`  | Filters `_all_tasks`        |
| `SessionDashboard` | `session`      | Updates header status badge |

______________________________________________________________________

## Navigation & Keybindings

Bindings are declared as static `BINDINGS` lists on each screen. Shown bindings appear in the footer; hidden bindings (vim motions) work but don't clutter UI.

Full keybinding tables are in `docs/internal/features/tui.md`.

______________________________________________________________________

## Orchestrator Overlay

`OrchestratorOverlay` (`src/kagan/tui/screens/orchestrator_overlay.py`) is the
global agent-stream switcher mounted via `app.SCREENS["orchestrator-overlay"]`
and bound to `o` (and the hidden `Ctrl+Space` chord) on `APP_BINDINGS`. Pushing
the overlay while it is already active simply re-focuses its input.

Two modes:

| Mode             | Behaviour                                                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Orchestrator** | Sends messages to the project orchestrator chat session.                                                                          |
| **Attached**     | Re-streams a worker or reviewer session: replay via `/api/v1/sessions/{id}/replay`, live tail via `/api/v1/sessions/{id}/events`. |

`Esc` is layered: from an attached stream it detaches back to orchestrator
mode; from orchestrator mode it closes the overlay. `Ctrl+Space` mirrors `Esc`.

The overlay composes a breadcrumb header (`Orchestrator` /
`Worker · running · …`), a `ChatPanel`, and a `RunningAgentsBar`
(`src/kagan/tui/widgets/running_agents_bar.py`) under the chat input. The bar
polls `client.list_running_agents()`, renders one row per active session, and
on `Enter` posts an `AgentSelected` message carrying the target session id.
From the chat input, `↓` focuses the bar; from the bar, `Esc` returns focus to
the input. Keys are declared on `ORCHESTRATOR_OVERLAY_BINDINGS` /
`RUNNING_AGENTS_BAR_BINDINGS` in `keybindings.py`.

`TaskScreen` integrates with the overlay on show:

- `BACKLOG` tasks push the overlay automatically so the user can talk to the
  orchestrator about the task before launching an agent.
- In-progress tasks call `client.resolve_active_session(task_id)` and
  auto-attach to the resulting session when one exists.

### Removed surfaces

The overlay supersedes the embedded per-task chat:

- `screens/_task_chat.py` and `screens/_task_stream.py` were deleted.
- The embedded `ChatPanel` region inside `screens/_task_review.py` was removed.
- `TaskScreen` is now a header + tabs (Overview / Changes / Review) and a
  static `#ts-chat-hint` widget that points the user at the overlay.

References to `action_open_task_chat`, `_task_chat` mixins, and the per-screen
`ctrl+f` / `ctrl+.` chat bindings have been scrubbed across `app.py`,
`kanban.py`, `session_dashboard.py`, `_chat_runner.py`, and the
`task_event_handler` helpers.

______________________________________________________________________

## Chat Integration

### ChatSession

`ChatSession` lives in `kagan.cli.chat` (not core or TUI). It wraps core primitives:

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

`ChatPanel` holds a `ChatSession` as a reactive `var`. An exclusive worker iterates over the session's stream and posts `NewChatMessage` Textual messages for each event.

`StreamingOutput` and `OutputChunk` render task/session output progressively. Incoming fragments enqueue into the active chunk, a timer drains words with a short animation delay, and the scroll position follows live output unless the user is browsing older entries.

Slash commands and plan/permission flows are behavioral — see `docs/internal/features/tui.md`.

______________________________________________________________________

## Styling Strategy

Three TCSS layers, ascending specificity:

1. **Widget `DEFAULT_CSS`** — scoped to widget class, lowest specificity
1. **`app.tcss`** — global variables, base layout, theme
1. **Screen-specific** (`kanban.tcss`, `chat.tcss`) — highest, only where needed

```text
styles/
├── app.tcss              # theme vars ($primary, $surface, etc.)
├── kanban.tcss           # board columns, card styles
├── chat.tcss             # AI Panel, messages, input
├── task_screen.tcss      # task screen layout
├── session_dashboard.tcss # dashboard layout + panels
└── workspace.tcss        # workspace layout + session sidebar
```

Visibility toggles use CSS classes (e.g., `.chat-hidden`, `.peek-visible`). Responsive breakpoints stack columns vertically below 80 columns.

______________________________________________________________________

## File Layout

```text
src/kagan/tui/
├── __init__.py              # re-exports KaganApp
├── app.py                   # KaganApp — top-level Textual App
├── messages.py              # all custom Message classes
├── keybindings.py           # binding tables per screen
├── types.py                 # shared type aliases
├── _chat_helpers.py         # chat helper utilities
├── orchestrator_sessions.py # TuiOrchestratorSessionStore
├── textual_compat.py        # Textual compatibility workarounds
├── theme.py                 # KAGAN_THEME, KAGAN_THEME_256
│
├── screens/
│   ├── __init__.py
│   ├── welcome.py           # WelcomeScreen
│   ├── setup.py             # OnboardingFlow (modal)
│   ├── kanban.py            # KanbanScreen
│   ├── _chat_runner.py      # ACP payload + stream chunk helpers (not a Screen class)
│   ├── _task_review.py      # Task review screen helpers
│   ├── orchestrator_overlay.py  # OrchestratorOverlay ModalScreen — global agent stream switcher
│   ├── workspace.py         # WorkspaceScreen
│   ├── task_screen.py       # TaskScreen (header + Overview/Changes/Review tabs + chat hint)
│   ├── session_dashboard.py # SessionDashboardScreen
│   ├── analytics.py         # AnalyticsModal
│   ├── doctor_modal.py      # DoctorModal
│   ├── session_resume_modal.py
│   ├── file_picker.py
│   ├── review_no_criteria.py
│   ├── repo_picker.py
│   ├── gateway.py           # PairInstructionsModal
│   ├── agent_picker.py
│   ├── confirm.py
│   ├── github_import_modal.py
│   ├── message_actions_modal.py
│   ├── help.py
│   ├── session_picker.py
│   ├── settings.py
│   ├── task_editor_modal.py
│   ├── rejection_input.py
│   ├── kanban_commands.py   # Kanban command palette helpers
│   ├── task_commands.py     # Task command palette helpers
│   └── tutorial.py          # TutorialOverlay
│
├── widgets/
│   ├── __init__.py
│   ├── board.py             # BoardView, Column
│   ├── card.py              # TaskCard
│   ├── peek.py              # PeekOverlay
│   ├── task_editor.py       # TaskEditor (create/edit form)
│   ├── task_inspector.py    # TaskInspector
│   ├── task_diff_pane.py    # TaskDiffPane
│   ├── chat.py              # ChatPanel, MessageList, ChatInput, SlashComplete
│   ├── running_agents_bar.py # RunningAgentsBar — picker shown under the orchestrator overlay input
│   ├── streaming.py         # StreamingOutput, OutputChunk, ToolCallView
│   ├── diff.py              # DiffView, DiffStats
│   ├── permission.py        # PermissionPrompt
│   ├── header.py            # KaganHeader
│   ├── hint_bar.py          # KanbanHintBar
│   ├── status_bar.py        # StatusBar, SimpleFooter
│   ├── context_footer.py    # ContextFooter
│   ├── search_bar.py        # SearchBar
│   ├── agent_status.py      # AgentStatusPanel
│   ├── persona_pipeline.py  # PersonaPipelineMap
│   ├── worktree_panel.py    # WorktreePanel
│   ├── commits_panel.py     # CommitsPanel
│   └── task_detail_pane.py  # TaskDetailPane
│
└── styles/
    ├── app.tcss
    ├── kanban.tcss
    ├── chat.tcss
    ├── task_screen.tcss
    ├── session_dashboard.tcss
    └── workspace.tcss
```

~58 files, ~17K LOC. Each file has one clear responsibility.

______________________________________________________________________

## Testing

See `docs/internal/testing.md` for the full testing guide.

TUI-specific:

- Use `app.run_test()` with `Pilot`, not manual event loops
- Use targeted waits (`wait_for_screen`, `pilot.pause()`), never `wait_for_workers()`

______________________________________________________________________

## Data Flow Summary

All screens/widgets call core's namespaced API directly via `self.app.core`. Workers iterate `core.task.events.stream()` — reactive `asyncio.Event` signaling. Data flows down via `data_bind`, messages bubble up via Textual message passing. Watch methods fire on reactive changes.
