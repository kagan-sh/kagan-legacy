# Unified Sessions Refactor Plan

## Goal

Replace fragmented chat, attach, watch, right-rail, running-agent, and task-chat
concepts with one product and code concept:

> Sessions

The global session surface must support three first-class session types:

- `orchestrator` - Kagan-aware planning/coordinating chat with Kagan prompts and
  tools.
- `task` - worker/reviewer task execution sessions with task/worktree context.
- `general` - raw backend chat proxy with no Kagan prompts, no MCP tools, and a
  visible user disclaimer that it is a general backend session.

The new UX is one global `SessionOverlay` where users can navigate all live and
recent sessions, switch instantly, replay completed sessions, and stop or close
sessions when supported.

## Non-Goals

- Do not preserve old task-owned chat panels.
- Do not preserve `/watch` as a first-class mode.
- Do not preserve fake "send to worker" semantics that only append replay
  annotations.
- Do not keep backwards-compatible aliases unless a wave explicitly proves a
  short temporary adapter is needed for another in-flight wave. Any temporary
  adapter must be deleted in Wave 4 before the final integration commit.

## Canonical Model

Public/API/UI names use `Session`, not `AgentSession`.

```ts
type SessionType = "orchestrator" | "task" | "general";
type TaskRole = "worker" | "reviewer";

type SessionStatus =
  | "idle"
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

type SessionCapabilities = {
  can_chat: boolean;
  can_stream: boolean;
  can_replay: boolean;
  can_stop: boolean;
  can_close: boolean;
  has_kagan_tools: boolean;
};

type SessionItem = {
  id: string;
  type: SessionType;
  role?: TaskRole;
  status: SessionStatus;
  title: string;
  backend?: string;
  project_id?: string;
  task_id?: string;
  session_id?: string;
  chat_session_id?: string;
  updated_at: string;
  capabilities: SessionCapabilities;
};
```

Sorting:

1. `running` / `pending`
1. blocked or approval-needed states if added later
1. `idle`
1. terminal states: `completed`, `failed`, `cancelled`
1. newest `updated_at` first within each group

## Routes

Canonical routes:

```http
GET  /api/v1/sessions
POST /api/v1/sessions
GET  /api/v1/sessions/:id/replay
POST /api/v1/sessions/:id/message
POST /api/v1/sessions/:id/stop
POST /api/v1/sessions/:id/close
```

Creation:

```ts
type CreateSessionRequest =
  | { type: "orchestrator"; backend?: string; title?: string }
  | { type: "general"; backend: string; title?: string };
```

Task sessions are created only by task execution and review flows.

## General Session Rules

General sessions are raw backend chats:

- no Kagan orchestrator prompt
- no task prompt
- no review prompt
- no MCP tools
- no project/task context unless a future explicit feature adds it
- no hidden Kagan behavior
- visible disclaimer in UI and replay:

```text
General session: this chat talks directly to the selected backend without
Kagan project tools, task context, or orchestration prompts.
```

Tests must assert that general sessions do not resolve or inject Kagan prompts
and do not attach Kagan MCP tools.

## Delegation Plan

### Wave 0: Contract Lock

Single lead agent.

Owns:

- `plan.md`
- `docs/internal/architecture/sessions.md`
- `docs/internal/features/sessions.md`

Work:

- Define the `SessionItem` contract.
- Define session type semantics.
- Define route names and capability rules.
- Define breaking-change policy.
- Add an explicit deletion ledger for legacy code.

TDD:

- Draft test names and acceptance criteria in docs before implementation.

Commit:

- `docs: define unified sessions architecture`

### Wave 1: Backend Foundation

#### Agent A: Core Session Read Model

Owns:

- `src/kagan/core/_sessions_query.py` or new
  `src/kagan/core/_session_items.py`
- `src/kagan/core/client.py`
- `tests/core/test_session_items.py`

Work:

- Add `SessionItem` read model.
- Flatten:
  - `ChatSession(type="orchestrator")`
  - `ChatSession(type="general")`
  - worker/reviewer `Session` rows as `type="task"`
- Compute stable ids.
- Compute real `updated_at` and `last_event_at`.
- Compute capabilities.
- Sort active first and terminal sessions below.

TDD first:

- `test_session_items_include_orchestrator_task_and_general_sessions`
- `test_session_items_sort_active_before_terminal_and_newest_first`
- `test_session_items_have_stable_kind_scoped_ids`
- `test_session_items_capabilities_match_session_type`
- `test_session_items_project_filter_excludes_other_projects`

Commit:

- `refactor(core): add unified session items`

#### Agent B: General Sessions

Owns:

- `src/kagan/core/models.py`
- `src/kagan/core/chat/`
- `src/kagan/cli/chat/acp.py`
- migration files
- focused core tests

Work:

- Add `ChatSession.session_type`.
- Migrate existing chat sessions to `orchestrator`.
- Add general session creation.
- Add raw backend turn execution for general sessions.
- Persist the visible general-session disclaimer as metadata or an info event.
- Ensure general sessions do not call Kagan prompt resolution or MCP setup.

TDD first:

- `test_general_session_uses_raw_backend_without_kagan_prompt`
- `test_general_session_does_not_attach_kagan_tools`
- `test_general_session_records_visible_disclaimer`
- `test_existing_chat_sessions_migrate_to_orchestrator_type`

Commit:

- `feat(core): add general sessions`

#### Agent C: Server Sessions API

Owns:

- new `src/kagan/server/_session_routes.py` or equivalent
- `src/kagan/server/responses.py`
- `scripts/generate_wire_types.py` output
- `packages/shared/api-client/src/wire.ts`
- server tests

Work:

- Add canonical session routes.
- Add `SessionItemResponse`, `SessionsResponse`, replay/message/action
  response models.
- Enforce bound project access.
- Add action capability validation.
- Generate TypeScript wire types.

TDD first:

- `tests/server/test_sessions_route.py`
- `tests/server/test_session_replay_route.py`
- `tests/server/test_session_actions_route.py`

Commit:

- `feat(server): expose unified sessions api`

### Wave 2: Client Migration

#### Agent D: Web Session State

Owns:

- `packages/web/src/lib/atoms/ui.ts`
- `packages/web/src/lib/api/client.ts`
- `packages/web/src/lib/hooks/`
- web atom/hook tests

Work:

- Replace split right-rail state with:
  - `selectedSessionAtom`
  - `sessionOverlayLayoutAtom`
  - `sessionListAtom`
- Add typed session API helpers.
- Add stable cycle by `SessionItem.id`, not list index.
- Remove ghost `/session/:id` route matching logic.

TDD first:

- selected session atom tests
- session list sorting tests
- cycle survives polling churn by id
- close/dismiss clears only the selected session

Commit:

- `refactor(web): unify session selection state`

#### Agent E: Web SessionOverlay

Owns:

- `packages/web/src/components/session/`
- `packages/web/src/components/layout/app-layout.tsx`
- `packages/web/src/pages/task-detail-page.tsx`
- `packages/web/src/pages/chat-page.tsx`
- web component/e2e tests

Work:

- Build `SessionOverlay`.
- Add bodies:
  - `OrchestratorSessionBody`
  - `TaskSessionBody`
  - `GeneralSessionBody`
- Merge reusable primitives:
  - `ChatView`
  - `EventStream`
  - `PermissionDialog`
- Task pages focus the global overlay; they do not render task-owned chat.
- `/chat/:id` becomes a thin route adapter or is removed if accepted as
  breaking.

TDD first:

- overlay renders all three session types
- only one overlay shell exists in `AppLayout`
- task page opens/focuses global overlay
- general session shows disclaimer
- task session body cannot send fake live messages

Commit:

- `refactor(web): replace chat side panel with session overlay`

#### Agent F: TUI SessionOverlay

Owns:

- `src/kagan/tui/screens/orchestrator_overlay.py`
- `src/kagan/tui/widgets/running_agents_bar.py`
- `src/kagan/tui/screens/kanban.py`
- `src/kagan/tui/screens/session_dashboard.py`
- TUI tests

Work:

- Rename/replace `RunningAgentsBar` with `SessionList`.
- Show orchestrator, task, and general sessions together.
- Add general session creation/opening if TUI supports new sessions.
- Remove embedded task chat remnants.
- Make keyboard behavior session-first:
  - arrows or `j/k` navigate
  - `Enter` selects
  - `s` stops when supported
  - `x` closes when supported
  - `Esc` unwinds input -> list -> close

TDD first:

- overlay lists orchestrator/task/general as peers
- completed task sessions sink below running sessions
- Enter switches selected session
- stop/close actions honor capabilities
- structural guard: Kanban and SessionDashboard do not compose old chat panel

Commit:

- `refactor(tui): make overlay session-first`

### Wave 3: CLI and VS Code

#### Agent G: CLI Sessions

Owns:

- `src/kagan/cli/chat/controller.py`
- `src/kagan/cli/chat/commands.py`
- `src/kagan/cli/chat/_session_picker.py`
- `src/kagan/cli/chat/repl.py`
- CLI tests

Work:

- `/sessions` lists all session types.
- `/new general --agent <backend>`.
- `/switch <id>`.
- `/stop`.
- `/close` or `/delete` follows the final product naming from Wave 0.
- General sessions run raw backend turns.
- Remove attach/detach semantics from CLI.

TDD first:

- `/sessions` shows orchestrator/task/general
- `/new general` creates raw backend session
- `/switch` changes selected session
- `/stop` stops selected live task session or orchestrator turn
- removed `/attach` and `/detach` fail with clear guidance, or are deleted
  from command registry if breaking removal is chosen

Commit:

- `refactor(cli): replace attach flow with sessions`

#### Agent H: VS Code Sessions

Owns:

- `packages/vscode/src/providers/chat.participant.ts`
- `packages/vscode/src/providers/running-agents.tree.ts`
- VS Code API/client files
- VS Code tests

Work:

- Rename Running Agents tree to Sessions.
- Use one selected `SessionItem`.
- Remove task watch mode.
- Add commands:
  - switch session
  - stop session
  - close session
  - new general session
- Collapse:
  - `activeChatSessionId`
  - `watchingTaskId`
  - `attachedSessionId`

TDD first:

- tree renders orchestrator/task/general rows
- switching uses `SessionItem.id`
- `/watch` is removed
- stop/close commands use capabilities

Commit:

- `refactor(vscode): switch to unified sessions`

### Wave 4: Complete Legacy Removal

This wave is mandatory. It deletes both existing legacy code and code made
obsolete by the new sessions model. No compatibility adapters should remain
after this wave.

#### Agent I: Backend Legacy Deletion

Owns:

- core/server old attach/running-agent surfaces
- migrations if needed
- backend deletion tests

Delete:

- `/api/v1/agents/running`
- `ActiveAgentRow`
- `ActiveAgentRowResponse`
- `RunningAgentsResponse`
- `list_running_agents`
- `send_message_to_session`
- replay-only attached message compatibility wrapper
- `ChatSession.attached_session_id` if all clients use explicit selection
- `attach_chat`
- `attach_chat_to_session`
- `record_session_user_message_for_replay` if it only served fake live sends
- `task-session` pseudo-session fallback
- any route comments or docs for deleted endpoints

TDD first:

- structural tests prove deleted names are not importable or exposed
- route tests prove old endpoints return 404 if the product accepts breaking
  removal
- migration tests cover removed columns

Commit:

- `refactor(core): remove legacy attach and running-agent APIs`

#### Agent J: Web Legacy Deletion

Owns:

- web dead components/routes/tests

Delete:

- `ChatSidePanel`
- lane-based `worker|reviewer` URL handling
- `rightRailTaskIdAtom`
- `rightRailChatSessionIdAtom`
- old `RightRailMode` names if replaced by overlay layout
- duplicated `/chat/:id` UI if route adapter is enough
- `/home` redirect if accepted as breaking
- `/analytics` redirect if accepted as breaking
- stale `/session/:id` command matching
- unused workspace sidebar duplication
- tests that only validate old rail behavior

TDD first:

- no duplicate overlay rendering
- no imports from deleted components
- command palette no longer references deleted routes

Commit:

- `refactor(web): delete legacy chat rail code`

#### Agent K: TUI Legacy Deletion

Owns:

- old TUI chat surfaces and keybindings

Delete:

- embedded Kanban `ChatPanel`
- Kanban chat mode state and handlers
- SessionDashboard embedded chat modes
- synthetic task chat keys
- `send_task_message`
- old AI Panel keybindings that compete with the global SessionOverlay
- tests that assert embedded chat behavior

TDD first:

- structural guard no old `ChatPanel` composition in Kanban/SessionDashboard
- keybinding tests assert only the session overlay entry points remain

Commit:

- `refactor(tui): delete embedded chat legacy`

#### Agent L: CLI and VS Code Legacy Deletion

Owns:

- old CLI/VS Code attach/watch code

Delete:

- CLI `/attach`
- CLI `/detach`
- CLI attached-agent fields
- VS Code `/watch`
- VS Code `watchingTaskId`
- VS Code `attachedSessionId`
- UUID-only attach parser
- task-session pseudo-session filters
- deprecated `Wire*` aliases once consumers are migrated

TDD first:

- command registries do not list removed commands
- help output uses only sessions vocabulary
- no tests import removed helpers

Commit:

- `refactor(clients): delete attach and watch legacy`

#### Agent M: Docs Legacy Deletion

Owns:

- docs only

Delete or archive:

- old AI Panel language
- ChatSidePanel language
- Running Agents as a primary product concept
- `/watch`
- attach/detach docs
- `task-preview-review.md` if obsolete
- duplicate `cli-chat.md` if merged into `chat.md`
- stale AGENTS.md paths and package references
- stale root config compatibility notes if breaking removal is accepted

Update:

- public chat guide
- web dashboard guide
- VS Code guide
- keybindings reference
- CLI reference
- MCP/server references
- internal architecture docs
- internal features docs
- testing guide

Commit:

- `docs: remove legacy chat and attach model`

## Legacy Removal Ledger

Every item below must be either deleted or explicitly marked "kept" with a
reason before final integration. Default is delete.

### Backend/Core

- [ ] `/api/v1/agents/running`
- [ ] `ActiveAgentRow`
- [ ] `ActiveAgentRowResponse`
- [ ] `RunningAgentsResponse`
- [ ] `list_running_agents`
- [ ] `send_message_to_session`
- [ ] replay-only attached message wrapper
- [ ] `attach_chat`
- [ ] `attach_chat_to_session`
- [ ] `ChatSession.attached_session_id`
- [ ] `record_session_user_message_for_replay`
- [ ] `task-session` pseudo-session fallback
- [ ] stale SSE/running-agent route comments

### Web

- [ ] `ChatSidePanel`
- [ ] `rightRailTaskIdAtom`
- [ ] `rightRailChatSessionIdAtom`
- [ ] old `RightRailMode` naming
- [ ] lane-based `worker|reviewer` URL handling
- [ ] duplicated `/chat/:id` chat UI
- [ ] `/session/:id` ghost command handling
- [ ] `/home` redirect
- [ ] `/analytics` redirect
- [ ] workspace sidebar duplication
- [ ] tests that only cover old right-rail behavior

### TUI

- [ ] embedded Kanban `ChatPanel`
- [ ] Kanban chat mode state
- [ ] SessionDashboard embedded chat modes
- [ ] synthetic task chat keys
- [ ] `send_task_message`
- [ ] old AI Panel keybindings
- [ ] tests asserting embedded task chat

### CLI

- [ ] `/attach`
- [ ] `/detach`
- [ ] attached-agent controller fields
- [ ] replay-only send-to-attached-session flow
- [ ] help text mentioning attach/detach

### VS Code

- [ ] `/watch`
- [ ] `watchingTaskId`
- [ ] `attachedSessionId`
- [ ] UUID-only attach parser
- [ ] `RunningAgentsTreeProvider` name/product framing
- [ ] task-session filters

### Shared Types

- [ ] deprecated `Wire*` aliases that exist only for old generated type names
- [ ] generated running-agent response types
- [ ] API client helpers for removed endpoints

### Docs

- [ ] AI Panel as separate product concept
- [ ] ChatSidePanel as product concept
- [ ] Running Agents as primary product concept
- [ ] `/watch` docs
- [ ] attach/detach docs
- [ ] old task chat docs
- [ ] duplicate `cli-chat.md`
- [ ] obsolete `task-preview-review.md`
- [ ] stale AGENTS.md paths/package references

## Final Integration

Single lead agent.

Run:

```bash
uv run poe check-guardrails
uv run poe lint
uv run poe typecheck
uv run poe docs-check
uv run pytest tests/core/test_session_items.py tests/server/test_sessions_route.py tests/server/test_session_replay_route.py -q
cd packages/web && pnpm test && pnpm run build
cd packages/vscode && pnpm run check-types && pnpm run test:unit
```

Search for removed vocabulary:

```bash
rg -n "ChatSidePanel|RunningAgents|/watch|attached_session_id|send_message_to_session|AI Panel|rightRailTaskIdAtom|rightRailChatSessionIdAtom|ActiveAgentRow"
```

Acceptance criteria:

- One canonical `Sessions` API.
- One global `SessionOverlay`.
- Three session types: `orchestrator`, `task`, `general`.
- General sessions are raw backend chats with visible disclaimer and no Kagan
  tools/prompts.
- No task-owned chat panel remains.
- No attach/watch compatibility code remains.
- No running-agent-specific API remains as a primary or compatibility surface.
- Docs and tests use the new sessions vocabulary only.
- Worktree is clean.

Commit:

- `test: verify unified sessions integration`
