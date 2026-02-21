---
title: Keyboard Shortcuts
description: Every keybinding available in the TUI
icon: material/keyboard
---

# Keyboard Shortcuts

Mirrors the in-app help (press ++question++).

## Accessibility

- Header, footer, modal hint, and AI Assistant overlay text are tuned for WCAG AA contrast in both the full and 256-color themes.
- Focused controls always use a visible border change (primary accent) instead of dim-only states.
- If your terminal uses background transparency, turning it off improves practical contrast consistency.

## Essential

| Key          | Action                 |
| ------------ | ---------------------- |
| ++n++        | New task               |
| ++enter++    | Open details / confirm |
| ++a++        | Start agent (AUTO)     |
| ++s++        | Stop agent             |
| ++question++ | Help                   |
| ++period++   | Actions palette        |
| ++comma++    | Settings               |
| ++ctrl+q++   | Quit                   |

## Global

| Key                           | Action           |
| ----------------------------- | ---------------- |
| ++question++ / ++f1++         | Help             |
| ++period++ / ++ctrl+shift+p++ | Actions palette  |
| ++ctrl+shift+o++              | Project selector |
| ++ctrl+r++                    | Repo selector    |
| ++f12++                       | Debug log        |
| ++ctrl+q++                    | Quit             |

## Board (Kanban)

### Navigation

| Key               | Action                                   |
| ----------------- | ---------------------------------------- |
| ++h++ / ++left++  | Focus left column                        |
| ++l++ / ++right++ | Focus right column                       |
| ++j++ / ++down++  | Focus next card                          |
| ++k++ / ++up++    | Focus previous card                      |
| ++tab++           | Next column                              |
| ++shift+tab++     | Previous column                          |
| ++esc++           | Clear focus, close search, or close peek |

### Tasks

| Key         | Action                                                                                                                                  |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| ++n++       | New task                                                                                                                                |
| ++shift+n++ | New AUTO task                                                                                                                           |
| ++enter++   | Open task details                                                                                                                       |
| ++o++       | Open focused task session/output (AUTO Task Output session / PAIR backend / REVIEW output). Repeated presses are ignored while opening. |
| ++slash++   | Search tasks                                                                                                                            |
| ++v++       | View details                                                                                                                            |
| ++e++       | Edit task                                                                                                                               |
| ++x++       | Delete task                                                                                                                             |
| ++y++       | Duplicate task                                                                                                                          |
| ++c++       | Copy task ID                                                                                                                            |
| ++space++   | Peek overlay                                                                                                                            |
| ++f++       | Expand description                                                                                                                      |
| ++f5++      | Full editor                                                                                                                             |

### Workflow and agents

| Key                           | Action                                 |
| ----------------------------- | -------------------------------------- |
| ++shift+left++ / ++shift+h++  | Move task left                         |
| ++shift+right++ / ++shift+l++ | Move task right                        |
| ++a++                         | Start agent (AUTO)                     |
| ++s++                         | Stop agent (AUTO)                      |
| ++shift+d++                   | View diff (REVIEW)                     |
| ++r++                         | Open Task Output screen (REVIEW)       |
| ++m++                         | Merge (REVIEW)                         |
| ++ctrl+p++                    | Toggle fullscreen AI Assistant overlay |
| ++ctrl+o++                    | Toggle docked AI Assistant overlay     |
| ++b++                         | Set task branch                        |
| ++shift+g++                   | Repo Sync                              |
| ++comma++                     | Settings                               |

## AI Assistant overlay

The empty-state intro can occasionally show a random Kagan quote (funny or wise).
Startup behavior: if at least one task exists on the board, Kagan opens board-first with the
overlay closed. On empty boards, the fullscreen intro opens automatically.
The footer includes a session indicator and quick session palette so you can switch active
chat sessions directly at any scale.
Session quick-pick is two-pane: left side for orchestrator/task groups, right side for
session targets (worker/reviewer/orchestrator session).
Session quick-pick includes a Recent sessions group and a live `N sessions` filter match count.
In docked mode, board columns shrink above the overlay; when tickets exceed visible space, the
column list scrolls.

### Screen

| Key        | Action                                                                                                          |
| ---------- | --------------------------------------------------------------------------------------------------------------- |
| ++esc++    | Interrupt active stream; close overlay when idle                                                                |
| ++ctrl+p++ | Toggle fullscreen (switches from docked)                                                                        |
| ++ctrl+o++ | Toggle docked (switches from fullscreen)                                                                        |
| ++tab++    | Cycle sessions in scope (linear in task scope); opens session quick-pick when only one target is available |
| ++ctrl+k++ | Open session quick-pick palette                                                                                 |

### Input

| Key                          | Action                                                |
| ---------------------------- | ----------------------------------------------------- |
| ++enter++                    | Send message                                          |
| ++shift+enter++ / ++ctrl+j++ | New line                                              |
| ++up++                       | Recall the last submitted prompt when input is empty  |
| ++ctrl+c++                   | Clear chat input                                      |
| `/help`                      | Show commands                                         |
| `/clear`                     | Clear conversation                                    |
| `/clear all sessions`        | Clear all local chat sessions and reset target focus  |
| `/new session`               | Create and switch to a new orchestrator session       |
| `/close session`             | Close the active orchestrator session                 |
| `/export`                    | Copy active session transcript to clipboard           |
| `/compact`                   | Compact context (native preferred, snapshot fallback) |
| `/mode`                      | List agent modes                                      |
| `/mode <id>`                 | Switch AI Assistant mode                              |
| `/sessions`                  | Open session quick-pick palette                       |
| `/agent`                     | List grouped agent commands                           |
| `/agent <command> [args]`    | Run a grouped agent command                           |
| `/restart [extra context]`   | Restart active AUTO runtime task (optional injected context) |
| `/stop`                      | Stop active AUTO runtime task                                 |

### Slash complete

| Key               | Action                              |
| ----------------- | ----------------------------------- |
| Typing after `/`  | Filter list by command/alias prefix |
| ++up++ / ++down++ | Navigate list                       |
| ++enter++         | Select command                      |
| ++esc++           | Dismiss list                        |

### Session quick-pick

| Key                            | Action                                                       |
| ------------------------------ | ------------------------------------------------------------ |
| ++tab++                        | Cycle focus: filter → sessions → agents → filter            |
| ++up++ / ++down++              | Move selection in focused list                              |
| ++left++ / ++right++           | Move focus between sessions and agents lists                |
| ++ctrl+f++                     | Return focus to filter input                                |
| ++enter++                      | Select highlighted agent session                            |
| ++esc++ (with active filter)   | Clear filter and keep quick-pick open                       |
| ++esc++ (with empty filter)    | Close quick-pick                                             |

When switching sessions, unsent input is cleared by design to avoid cross-session draft confusion.

### Stream output

| UI Element          | Behavior                                                               |
| ------------------- | ---------------------------------------------------------------------- |
| Current Action rail | Shows what the agent is doing now, with confidence labels              |
| Jump to Live        | Appears when new output arrives while you are reading older scrollback |
| Run Summary card    | Posted on completion/failure with outcome, status, and next-step hint  |

### Plan approval

| Key                            | Action         |
| ------------------------------ | -------------- |
| ++up++/++down++ or ++j++/++k++ | Move selection |
| ++enter++                      | Preview task   |
| ++a++                          | Approve        |
| ++e++                          | Edit           |
| ++d++ / ++esc++                | Dismiss        |

## Welcome and onboarding

### Welcome screen

| Key                     | Action                                                |
| ----------------------- | ----------------------------------------------------- |
| ++enter++               | Open selected project                                 |
| ++n++                   | New project                                           |
| ++o++                   | Open folder                                           |
| ++s++                   | Settings                                              |
| ++ctrl+p++ / ++ctrl+o++ | After opening a board: fullscreen/docked AI Assistant |
| ++1++ to ++9++          | Open project by number                                |
| ++esc++                 | Back (from board) / Quit                              |

### Onboarding

| Key                     | Action                            |
| ----------------------- | --------------------------------- |
| ++tab++ / ++shift+tab++ | Move focus between setup controls |
| ++enter++ / ++ctrl+s++  | Save setup and continue           |
| ++esc++                 | Quit                              |

## Repo picker

| Key                            | Action         |
| ------------------------------ | -------------- |
| ++up++/++down++ or ++j++/++k++ | Navigate repos |
| ++enter++                      | Select repo    |
| ++n++                          | Add repo       |
| ++esc++                        | Cancel         |

## Modals

### Help

| Key                      | Action                               |
| ------------------------ | ------------------------------------ |
| ++ctrl+f++               | Focus help search                    |
| ++esc++ (with query)     | Clear search query                   |
| ++esc++ / ++q++ (no query) | Close                                |

### Confirm

| Key       | Action  |
| --------- | ------- |
| ++enter++ | Confirm |
| ++y++     | Yes     |
| ++n++     | No      |
| ++esc++   | Cancel  |

### Task details

| Key                    | Action             |
| ---------------------- | ------------------ |
| ++e++                  | Toggle edit        |
| ++d++                  | Delete             |
| ++f++                  | Expand description |
| ++f5++                 | Full editor        |
| ++ctrl+s++ / ++alt+s++ | Save (edit mode)   |
| ++y++                  | Copy               |
| ++esc++                | Close/Cancel       |

### Task editor

| Key                    | Action         |
| ---------------------- | -------------- |
| ++ctrl+s++ / ++alt+s++ | Finish editing |
| ++esc++                | Cancel         |

### Description editor

| Key                    | Action |
| ---------------------- | ------ |
| ++ctrl+s++ / ++alt+s++ | Save   |
| ++esc++                | Cancel |

### Settings

| Key                    | Action                            |
| ---------------------- | --------------------------------- |
| ++ctrl+s++ / ++alt+s++ | Save                              |
| ++ctrl+f++ / ++/++     | Focus settings search             |
| ++esc++                | Cancel                            |

### Duplicate task

| Key       | Action |
| --------- | ------ |
| ++enter++ | Create |
| ++esc++   | Cancel |

### Diff

| Key       | Action  |
| --------- | ------- |
| ++enter++ | Approve |
| ++r++     | Reject  |
| ++y++     | Copy    |
| ++esc++   | Close   |

### Task Output screen

| Key        | Action                                           |
| ---------- | ------------------------------------------------ |
| ++tab++    | Next scoped chat target (worker/reviewer)        |
| ++ctrl+p++ | Toggle fullscreen task overlay                   |
| ++ctrl+o++ | Toggle docked task overlay                       |
| ++a++      | Start AUTO agent (`IN_PROGRESS` AUTO tasks only) |
| ++s++      | Stop AUTO agent (`IN_PROGRESS` AUTO tasks only)  |
| ++esc++    | Close                                            |

### Rejection input

| Key       | Action              |
| --------- | ------------------- |
| ++enter++ | Back to In Progress |
| ++esc++   | Backlog             |

### Agent and review chat input

| Key                          | Action       |
| ---------------------------- | ------------ |
| ++enter++                    | Send message |
| ++shift+enter++ / ++ctrl+j++ | New line     |

### Debug log

| Key     | Action     |
| ------- | ---------- |
| ++c++   | Clear logs |
| ++s++   | Save logs  |
| ++esc++ | Close      |

### Tmux gateway

| Key       | Action           |
| --------- | ---------------- |
| ++enter++ | Continue         |
| ++esc++   | Cancel           |
| ++s++     | Don't show again |

### Base branch

| Key       | Action |
| --------- | ------ |
| ++enter++ | Submit |
| ++esc++   | Cancel |

### Permission prompt

| Key                     | Action       |
| ----------------------- | ------------ |
| ++y++ / ++enter++       | Allow once   |
| ++a++                   | Allow always |
| ++n++ / ++d++ / ++esc++ | Deny         |

### No dedicated hotkeys

| Modal         | Notes                        |
| ------------- | ---------------------------- |
| Merge Dialog  | Use buttons and checkboxes   |
| New Project   | Use inputs and buttons       |
| Folder Picker | Use input, tree, and buttons |
