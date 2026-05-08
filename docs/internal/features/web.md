# Web Features

Observable behaviors of the React web client.

______________________________________________________________________

## 1. Boot & Onboarding

- the shipped web app runs in bundled mode against the same-origin Kagan server
- onboarding state is local to the browser and does not require a separate pairing route
- startup verifies same-origin server health before entering the board workspace
- `/welcome` hosts the onboarding/project setup page; first-run users land here before the board
- `first-boot-tutorial-dialog.tsx` surfaces an in-board tutorial overlay on first launch

______________________________________________________________________

## 2. IDE-Style App Shell

- persistent activity bar, contextual header, and desktop utility rail
- global Quick Actions (`Cmd/Ctrl+Shift+P`) with route-aware task actions and workspace navigation
- mobile uses bottom tabs instead of the desktop shell rails

______________________________________________________________________

## 3. Board Workspace

- four-lane kanban board: `BACKLOG`, `IN_PROGRESS`, `REVIEW`, `DONE`
- search plus structured status/mode filters
- advisory WIP warnings from resolved workflow settings
- richer task cards with review state, acceptance-criteria count, last activity, workspace state, and live session telemetry
- task cards can show lightweight watcher counts from live client presence when another web or editor client is actively focused on that task
- desktop right rail supports task inspection and related chat preview
- the header repo selector auto-selects an available repo and opens Add Repository when an active project has none
- `Cmd/Ctrl+Shift+W` toggles to the conversation-first workspace view

______________________________________________________________________

## 3a. Workspace View

- conversation-first alternative to the kanban board, accessible via `/workspace` or `Cmd/Ctrl+Shift+W`
- left sidebar lists orchestrator conversations only; task streams are not separate primary navigation in this route
- sidebar search filters across conversation labels and configured backends
- selecting a conversation opens `OrchestratorChatPanel` full-width as the main workspace surface
- first visit bootstraps a blank orchestrator session automatically if none exist
- the workspace route suppresses the global AI rail so users do not get two competing chat surfaces
- session labels and backend changes propagate back into the sidebar after turns complete or metadata changes

______________________________________________________________________

## 4. Task Workspace

- `/task/:id` adapts its default tab by task state and workspace availability
- three tabs: **Overview**, **Changes**, and **Review**
- tab auto-selection: `REVIEW` with workspace opens Review; `BACKLOG` opens Overview; workspace present opens Changes; otherwise Overview
- live streaming happens in the **ChatSidePanel** overlay (right rail), which auto-opens when a task has an active session
- the ChatSidePanel has a Worker/Reviewer lane toggle in its header, a LIVE indicator, and filters events by the active session ID
- URL deep-linking via `?lane=worker|reviewer` auto-opens the overlay with the specified lane
- "Watch stream" on the board inspector opens `/task/:id?lane=worker` (overlay auto-opens)
- sticky action bar keeps lifecycle controls and run controls visible
- summary rail surfaces metadata, runtime telemetry, workspace state, and review approval

______________________________________________________________________

## 5. ChatSidePanel Streaming Overlay

- live execution streaming surfaces in the **ChatSidePanel**, a right-rail overlay on the task detail page
- the overlay auto-opens when a task has an active session or when navigating with `?lane=worker|reviewer`
- Worker/Reviewer lane toggle in the overlay header switches streaming context
- LIVE indicator and streaming status use the shared animated wave glyph
- the overlay filters events by the active session ID
- Session picker navigates to `/task/:id?lane=...` so task overlays open directly.
- live task event updates over SSE
- AGENT_STATUS events with usage data render an inline metrics row: context window fill bar, percentage, and cost

______________________________________________________________________

## 6. Chat & Sessions

- Session Switcher (`Cmd/Ctrl+Shift+K`) provides a global session index across orchestrator and task-linked sessions
- `/chat/:id` shows orchestrator conversation history, streaming output, slash commands, and backend metadata
- task-specific quick-jump entry points link the ChatSidePanel overlay and chat surfaces together
- during streaming, the shared animated wave glyph and `esc interrupt` hint appear below the chat input; space is always reserved to prevent layout shift (shape language matches the chat REPL and TUI)
- session titles are auto-generated after the first exchange via a lightweight ACP call and pushed to the client via `CHAT_SESSION_UPDATED` SSE event

______________________________________________________________________

## 7. Settings

- categorized settings surface: `Orchestration`, `Appearance`, `Delivery Automation`, `Workspace`, `Identity & Models`, and `Additional Instructions`
- orchestration section exposes typed behavioral controls: execution mode, review strictness, planning depth, auto-confirm
- additional instructions section provides a single text field for user-specific guidance (additive, never replaces defaults)
- dotfile override status shown when `.kagan/prompts/` files are detected
- resolved workflow settings expose advisory WIP limits to both settings and board UI

______________________________________________________________________

## 8. Realtime & Accessibility

- board, task (including ChatSidePanel overlay), and chat views react to SSE updates
- visible keyboard focus, strong border contrast, skip link support, and reduced-motion respect
- typography is split between UI and code surfaces for readability in long work sessions

______________________________________________________________________

## 8a. Orchestrator Overlay

- the right-rail dock is a single mode-aware overlay
  (`components/session/orchestrator-overlay.tsx`) with three modes:
  orchestrator, worker, reviewer
- a breadcrumb header shows the active mode (`Orchestrator` /
  `Worker · running · 23s · ↑12k ↓3k`)
- `RunningAgentsBar` (`components/session/running-agents-bar.tsx`) lists
  active worker / reviewer sessions polled from `GET /api/v1/agents/running`
  and attaches the rail on click
- attach state lives in `lib/atoms/chat-attach.ts` (`chatAttachAtom` plus
  `attachChatSessionAtom` / `detachChatSessionAtom` and
  `cycleChatAttachAtom`); running-agents data lives in
  `lib/atoms/running-agents.ts`
- `Cmd/Ctrl+K` toggles the rail; `Esc` while attached detaches back to
  orchestrator mode and `Esc` from the chat input while streaming stops the
  current turn so the user can edit and resend the last message
- `Cmd/Ctrl+↑` / `Cmd/Ctrl+↓` cycle the attached stream through
  `[Orchestrator, ...running workers/reviewers]`. Cycle order matches by
  `session_id` (not list index) so the selection survives polling churn.
  Wired in `lib/hooks/use-global-shortcuts.ts` via `cycleChatAttachAtom`.
- the help overlay (`components/layout/help-overlay.tsx`) lists the two
  `Esc` behaviors as separate rows — "Detach to orchestrator" while
  attached and "Stop & edit last message" while the chat input is
  streaming — to remove the previously misleading single-row hint
- the URL query param `?chat=task:<taskId>:<sessionId>` deep-links into the
  attached state
- `ChatSidePanel` is preserved for the task-detail "Open chat" entry point but
  no longer drives the global rail

*Tests:* `packages/web/src/components/__tests__/OrchestratorOverlay.test.tsx`,
`packages/web/src/components/__tests__/RunningAgentsBar.test.tsx`,
`packages/web/src/lib/atoms/__tests__/chat-attach.test.ts`.

### Preflight gate

- `components/welcome/preflight-gate.tsx` mirrors the TUI doctor flow on
  Welcome: hard `fail` checks block the dashboard with a setup dialog,
  pure `warn` checks render a dismissible "Degraded configuration" banner
- the banner suppresses purely-optional backend warnings the same way the
  TUI does — when at least one backend is installed, missing non-default
  backends do not flip the boot state to degraded

______________________________________________________________________

## 9. Interactive Session Launch

- when launching an interactive session, a guidance dialog appears before the session launches
- dialog content adapts by launcher backend: tmux (attach command), nvim (nvim launch command), IDE (editor deep link)
- terminal backends (tmux, nvim) copy a runnable command to clipboard
- "Do not show this guidance again" toggle persists the `skip_attached_instructions_popup` setting
- task-level launcher override (`task.launcher`) takes priority over global `settings.attached_launcher`
- if a managed run is active when Attach is clicked, the dialog warns that the background agent will be stopped; on confirmation the managed run is cancelled before the interactive session starts
