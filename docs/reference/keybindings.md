---
title: Keyboard Shortcuts
description: Keybindings for the Kagan TUI
icon: material/keyboard
---

# Keyboard Shortcuts

Press `?` any time to open context-aware help for the current screen.

## Global

| Key                       | Action                   |
| ------------------------- | ------------------------ |
| ++question++ / ++f1++     | Open help                |
| ++ctrl+shift+p++ / ++f2++ | Quick Actions            |
| ++ctrl+o++                | Open project selector    |
| ++ctrl+r++                | Open repository selector |
| ++ctrl+comma++            | Open settings            |
| ++ctrl+q++                | Quit                     |
| ++ctrl+space++            | Orchestrator (toggle)    |
| ++ctrl+w++                | Toggle Chat / Board      |

## Web Dashboard

These shortcuts apply in the web dashboard (`kagan web`). All Cmd/Ctrl bindings accept either modifier — `Cmd` on macOS, `Ctrl` elsewhere.

| Key                                | Action                                          |
| ---------------------------------- | ----------------------------------------------- |
| ++cmd+shift+w++ / ++ctrl+shift+w++ | Toggle Board / Workspace view                   |
| ++cmd+shift+p++ / ++ctrl+shift+p++ | Open Quick Actions                              |
| ++cmd+period++ / ++ctrl+period++   | Toggle Sessions overlay on Board / Task routes  |
| ++cmd+shift+f++ / ++ctrl+shift+f++ | Toggle AI panel fullscreen off-workspace        |
| ++cmd+up++ / ++ctrl+up++           | Cycle attached agent stream — previous          |
| ++cmd+down++ / ++ctrl+down++       | Cycle attached agent stream — next              |
| ++cmd+k++ / ++ctrl+k++             | Open session switcher                           |
| ++question++ / ++f1++              | Open help overlay                               |
| ++escape++                         | Close AI panel off-workspace or dismiss overlay |

The cycle keys walk `[Orchestrator, ...running workers/reviewers]` and match by session id, so a stream stays selected even if its position in the list shifts. The help overlay lists the two `Esc` behaviors separately — "Detach to orchestrator" while attached, and "Stop & edit last message" while the chat input is streaming.

## Kanban Board

| Key                              | Action                    |
| -------------------------------- | ------------------------- |
| ++n++                            | New task                  |
| ++enter++                        | Open task                 |
| ++w++                            | Switch to Workspace       |
| ++a++                            | Attach interactive run    |
| ++p++                            | Peek task                 |
| ++e++                            | Edit task                 |
| ++x++                            | Delete task               |
| ++y++                            | Copy task ID              |
| ++s++                            | Start agent               |
| ++shift+s++                      | Stop or detach active run |
| ++shift+left++ / ++shift+right++ | Move task left/right      |
| ++slash++                        | Search                    |
| ++f++                            | Expand description        |
| ++ctrl+f++                       | Expand AI / sessions dock |
| ++ctrl+period++                  | Sessions overlay          |
| ++ctrl+k++                       | Session Switcher          |
| ++esc++                          | Close SessionOverlay      |
| ++b++                            | Set branch                |

`Enter` is two-step on the TUI board: first press opens the inspector for the selected card; press `Enter` again to open the full task screen.

Press `Ctrl+.` to toggle the **Sessions** overlay from the board, task screen, or session dashboard (the same unified chat surface as global `Ctrl+Space` / **Orchestrator**). Use `Ctrl+F` for **AI expand** from Kanban or the task screen, and `Ctrl+Shift+F` inside the overlay for AI fullscreen.

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

| Key             | Action           |
| --------------- | ---------------- |
| ++1++ / ++2++   | Switch tabs      |
| ++enter++       | Primary action   |
| ++ctrl+period++ | Sessions overlay |
| ++ctrl+f++      | AI expand        |
| ++ctrl+k++      | Session switcher |
| ++e++           | Edit task        |
| ++d++           | Delete task      |
| ++a++           | Approve          |
| ++x++           | Reject           |
| ++m++           | Merge            |
| ++b++           | Rebase           |
| ++esc++         | Back             |

AI review is Quick Actions first (`Ctrl+Shift+P` -> `review.ai`).

## Session Dashboard

| Key             | Action           |
| --------------- | ---------------- |
| ++enter++       | Start/focus      |
| ++s++           | Start agent      |
| ++x++           | Stop agent       |
| ++r++           | Restart agent    |
| ++ctrl+period++ | Sessions overlay |
| ++ctrl+k++      | Session Switcher |
| ++esc++         | Back             |

The Session Dashboard does not own a fullscreen chat binding; use `Ctrl+F` from the Kanban board or the SessionOverlay to fullscreen the chat surface.

## SessionOverlay

Open or close from Kanban, Session Dashboard, or Task screen with ++ctrl+period++ (**Sessions** in footer hints). Toggle globally with ++ctrl+space++ (**Orchestrator**); when the overlay is focused, the same chord closes it (along with ++esc++). The overlay selects the project orchestrator session by default and can switch across orchestrator, task, and general sessions from the session list.

| Key            | Action                             |
| -------------- | ---------------------------------- |
| ++ctrl+up++    | Cycle selected session — previous  |
| ++ctrl+down++  | Cycle selected session — next      |
| ++down++       | Move focus from chat input to list |
| ++enter++      | Open highlighted session           |
| ++esc++        | Unwind input/list focus or close   |
| ++ctrl+space++ | Close overlay (same as Esc)        |

Cycle order is matched by stable session ID rather than list position. The footer is mode-aware: keys that the parent screen would handle (for example `Ctrl+.`) are dropped from the hint while the overlay is active so only keys that fire inside the overlay are advertised.

| Key             | Action            |
| --------------- | ----------------- |
| ++enter++       | Send message      |
| ++shift+enter++ | Insert newline    |
| ++tab++         | Accept completion |
| ++ctrl+c++      | Clear input       |
| ++esc++         | Stop agent        |
| ++ctrl+k++      | Session Switcher  |

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
