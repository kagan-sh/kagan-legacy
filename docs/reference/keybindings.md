---
title: Keyboard Shortcuts
description: Keybindings for the Kagan TUI
icon: material/keyboard
---

# Keyboard Shortcuts

Press `?` any time to open context-aware help for the current screen.

## Global

| Key                   | Action                   |
| --------------------- | ------------------------ |
| ++question++ / ++f1++ | Open help                |
| ++ctrl+o++            | Open project selector    |
| ++ctrl+r++            | Open repository selector |
| ++ctrl+comma++        | Open settings            |
| ++ctrl+q++            | Quit                     |

## Web Dashboard

These shortcuts apply in the web dashboard (`kagan web`).

| Key                   | Action                                          |
| --------------------- | ----------------------------------------------- |
| ++cmd+shift+w++       | Toggle Board / Workspace view                   |
| ++cmd+shift+p++       | Open Quick Actions                              |
| ++cmd+period++        | Cycle AI panel on Board / Task routes           |
| ++cmd+shift+f++       | Toggle AI panel fullscreen off-workspace        |
| ++cmd+k++             | Open session switcher                           |
| ++question++ / ++f1++ | Open help overlay                               |
| ++escape++            | Close AI panel off-workspace or dismiss overlay |

## Kanban Board

| Key                              | Action                    |
| -------------------------------- | ------------------------- |
| ++n++                            | New task                  |
| ++enter++                        | Open task                 |
| ++w++                            | Switch to Workspace       |
| ++a++                            | Attach interactive run    |
| ++space++                        | Cycle AI split            |
| ++p++                            | Peek task                 |
| ++e++                            | Edit task                 |
| ++x++                            | Delete task               |
| ++y++                            | Copy task ID              |
| ++s++                            | Start agent               |
| ++shift+s++                      | Stop or detach active run |
| ++shift+left++ / ++shift+right++ | Move task left/right      |
| ++slash++                        | Search                    |
| ++f++                            | Expand description        |
| ++ctrl+f++                       | Fullscreen AI chat        |
| ++ctrl+period++                  | Toggle AI Panel           |
| ++ctrl+k++                       | Session Switcher          |
| ++esc++                          | Close AI Panel            |
| ++b++                            | Set branch                |

`Enter` is two-step on the TUI board: first press opens the inspector for the selected card; press `Enter` again to open the full task screen.

Press `Ctrl+.` to open/close AI Panel, `Space` to cycle split layout, and `Ctrl+F` to expand an already-open overlay fullscreen.

Rare actions like GitHub import, repo sync, and AI review are available via Quick Actions (`Ctrl+Shift+P`).

## Workspace

| Key             | Action                                                                        |
| --------------- | ----------------------------------------------------------------------------- |
| ++enter++       | Open highlighted session                                                      |
| ++n++           | Start new session                                                             |
| ++x++           | Delete highlighted session                                                    |
| ++slash++       | Focus session search                                                          |
| ++ctrl+period++ | Focus chat input                                                              |
| ++ctrl+k++      | Session Switcher                                                              |
| ++w++           | Return to Kanban                                                              |
| ++esc++         | Step back: clear search or leave chat, then return to Kanban from the sidebar |

The TUI Workspace is orchestrator-first: the left sidebar is the session list, and the main pane is the full chat surface. Focus enters on the sidebar by default so list actions stay predictable; use `Ctrl+.` to move into chat input.

## Task Screen

| Key             | Action             |
| --------------- | ------------------ |
| ++1++ / ++2++   | Switch tabs        |
| ++enter++       | Primary action     |
| ++e++           | Edit task          |
| ++d++           | Delete task        |
| ++a++           | Approve            |
| ++x++           | Reject             |
| ++m++           | Merge              |
| ++b++           | Rebase             |
| ++ctrl+f++      | Fullscreen AI chat |
| ++ctrl+period++ | Toggle AI Panel    |
| ++ctrl+k++      | Session Switcher   |
| ++esc++         | Back               |

AI review is Quick Actions first (`Ctrl+Shift+P` -> `review.ai`).

## Session Dashboard

| Key              | Action             |
| ---------------- | ------------------ |
| ++enter++        | Start/focus        |
| ++s++            | Start agent        |
| ++x++            | Stop agent         |
| ++r++            | Restart agent      |
| ++ctrl+period++  | Toggle AI Panel    |
| ++ctrl+shift+t++ | Fullscreen AI chat |
| ++ctrl+k++       | Session Switcher   |
| ++esc++          | Back               |

## AI Panel

| Key             | Action              |
| --------------- | ------------------- |
| ++enter++       | Send message        |
| ++shift+enter++ | Insert newline      |
| ++tab++         | Accept completion   |
| ++ctrl+j++      | Focus latest output |
| ++ctrl+c++      | Clear input         |
| ++esc++         | Stop agent          |
| ++ctrl+k++      | Session Switcher    |

## Welcome Screen

| Key           | Action                 |
| ------------- | ---------------------- |
| ++enter++     | Open selected project  |
| ++n++         | New project            |
| ++o++         | Open folder            |
| ++1++ - ++9++ | Quick open by position |
| ++esc++       | Quit                   |

## Quick Actions palette

Open with `Ctrl+Shift+P` from any TUI screen.

The palette surfaces rare or context-specific actions that do not have dedicated keys:

| Action          | Description                                    |
| --------------- | ---------------------------------------------- |
| `review.ai`     | Run AI review on the current REVIEW-state task |
| `github.import` | Import issues from a connected GitHub repo     |
| `repo.sync`     | Sync the active repository reference           |

Type to filter. Press `Enter` to run, `Esc` to dismiss.

## Common Modals

| Key        | Action                   |
| ---------- | ------------------------ |
| ++enter++  | Confirm / select         |
| ++esc++    | Cancel / close           |
| ++ctrl+s++ | Save in text-heavy forms |
