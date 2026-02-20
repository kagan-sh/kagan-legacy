# Kagan Architecture Draft

Based on 106 user stories across 11 epics. This document defines the domain model,
bounded contexts, Wire protocol, client architecture, and aggregate designs that
satisfy the full requirements catalog.

______________________________________________________________________

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                          Core Daemon                                │
│                        (singleton process)                          │
│                                                                     │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│   │ Project  │  │   Task   │  │ Session  │  │    Workspace      │  │
│   │ Context  │  │ Context  │  │ Context  │  │    Context        │  │
│   └──────────┘  └──────────┘  └──────────┘  └───────────────────┘  │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────────────────────┐  │
│   │ Review   │  │ Planning │  │         Plugin Registry          │  │
│   │ Context  │  │ Context  │  │  (GitHub, future integrations)   │  │
│   └──────────┘  └──────────┘  └──────────────────────────────────┘  │
│                                                                     │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │                    Event Bus                                 │  │
│   │             (Wire BroadcastQueue)                            │  │
│   │  Typed domain events → all subscribers in real time          │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└──────────┬──────────────────────┬──────────────────────┐
           │                      │
    ┌──────┴──────┐       ┌───────┴───────┐
    │     TUI     │       │     MCP       │
    │  (Textual)  │       │  (stdio /     │
    │             │       │  SSE)         │
    │  Board      │       │               │
    │  Modals     │       │  Tools        │
    │  Review     │       │  Queries      │
    │  Orchestrator│      │  Jobs         │
    │  Overlay    │       │  Sessions     │
    │  (native    │       │  Reviews      │
    │   widgets:  │       │  Settings     │
    │   Input +   │       │  GitHub       │
    │   Streaming │       │               │
    │   Output)   │       │               │
    │  FULL ADMIN │       │               │
    │  PARITY     │       │               │
    └─────────────┘       └───────────────┘
     kagan / kagan tui    kagan mcp
```

### Design Principles

1. **Singleton core, multi-client** — One daemon process owns all state.
   Multiple TUI and MCP instances connect concurrently. Real-time sync
   via Wire event broadcast. (US-005)

1. **TUI orchestrator overlay has full admin parity** — Every operation
   available via MCP tools is performable from the TUI orchestrator overlay
   via natural language or slash commands. Planning, agent I/O, task CRUD,
   reviews, settings, GitHub operations, project/repo management — all
   from native Textual widgets (Input + StreamingOutput). (US-046–071)

1. **TUI is a visual management surface** — Board, modals, review diffs.
   Read-only or form-input only. The orchestrator overlay provides
   admin/streaming capabilities via native Textual widgets. (US-018–027, US-072)

1. **Wire protocol decouples logic from rendering** — Strongly-typed events
   on a BroadcastQueue. Any client subscribes independently. Same events
   render differently per client. (US-046)

1. **Hexagonal / Ports & Adapters** — Core defines ports (interfaces).
   Agents, git, GitHub, storage are adapters. Plugins are anti-corruption
   layers that translate external domains into Kagan's ubiquitous language.

______________________________________________________________________

## 2. Bounded Context Map

```
┌─────────────────────────────────────────────────────────────────┐
│                         CORE DOMAIN                             │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ PROJECT CONTEXT  │    │  TASK CONTEXT    │                    │
│  │                 │    │                 │                    │
│  │ Project         │    │ Task (aggregate)│                    │
│  │ Repository      │    │ Scratchpad      │                    │
│  │ BranchConfig    │    │ AcceptCriteria  │                    │
│  └─────────────────┘    └─────────────────┘                    │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ SESSION CONTEXT  │    │ WORKSPACE CTX   │                    │
│  │                 │    │                 │                    │
│  │ PairSession     │    │ Worktree        │                    │
│  │ McpCredentials  │    │ AgentRuntime    │                    │
│  │ TerminalBackend │    │ Job             │                    │
│  └─────────────────┘    └─────────────────┘                    │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ REVIEW CONTEXT   │    │ PLANNING CTX    │                    │
│  │                 │    │                 │                    │
│  │ ReviewResult    │    │ Plan            │                    │
│  │ DiffSet         │    │ PlanItem        │                    │
│  │ MergeOperation  │    │ Draft           │                    │
│  └─────────────────┘    └─────────────────┘                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ EVENT BUS (Wire)                                         │   │
│  │ BroadcastQueue<DomainEvent> → subscribers                │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         △                    △                    △
         │ conformist         │ conformist         │ ACL
  ┌──────┴──────┐     ┌──────┴──────┐
  │     TUI     │     │   GitHub    │
  │   Client    │     │   Plugin    │
  └─────────────┘     └─────────────┘

Relationship types:
  conformist = client conforms to core's domain model
  ACL        = anti-corruption layer translates external domain
```

### Context Responsibilities

| Context         | Owns                                      | Key Invariants                                                                |
| --------------- | ----------------------------------------- | ----------------------------------------------------------------------------- |
| Project         | Projects, repos, branch config            | Repo path uniqueness, active repo state                                       |
| Task            | Tasks, lifecycle, scratchpad, priority    | Status transitions (BACKLOG→IP→REVIEW→DONE), DONE only via review/merge/close |
| Session         | PAIR sessions, MCP credentials, terminals | One active session per task, credential scoping                               |
| Workspace       | Worktrees, agent runtimes, jobs           | Worktree isolation, job state machine                                         |
| Review          | Diffs, review verdicts, merge ops         | Merge safety, serialize option, approval gating                               |
| Planning        | Plans, plan items, drafts                 | Draft persistence, approval before creation                                   |
| Event Bus       | Wire protocol, broadcast                  | Delivery to all subscribers, typed events                                     |
| GitHub (plugin) | Issue sync, PR ops, leases, CI            | Issue↔task mapping, lease exclusivity, status sync                            |

______________________________________________________________________

## 3. Aggregate Designs

### 3.1 Task Aggregate (central)

```
Aggregate: Task
  Identity:   TaskId (short alphanumeric, copyable)

  Invariants:
    - Status: BACKLOG → IN_PROGRESS → REVIEW → DONE
    - DONE reachable only via review_apply(merge) or close_exploratory
    - Type (AUTO | PAIR) is orthogonal to status
    - Type change triggers side effects (stop agent, kill session)
    - Branch override is optional; defaults to repo base branch

  Commands:
    CreateTask        → TaskCreated
    UpdateDetails     → TaskUpdated
    TransitionStatus  → TaskTransitioned
    ChangeType        → TaskTypeChanged
    AssignBranch      → BranchAssigned
    AppendNote        → NoteAppended
    DeleteTask        → TaskDeleted

  Entities:
    AcceptanceCriteria[]
    Scratchpad (append-only log)

  Value Objects:
    TaskType      { AUTO, PAIR }
    Priority      { LOW, MED, HIGH }
    Status        { BACKLOG, IN_PROGRESS, REVIEW, DONE }
    AgentBackend  { claude, codex, copilot, gemini, kimi, opencode }
    TerminalBackend { tmux, vscode, cursor }
    BranchOverride  (optional string)
```

### 3.2 Project Aggregate

```
Aggregate: Project
  Identity: ProjectId

  Invariants:
    - Repo paths are unique across projects
    - One active repo per runtime context per client
    - Branch config initialized from checked-out branch on first add

  Commands:
    CreateProject     → ProjectCreated
    OpenProject       → ProjectOpened
    AddRepo           → RepoAdded
    SwitchActiveRepo  → ActiveRepoSwitched  (broadcast to all clients)
    SetBranchConfig   → BranchConfigured

  Entities:
    Repository[] { path, base_branch, github_metadata? }

  Value Objects:
    RepoPath (validated absolute path)
```

### 3.3 Session Aggregate (PAIR)

```
Aggregate: PairSession
  Identity: SessionId (derived from TaskId)

  Invariants:
    - Bound to exactly one task
    - MCP credentials scoped to task
    - Backend must pass readiness check before attach
    - Session env vars injected on creation

  Commands:
    OpenSession       → SessionOpened    (task → IN_PROGRESS)
    AttachSession     → SessionAttached
    CloseSession      → SessionClosed

  Value Objects:
    TerminalBackend { tmux, vscode, cursor }
    McpCredentials  { session_id, scope }
    SessionEnvVars  { KAGAN_TASK_ID, worktree_path, ... }
```

### 3.4 Job Aggregate (AUTO)

```
Aggregate: Job
  Identity: JobId

  Invariants:
    - One active job per task
    - Workspace provisioned before agent start
    - Job emits Wire events for all output

  Commands:
    StartJob    → JobStarted    (provisions worktree, spawns agent)
    PollJob     → JobPolled     (returns current state)
    CancelJob   → JobCancelled  (stops agent, emits event)

  States:
    PENDING → RUNNING → COMPLETED | FAILED | CANCELLED

  Value Objects:
    WorktreePath
    AgentBackend
```

### 3.5 Plan Aggregate

```
Aggregate: Plan
  Identity: PlanId (per conversation session)

  Invariants:
    - Items require approval before task creation
    - Dismissed plans keep conversation context
    - Drafts persist across chat sessions

  Commands:
    GeneratePlan   → PlanGenerated
    EditPlanItem   → PlanItemEdited
    ApprovePlan    → PlanApproved      (creates tasks, refreshes board)
    DismissPlan    → PlanDismissed     (continues conversation)
    SaveDraft      → DraftSaved
    RestoreDraft   → DraftRestored

  Entities:
    PlanItem[] { title, description, AC, priority, type, backend, branch }

  Value Objects:
    DraftState { pending, approved, dismissed }
```

### 3.6 Review Aggregate

```
Aggregate: Review
  Identity: derived from TaskId

  Invariants:
    - DONE only via merge or close_exploratory
    - Merge blocked if serialize_merges and another merge in flight
    - Merge blocked if require_review_approval and not approved
    - Rebase conflicts move task to IN_PROGRESS with annotation
    - Plugin guardrails can block REVIEW transition

  Commands:
    RequestReview     → ReviewRequested
    ApproveReview     → ReviewApproved     (records state, non-terminal)
    RejectReview      → ReviewRejected     (task → BACKLOG or IP + notes)
    MergeTask         → TaskMerged         (task → DONE)
    RebaseTask        → TaskRebased | RebaseConflict
    CloseExploratory  → TaskClosed         (task → DONE, no merge)

  Value Objects:
    ReviewVerdict { approved, rejected, pending }
    DiffSet       { files[], additions, deletions }
    MergeStrategy { merge, squash, rebase }
```

______________________________________________________________________

## 4. Wire Protocol

The Wire is the central communication channel between core domain logic
and all client renderers. Inspired by Kimi CLI's Wire pattern.

### 4.1 Architecture

```
┌──────────────┐         ┌──────────────────────────┐
│  Core Domain │         │     BroadcastQueue        │
│              │  send   │   ┌───────────────────┐   │
│  Task ctx  ──┼────────→│   │  subscriber (TUI) │   │
│  Job ctx   ──┼────────→│   │  subscriber (Chat)│   │
│  Review ctx──┼────────→│   │  subscriber (MCP) │   │
│  Plan ctx  ──┼────────→│   │  subscriber (log) │   │
│              │         │   └───────────────────┘   │
└──────────────┘         └──────────────────────────┘
     producer              fan-out to N consumers
```

### 4.2 Event Types

```python
# Wire event hierarchy (all Pydantic BaseModel, serializable)

class WireEvent(BaseModel):
    timestamp: datetime
    task_id: TaskId | None    # None for system-level events

# Domain state changes (from aggregates)
class TaskCreated(WireEvent): ...
class TaskTransitioned(WireEvent): from_status, to_status
class TaskDeleted(WireEvent): ...
class ProjectOpened(WireEvent): project_id
class ActiveRepoSwitched(WireEvent): repo_path
class SessionOpened(WireEvent): backend, worktree_path
class SessionClosed(WireEvent): ...
class ReviewRequested(WireEvent): ...
class ReviewApproved(WireEvent): ...
class TaskMerged(WireEvent): merge_strategy
class PlanGenerated(WireEvent): items[]
class PlanApproved(WireEvent): created_task_ids[]

# Agent I/O (from running jobs)
class StreamChunk(WireEvent): text, task_id
class ToolExecution(WireEvent): tool_name, args, result
class AgentStep(WireEvent): step_number
class AgentStatus(WireEvent): tokens_used, context_pct
class AgentCompleted(WireEvent): outcome
class AgentFailed(WireEvent): error

# Interaction
class PermissionPrompt(WireEvent): tool_name, description
class PermissionResponse(WireEvent): approved
class FollowUpQueued(WireEvent): message
class FollowUpDelivered(WireEvent): message

# Job lifecycle
class JobStarted(WireEvent): job_id
class JobCancelled(WireEvent): job_id

# GitHub plugin
class PRCreated(WireEvent): pr_number, url
class PRMerged(WireEvent): pr_number
class CIStatusChecked(WireEvent): overall, checks[]
class IssuesSynced(WireEvent): created_count, updated_count
```

### 4.3 Merge Modes

```
Raw mode   (merge=False):  Every StreamChunk delivered individually
                           → For fine-grained streaming consumers

Merged mode (merge=True):  Consecutive StreamChunks coalesced into one
                           → TUI overlay uses this for clean block appends
```

### 4.4 Subscription Model

```python
class Wire:
    """Single-producer, multi-consumer event channel."""

    _broadcast: BroadcastQueue[WireEvent]

    # Producer side (core domain)
    def emit(self, event: WireEvent) -> None:
        self._broadcast.publish_nowait(event)

    # Consumer side (clients)
    def subscribe(self, merge: bool = False) -> WireSubscription:
        queue = self._broadcast.subscribe()
        return WireSubscription(queue, merge=merge)


class WireSubscription:
    async def receive(self) -> WireEvent: ...
    async def __aiter__(self) -> AsyncIterator[WireEvent]: ...
```

______________________________________________________________________

## 5. Client Architecture

### 5.1 TUI Client (Textual)

```
kagan.tui/
├── app.py              KaganApp (Textual App)
├── ui/
│   ├── board.py        Kanban board (columns, cards, indicators)
│   ├── modals/
│   │   ├── task_create.py    Create/edit task form
│   │   ├── task_detail.py    View/edit task details
│   │   ├── review.py         Review modal (summary, diff, verdict, PR comments)
│   │   └── confirm.py        Confirmation dialogs
│   ├── chat_overlay.py  Orchestrator overlay (Input + StreamingOutput, Wire subscription)
│   ├── welcome.py       Welcome screen (recent projects)
│   └── peek.py          Peek overlay (runtime snapshot)
├── styles/
│   └── kagan.tcss       Textual CSS
├── keybindings.py       Key map
└── theme.py             Color theme

Rendering contract:
  - Board and modals: static/form content only, no streaming
  - Chat overlay: subscribes to Wire(merge=True), renders via RichLog
  - Overlay auto-expands on: JobStarted, ReviewRequested events
  - Overlay toggled manually via ctrl+p
  - No Textual workers for streaming — plain asyncio.create_task
```

### 5.2 MCP Client (stdio / SSE)

```
kagan.mcp/
├── server.py            FastMCP server
├── tools/               Tool registrars by domain
│   ├── task_tools.py    task_get, task_list, task_create, task_patch, ...
│   ├── project_tools.py project_list, project_open, ...
│   ├── job_tools.py     job_start, job_poll, job_cancel
│   ├── session_tools.py session_manage
│   ├── review_tools.py  review_apply
│   ├── settings_tools.py settings_get, settings_set
│   └── github_tools.py  GitHub plugin tools
├── capabilities.py      Capability profiles (viewer → maintainer)
└── session.py           Session scoping, read-only mode

Rendering contract:
  - Subscribes to Wire for task_wait (long-poll with cursor resume)
  - Returns structured JSON responses
  - No streaming to client — poll-based with timeout
```

______________________________________________________________________

## 6. Data Flow: Key Scenarios

### 6.1 Start AUTO Agent (US-034, US-056, US-062)

```
User presses ↵ on AUTO task in board
  │
  ├─ TUI → Command(StartJob{task_id})
  │
  ├─ Core: Task aggregate asserts status=IN_PROGRESS, type=AUTO
  ├─ Core: Workspace context provisions worktree
  ├─ Core: Job aggregate spawns agent
  ├─ Core: Wire.emit(JobStarted{task_id, job_id})
  │
  ├─ TUI subscriber receives JobStarted → auto-expand overlay
  ├─ MCP subscriber receives JobStarted → available via job_poll
  │
  ├─ Agent runs, emits: StreamChunk, ToolExecution, AgentStep...
  │   └─ All flow through Wire → all subscribers
  │
  └─ Agent completes → Wire.emit(AgentCompleted)
      ├─ TUI: board card updates status indicator
      └─ Chat: shows "✓ Complete"
```

### 6.2 Plan and Create Tasks (US-050–053)

```
User types "plan an auth system" in orchestrator overlay
  │
  ├─ TUI overlay → Planning context: GeneratePlan
  ├─ Core: LLM generates plan items
  ├─ Wire.emit(PlanGenerated{items})
  │
  ├─ TUI overlay renders plan items with [a]pprove [e]dit [d]ismiss
  │
  ├─ User presses [a]
  ├─ TUI overlay → Planning context: ApprovePlan
  ├─ Core: creates Task per plan item
  ├─ Wire.emit(PlanApproved{task_ids})
  ├─ Wire.emit(TaskCreated × N)
  │
  ├─ TUI subscriber: board refreshes with new tasks
  ├─ MCP subscriber: task_list returns new tasks
  └─ TUI overlay: "Created 4 tasks"
```

### 6.3 Review and Merge (US-063, US-072–073)

```
Path A: User presses ↵ on REVIEW task in TUI board
  │
  ├─ TUI: opens Review modal (static: summary + diff + verdict + PR comments)
  ├─ TUI: if auto_review, sends Command(RunReviewAgent)
  ├─ Core: spawns review agent
  ├─ Wire.emit(ReviewAgentStarted)
  │
  ├─ TUI overlay auto-expands, shows review agent stream
  ├─ Review agent completes → Wire.emit(ReviewCompleted{verdict})
  ├─ TUI: modal Review tab populates with verdict
  │
  ├─ User presses [m] merge in modal
  ├─ TUI → Command(MergeTask{task_id})
  │
  └─ (continues below)

Path B: User types "/merge task-abc" in orchestrator overlay
  │
  ├─ TUI overlay → Command(MergeTask{task_id})
  │
  └─ (continues below)

Both paths:
  ├─ Core: Review aggregate checks serialize_merges, require_approval
  ├─ Core: performs merge (quiesce, risk assessment, rebase retry)
  ├─ Wire.emit(TaskMerged{task_id})
  │
  ├─ TUI: modal closes, board card moves to DONE
  ├─ TUI overlay: "✓ task-abc merged"
  ├─ GitHub plugin: closes linked issue, syncs labels
  └─ All clients: updated via Wire events
```

### 6.4 Multi-Instance Sync (US-005)

```
Instance A (TUI) creates a task
  │
  ├─ Core: Task aggregate → Wire.emit(TaskCreated)
  │
  ├─ Instance A (TUI): board refreshes (local)
  ├─ Instance B (TUI): Wire subscriber → board refreshes
  ├─ Instance C (MCP): Wire subscriber → task_list updated
  │
  All instances reflect same state within event delivery latency
```

______________________________________________________________________

## 7. Package Structure

```
src/kagan/
├── __main__.py              Entry point
├── core/                    Domain logic (no UI dependencies)
│   ├── domain/
│   │   ├── task.py          Task aggregate
│   │   ├── project.py       Project aggregate
│   │   ├── session.py       PairSession aggregate
│   │   ├── job.py           Job aggregate
│   │   ├── plan.py          Plan aggregate
│   │   ├── review.py        Review aggregate
│   │   └── events.py        All domain events
│   ├── services/
│   │   ├── task_service.py
│   │   ├── project_service.py
│   │   ├── job_service.py
│   │   ├── session_service.py
│   │   ├── review_service.py
│   │   ├── planning_service.py
│   │   └── merge_service.py
│   ├── ports/               Interfaces (protocols)
│   │   ├── repository.py    TaskRepository, ProjectRepository, ...
│   │   ├── agent_runner.py  AgentRunner protocol
│   │   ├── workspace.py     WorkspaceProvider protocol
│   │   └── event_bus.py     EventBus / Wire protocol
│   ├── adapters/            Implementations
│   │   ├── sqlite/          SQLite persistence
│   │   ├── git/             Git workspace operations
│   │   └── agents/          Claude, Codex, Copilot, Gemini, Kimi, OpenCode
│   ├── plugins/
│   │   ├── registry.py      Plugin operation registry
│   │   └── github/          Bundled GitHub plugin (ACL)
│   │       ├── adapter.py   GitHub API → Kagan domain translation
│   │       ├── operations.py
│   │       └── hooks.py     Lifecycle hooks (REVIEW guardrails, status sync)
│   └── config/
│       ├── settings.py      Runtime settings (serialize_merges, etc.)
│       └── onboarding.py    First-run config collection
│
├── tui/                     TUI client (Textual, native widgets)
│   ├── app.py               KaganApp
│   ├── ui/
│   │   ├── board.py         Kanban board
│   │   ├── chat_overlay.py  Wire → Input + RichLog (asyncio.create_task)
│   │   ├── modals/          Create, detail, review (static), confirm
│   │   ├── welcome.py       Welcome screen
│   │   └── peek.py          Peek overlay
│   ├── styles/
│   └── keybindings.py
│
├── cli/                     CLI entry points (Click/Typer)
│   ├── __init__.py          Main CLI group
│   ├── tui.py               kagan / kagan tui
│   ├── core.py              kagan core start/status/stop
│   ├── mcp.py               kagan mcp [flags]
│   ├── doctor.py            kagan doctor
│   ├── update.py            kagan update
│   ├── reset.py             kagan reset
│   ├── list.py              kagan list
│   └── tools.py             kagan tools enhance
│
└── mcp/                     MCP server
    ├── server.py
    ├── tools/
    ├── capabilities.py
    └── session.py
```

______________________________________________________________________

## 8. Technology Choices

| Layer          | Technology                      | Rationale                                              |
| -------------- | ------------------------------- | ------------------------------------------------------ |
| Core domain    | Pure Python + Pydantic          | No framework lock-in, serializable events              |
| Event bus      | Wire + BroadcastQueue           | Proven pattern (Kimi CLI), async native                |
| Persistence    | SQLite (via adapters)           | Single-file, no server, concurrent-read safe           |
| TUI            | Textual                         | Existing investment, CSS styling, native widgets       |
| TUI overlay    | Textual Input + StreamingOutput | Native widgets, Wire subscription, asyncio.create_task |
| CLI framework  | Click/Typer                     | Existing investment, argument parsing                  |
| MCP server     | FastMCP                         | Existing investment, stdio/SSE                         |
| Git operations | subprocess (git)                | Direct, no abstraction needed                          |
| GitHub API     | gh CLI / httpx                  | gh for user-facing, httpx for automation               |

______________________________________________________________________

## 9. Key Architecture Decisions

### ADR-001: Singleton Core with Event-Based Multi-Client Sync

All state lives in one daemon. Clients subscribe to Wire events for
real-time updates. No distributed state, no conflicts, no locks.
Satisfies US-005.

### ADR-002: TUI Orchestrator Overlay as Universal Control Surface with Admin MCP Parity

The orchestrator overlay is a native Textual widget embedded in the TUI.
Every MCP operation is available via natural language or slash commands.
Input and streaming output use native Textual widgets (Input, StreamingOutput).
No separate REPL, no prompt_toolkit. Satisfies US-047, US-061–066.

### ADR-003: Wire Protocol for All Domain Events

All aggregate state changes and agent I/O emit typed WireEvents through
a BroadcastQueue. Clients subscribe independently. Supports merge mode
for TUI overlay (block appends) and raw mode for fine-grained streaming.
Inspired by Kimi CLI's Wire pattern. Satisfies US-046.

### ADR-004: Review Modal as Static Decision Surface

Review modal shows only completed/static content (diff, summary, verdict,
PR comments). Live review-agent output streams in chat overlay. Modal
has no streaming, no workers, no waiting states. Satisfies US-066.

### ADR-005: Task Aggregate Enforces Lifecycle Invariants

DONE status only reachable via review_apply(merge) or close_exploratory.
Direct DONE mutation rejected at aggregate level. Type changes trigger
side effects (stop agent, kill session). Satisfies US-028–033.

### ADR-006: GitHub Plugin as Anti-Corruption Layer

GitHub concepts (issues, PRs, checks, labels) translated into Kagan
domain (tasks, reviews, status, metadata) at the plugin boundary.
Core domain never imports GitHub types. Satisfies US-076–087.

### ADR-007: No Instance Locking

Multiple TUI and MCP instances coexist freely. Concurrency handled by
singleton core + event broadcast, not locks. The only locks are
GitHub issue leases for distributed team coordination. Satisfies US-005.

______________________________________________________________________

## 10. Story-to-Architecture Traceability

| Epic                    | Stories    | Primary Context             | Client Surface              |
| ----------------------- | ---------- | --------------------------- | --------------------------- |
| 1. Onboarding           | US-001–009 | Config, Preflight           | CLI, TUI                    |
| 2. Project/Repo         | US-010–017 | Project                     | TUI, MCP                    |
| 3. Kanban Board         | US-018–027 | Task                        | TUI, MCP                    |
| 4. Task Lifecycle       | US-028–033 | Task (invariants)           | Core (enforced)             |
| 5. AUTO Execution       | US-034–037 | Workspace, Job              | TUI (trigger), MCP          |
| 6. PAIR Execution       | US-038–045 | Session                     | TUI, MCP                    |
| 7. Orchestrator Overlay | US-046–071 | All contexts (admin parity) | TUI overlay                 |
| 8. Review/Merge         | US-072–081 | Review                      | TUI modal, TUI overlay, MCP |
| 9. GitHub               | US-082–093 | GitHub plugin (ACL)         | TUI, TUI overlay, MCP       |
| 10. MCP Access          | US-094–096 | MCP capabilities            | MCP                         |
| 11. CLI Ops             | US-097–106 | CLI commands                | CLI                         |
