---
title: Keyboard Shortcuts
description: Every keybinding available in the TUI
icon: material/keyboard
---

# Keyboard Shortcuts

Mirrors the in-app help (press ++question++).

## Essential

| Key          | Action             |
| ------------ | ------------------ |
| ++n++        | New task           |
| ++enter++    | Open / confirm     |
| ++a++        | Start agent (AUTO) |
| ++s++        | Stop agent         |
| ++question++ | Help               |
| ++period++   | Actions palette    |
| ++comma++    | Settings           |
| ++ctrl+q++   | Quit               |

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

| Key         | Action                                                                                                                                     |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| ++n++       | New task                                                                                                                                   |
| ++shift+n++ | New AUTO task                                                                                                                              |
| ++enter++   | Open focused task session (AUTO Task Output session / PAIR backend / REVIEW output). Repeated presses are ignored while the session opens. |
| ++slash++   | Search tasks                                                                                                                               |
| ++v++       | View details                                                                                                                               |
| ++e++       | Edit task                                                                                                                                  |
| ++x++       | Delete task                                                                                                                                |
| ++y++       | Duplicate task                                                                                                                             |
| ++c++       | Copy task ID                                                                                                                               |
| ++space++   | Peek overlay                                                                                                                               |
| ++f++       | Expand description                                                                                                                         |
| ++f5++      | Full editor                                                                                                                                |

### Workflow and agents

| Key         | Action                         |
| ----------- | ------------------------------ |
| ++shift+h++ | Move task left                 |
| ++shift+l++ | Move task right                |
| ++a++       | Start agent (AUTO)             |
| ++s++       | Stop agent (AUTO)              |
| ++shift+d++ | View diff (REVIEW)             |
| ++r++       | Open review stream (REVIEW)    |
| ++m++       | Merge (REVIEW)                 |
| ++ctrl+p++  | Toggle fullscreen orchestrator |
| ++ctrl+o++  | Toggle docked orchestrator     |
| ++b++       | Set task branch                |
| ++shift+g++ | Repo Sync                      |
| ++comma++   | Settings                       |

## Orchestrator overlay

The empty-state intro can occasionally show a random Kagan quote (funny or wise).
Startup behavior: if at least one task exists on the board, Kagan opens board-first with the
overlay closed. On empty boards, the fullscreen intro opens automatically.

### Screen

| Key        | Action                                        |
| ---------- | --------------------------------------------- |
| ++esc++    | Close overlay                                 |
| ++ctrl+p++ | Toggle fullscreen (switches from docked)      |
| ++ctrl+o++ | Toggle docked (switches from fullscreen)      |
| ++tab++    | Switch chat target (orchestrator/AUTO/REVIEW) |

### Input

| Key                          | Action                                                      |
| ---------------------------- | ----------------------------------------------------------- |
| ++enter++                    | Send message                                                |
| ++shift+enter++ / ++ctrl+j++ | New line                                                    |
| ++ctrl+c++                   | Clear chat input                                            |
| ++ctrl+c++, ++ctrl+c++       | Interrupt active stream (only when running in this session) |
| `/help`                      | Show commands                                               |
| `/clear`                     | Clear conversation                                          |
| `/clear all sessions`        | Clear all local chat sessions and reset target focus        |
| `/new session`               | Start a fresh local chat session                            |
| `/compact`                   | Compact context (native preferred, snapshot fallback)       |
| `/mode`                      | List agent modes                                            |
| `/mode <id>`                 | Switch orchestrator mode                                    |
| `/browse`                    | List available chat sessions/targets                        |
| \`/attach \<task-id          | kind                                                        |
| `/targets`                   | List available chat targets                                 |
| `/restart [extra context]`   | Restart active AUTO run (optional injected context)         |
| `/stop`                      | Stop active AUTO run                                        |

### Slash complete

| Key               | Action         |
| ----------------- | -------------- |
| ++up++ / ++down++ | Navigate list  |
| ++enter++         | Select command |
| ++esc++           | Dismiss list   |

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

| Key            | Action                 |
| -------------- | ---------------------- |
| ++enter++      | Open selected project  |
| ++n++          | New project            |
| ++o++          | Open folder            |
| ++s++          | Settings               |
| ++1++ to ++9++ | Open project by number |
| ++esc++        | Quit                   |

### Onboarding

| Key     | Action |
| ------- | ------ |
| ++esc++ | Quit   |

## Repo picker

| Key                            | Action         |
| ------------------------------ | -------------- |
| ++up++/++down++ or ++j++/++k++ | Navigate repos |
| ++enter++                      | Select repo    |
| ++n++                          | Add repo       |
| ++esc++                        | Cancel         |

## Modals

### Help

| Key             | Action |
| --------------- | ------ |
| ++esc++ / ++q++ | Close  |

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

| Key                    | Action |
| ---------------------- | ------ |
| ++ctrl+s++ / ++alt+s++ | Save   |
| ++esc++                | Cancel |

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

### Task Output (AUTO live screen)

| Key        | Action                         |
| ---------- | ------------------------------ |
| ++tab++    | Next chat session target       |
| ++ctrl+p++ | Toggle fullscreen task overlay |
| ++ctrl+o++ | Toggle docked task overlay     |
| ++a++      | Start AUTO agent               |
| ++s++      | Stop AUTO agent                |
| ++esc++    | Close                          |

### Task Output (REVIEW modal)

| Key        | Action                                                        |
| ---------- | ------------------------------------------------------------- |
| ++tab++    | Next session                                                  |
| ++ctrl+p++ | Cycle view (`split -> terminal fullscreen -> split -> board`) |
| ++enter++  | Approve                                                       |
| ++r++      | Reject                                                        |
| ++R++      | Rebase                                                        |
| ++g++      | Run review                                                    |
| ++a++      | Start AUTO agent                                              |
| ++s++      | Stop AUTO agent                                               |
| ++y++      | Copy                                                          |
| ++esc++    | Close/Cancel                                                  |

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
