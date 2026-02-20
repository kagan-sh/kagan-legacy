# Epic 7: Orchestrator Overlay (TUI Native Chat)

The orchestrator overlay is a native Textual widget embedded in the TUI. It provides
the universal control surface for planning, agent output, and admin operations.
It has full parity with admin MCP capabilities: every operation available via MCP
tools is performable via natural language or commands. The chat experience uses
native Textual widgets (Input, StreamingOutput, etc.) — no separate REPL, no
prompt_toolkit. Fullscreen by default when opening a project; p = bottom overlay,
Ctrl+P = fullscreen.

## Wire Protocol

| ID | Story |
|----|-------|
| US-046 | As a user, I want a Wire event protocol with strongly-typed events (StreamChunk, ToolExecution, AgentStatus, PermissionPrompt, etc.) and a BroadcastQueue so multiple consumers can subscribe to the same agent stream independently. |

## TUI Orchestrator Overlay

| ID | Story |
|----|-------|
| US-047 | As a TUI user, I want an orchestrator overlay (p / Ctrl+P) to plan, manage tasks, query the board, and interact with agents using native Textual widgets. |
| US-048 | As a TUI user, I want slash commands and autocomplete in the orchestrator overlay covering admin operations (/help, /clear, /create, /edit, /move, /delete, /start, /stop, /focus, /unfocus, /follow, /list, /approve, /merge, /reject, /rebase, /settings, /project, /repo, /gh). |
| US-049 | As a TUI user, I want board queries from the orchestrator ("show backlog", "what's in review", "list projects") so I can inspect full system state without leaving the overlay. |

## Planning

| ID | Story |
|----|-------|
| US-050 | As a user, I want plan mode to generate structured tasks from natural language input. |
| US-051 | As a user, I want plan approval controls (approve/edit/dismiss) before tasks are created. |
| US-052 | As a user, I want a task editor for generated plan items so I can tune priority/type/backend/branch/AC before approval. |
| US-053 | As a user, I want approved plans persisted as created tasks with notifications and board refresh. |
| US-054 | As a user, I want dismissed plans to continue conversational refinement instead of hard reset. |
| US-055 | As a user, I want planner draft persistence and restoration of pending drafts when revisiting chat. |

## Agent Output Streaming

| ID | Story |
|----|-------|
| US-056 | As a user, I want live agent output streaming via the Wire so I can watch AUTO agents work in real time. |
| US-057 | As a user, I want stale-output recovery and backfill if execution metadata exists but no live agent stream is attached. |
| US-058 | As a user, I want multi-agent output multiplexing with task-id prefixed lines and /focus to filter to a single agent. |
| US-059 | As a user, I want to send follow-up instructions to a running agent (/follow task-id message) without losing run context. |
| US-060 | As a user, I want to stop a running agent from the overlay (/stop task-id) with confirmation feedback. |

## Admin Operations (MCP Parity)

| ID | Story |
|----|-------|
| US-061 | As a user, I want to create, edit, move, and delete tasks from the orchestrator overlay via natural language or slash commands (/create, /edit, /move, /delete) so I have full board control. |
| US-062 | As a user, I want to start AUTO agents and open/close PAIR sessions from the overlay (/start, /session open, /session close) so execution control is available from the overlay. |
| US-063 | As a user, I want to trigger review actions from the overlay (/approve, /reject, /merge, /rebase) so I can complete the full review workflow without the TUI modal. |
| US-064 | As a user, I want to manage settings from the overlay (/settings) so I can configure serialize_merges, auto_review, require_review_approval, and other options inline. |
| US-065 | As a user, I want to invoke GitHub plugin operations from the overlay (/gh connect, /gh sync, /gh pr create, /gh pr merge) so GitHub workflows are accessible. |
| US-066 | As a user, I want to manage projects and repos from the overlay (/project create, /project open, /repo add, /repo switch) so I can set up and switch context. |

## TUI Integration

| ID | Story |
|----|-------|
| US-067 | As a TUI user, I want an orchestrator overlay (p = bottom overlay, Ctrl+P = fullscreen) that renders Wire events via native Textual widgets (Input + StreamingOutput) so chat is seamlessly embedded in the board. |
| US-068 | As a TUI user, I want the overlay to auto-expand when an AUTO agent starts or a review agent runs so I see output immediately without manual toggle. |

## Interaction Polish

| ID | Story |
|----|-------|
| US-069 | As a user, I want prompt refinement (F2) with validation rules (min length, skip prefixes, enabled flag). |
| US-070 | As a user, I want permission prompts and optional auto-approve for planner and agent tool calls. |
| US-071 | As a user, I want queued follow-ups while the agent is processing so no input is lost. |
