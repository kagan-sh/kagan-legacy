# TUI Features

Observable behaviors of `kagan.tui`. Each section maps to a test file in `tests/tui/`.
Implementation details live in `docs/internal/architecture/tui.md`.

______________________________________________________________________

## 1. Welcome & Onboarding

- App launches to a welcome screen showing the KAGAN logo and a project list
- Project list shows each project's name, repo count, and relative timestamp inline
- Select a project → opens the kanban board
- CWD suggestion banner appears only when the current directory is not already linked to a project
- Create a new project with name and repo path (via onboarding flow)
- First-run setup flow: choose default agent backend, default launcher, auto-review preference
- If a recent project exists, optionally skip welcome and go straight to the board

______________________________________________________________________

## 2. Kanban Board

- Four columns: BACKLOG, IN PROGRESS, REVIEW, DONE
- Tasks appear as sparse cards; detailed task data is shown in a docked inspector panel
- Vim-style navigation: h/j/k/l moves between columns and cards
- `/` opens search — supports `@status`, `@priority`, `@mode`, and `@sort` tokens
- Search preset pills expose common filters/sorts (Review, Active, Backlog, High Priority, Recent, Priority)
- `Enter` opens task inspector for the selected card (does not leave the board)
- `Esc` closes inspector/peek/search in place before leaving context
- Space peeks at a task (full description, notes, status) without leaving the board
- Ctrl+R opens a project/repo picker to switch context
- Board refreshes automatically when task state changes

______________________________________________________________________

## 3. Task Authoring

- `n` opens a task creation form (title, description, priority, execution mode)
- Enter on a card opens it for editing
- `D` duplicates the selected task into BACKLOG
- `d` deletes with confirmation

______________________________________________________________________

## 4. Task Output

- From Kanban: `Enter` opens inspector, then `o`/`p` opens the selected task session screen
- Agent output streams live: text chunks, tool calls, plan proposals
- Auto-scrolls to bottom; manual scroll pauses auto-scroll
- Enter starts execution when idle, Ctrl+C stops it
- Follow-up messages can be sent to a running agent
- Past executions are viewable when no live run is active

______________________________________________________________________

## 5. Review & Diff

- `r` on a REVIEW task opens the review modal
- Shows diff stats (files changed, insertions, deletions) and scrollable unified diff
- `a` approves, `x` rejects (opens feedback input), `b` rebases
- Empty diff shows a "no changes" state
- Rebase conflicts display a summary of affected files

______________________________________________________________________

## 6. Chat Overlay

- Chat panel with two modes: orchestrator chat (`Ctrl+O`) and task chat (`Ctrl+P`)
- Send messages, receive streamed responses with markdown rendering
- Slash commands: `/help`, `/clear`, `/agents [backend]`
- Permission prompts appear inline when the agent requests approval
- Chat persists across card navigation within the board

______________________________________________________________________

## 7. Session & Backend

- From Kanban: `Enter` inspect first, then `o`/`p` opens PAIR attach/start flow
- Pre-launch gateway checks backend dependencies (tmux, IDE, etc.)
- Missing dependencies show actionable install instructions
- Agent picker lets the user choose from registered backends
- Backends not on PATH are shown as "not installed"

______________________________________________________________________

## 8. Settings

- Settings screen for user preferences (default agent, default launcher, etc.)
- Accessible from the kanban board

______________________________________________________________________

## 9. Help

- Help screen showing keybinding reference
- Accessible from any screen

______________________________________________________________________

## 10. Session Picker

- Modal for listing and switching between sessions
- Shows session metadata (mode, status, agent)

______________________________________________________________________

## 11. Chat Modes

- Orchestrator mode: project-level chat for task planning and coordination
- Task mode: chat scoped to a specific task's agent session
- Mode switching between orchestrator and task chat

______________________________________________________________________

## 12. Keybindings

### Global (all screens)

| Key    | Action                                                                    |
| ------ | ------------------------------------------------------------------------- |
| Ctrl+Q | Quit — shows confirmation popup (configurable via `confirm_quit` setting) |
| ?      | Help                                                                      |
| .      | Command palette                                                           |

### Kanban Board

| Key       | Action                       |
| --------- | ---------------------------- |
| j/k (↓/↑) | Next / previous card         |
| h/l (←/→) | Previous / next column       |
| Enter     | Open inspector               |
| o / p     | Open task session            |
| Space     | Peek overlay                 |
| n         | New task                     |
| x / y     | Delete (confirm) / Duplicate |
| /         | Search / filter              |
| r         | Open review modal            |
| Ctrl+O    | Orchestrator chat            |
| Ctrl+P    | Task chat                    |
| Ctrl+R    | Repo picker                  |

### Chat Panel

| Key         | Action                  |
| ----------- | ----------------------- |
| Enter       | Send message            |
| Shift+Enter | Newline                 |
| Tab         | Accept slash completion |
| Escape      | Close / dismiss plan    |

### Task Output

| Key    | Action                                               |
| ------ | ---------------------------------------------------- |
| Enter  | Start agent (when idle) / focus input (when running) |
| Ctrl+C | Stop agent                                           |
| Escape | Back to kanban                                       |

### Review Modal

| Key    | Action                  |
| ------ | ----------------------- |
| a      | Approve                 |
| x      | Reject (feedback input) |
| b      | Rebase                  |
| Escape | Dismiss                 |

______________________________________________________________________

## 13. Session Dashboard

- Enter on a running AUTO task in IN_PROGRESS opens the session dashboard
- Dashboard shows six information panels in a two-column layout:
  - **Agent Status**: backend name, run status (Running/Completed/Failed), elapsed time, run ID, PID
  - **Persona Pipeline**: horizontal map of planned personas (e.g., `✓ ANALYST → ✓ PLANNER → ● IMPLEMENTER → ○ REVIEWER`) with current step highlighted
  - **Live Output**: latest agent output chunks and active tool calls with auto-scroll
  - **Worktree Changes**: file-level diff stats (files changed, insertions, deletions) per modified file
  - **Commits**: chronological list of commits on the task branch since diverging from base
  - **Diff Preview**: unified diff of the currently selected file
- Agent status panel updates every second (elapsed time, run status)
- Persona pipeline shows completion state: `✓` completed, `●` running, `○` pending
- When no persona pipeline is active, the persona panel is hidden
- Ctrl+O opens a docked chat overlay pre-connected to the running agent's output stream
- Ctrl+P opens the chat overlay in fullscreen mode
- Chat overlay streams live agent output; user can type messages to interject with the running agent
- Tab cycles between task agent and orchestrator sessions within the chat overlay
- When chat overlay opens, the dashboard collapses to a compact single-line status bar (task title, agent status, persona progress)
- Ctrl+C cancels the running agent
- Escape pops back to the kanban board
- Dashboard auto-refreshes worktree changes and commits periodically while the agent runs

______________________________________________________________________

### Session Dashboard Keybindings

| Key    | Action                                                    |
| ------ | --------------------------------------------------------- |
| Enter  | Start agent (when idle) / focus chat input (when running) |
| Ctrl+O | Toggle docked chat overlay (agent stream)                 |
| Ctrl+P | Toggle fullscreen chat overlay                            |
| Tab    | Cycle chat session (task / orchestrator)                  |
| Ctrl+C | Cancel running agent                                      |
| Ctrl+R | Repo picker                                               |
| j/k    | Navigate diff file list                                   |
| Escape | Back to kanban board                                      |
