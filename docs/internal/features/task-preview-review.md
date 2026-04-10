# Task Preview & Post-Creation Review

**Status:** Proposed
**Scope:** Core (orchestrator prompt), Chat, TUI, Web, MCP

## Problem

When the orchestrator creates tasks via `task_create`, users lack a structured,
editable view of what was created. The orchestrator may present a text table before
creation but does not consistently follow up with an actionable review after tasks
land on the board. Users want to:

- See a concise overview of all tasks just created (title, mode, priority, AC count)
- Make quick edits (tweak a title, adjust priority, add/remove acceptance criteria)
- Delete tasks that don't belong
- Reorder or adjust execution mode before agents launch

## Design Decision: Autonomous Creation + Review Loop

**We embrace autonomous creation.** The orchestrator creates tasks directly — no
blocking approval gate. This is the right UX for AI-assisted tools because:

1. **Task creation is cheap and reversible** — BACKLOG tasks cost nothing to create or delete.
1. **Visual feedback beats text proposals** — a real task on the board with metadata
   is more useful than a text summary the user has to mentally map.
1. **Lower friction** — no modal approval interrupting conversational flow.
1. **Matches modern AI tool patterns** — act autonomously, then present for review.

The old plan-approval flow (removed in v0.9.0) was a blocking modal that required
explicit "approve" before any task existed. That created unnecessary friction and
was architecturally fragile (orphaned workers, timing issues in tests).

**What we add instead:** a mandatory **post-creation review nudge** in the
orchestrator prompt, plus structured task-preview rendering across all clients.

## Orchestrator Behavior

After every `task_create` call, the orchestrator MUST:

1. **Present a structured overview** of all created tasks as a markdown table:

   ```text
   | # | Title | Launcher | Priority | AC | Status |
   |---|-------|----------|----------|----|--------|
   | 1 | Fix login bug | Default | HIGH | 3 | BACKLOG |
   | 2 | Add dark mode | tmux | MEDIUM | 4 | BACKLOG |
   ```

1. **Explicitly invite edits** with a prompt like:

   > "Here are the tasks I created. Would you like to edit any titles,
   > priorities, acceptance criteria, or launcher preferences before I start
   > execution? You can also delete tasks that don't belong."

1. **Wait for user response** before calling `run_start` on any task.

1. **Apply edits** via `task_update` or `task_delete` based on user feedback.

1. **Only then** proceed to execution waves.

This is enforced via the orchestrator system prompt, not application code. The
orchestrator is an LLM agent — the prompt IS the feature.

## Client Rendering

Each client renders the task overview in its native idiom:

### Chat REPL (`kg chat`)

- Rich table in terminal (already supported — orchestrator outputs markdown tables)
- No special rendering needed beyond what Rich/Markdown already does

### TUI (`kg` / `kg tui`)

- AI Panel already renders markdown tables via StreamingOutput

- No new widgets needed — the old PlanDisplay/PlanApprovalWidget are deleted

- If richer preview is desired later, add a TaskPreviewWidget (not blocking)

- AI Panel already renders markdown tables via StreamingOutput

- No new widgets needed — the old PlanDisplay/PlanApprovalWidget are deleted

- If richer preview is desired later, add a TaskPreviewWidget (not blocking)

- No new widgets needed — the old PlanDisplay/PlanApprovalWidget are deleted

- If richer preview is desired later, add a TaskPreviewWidget (not blocking)

- No new widgets needed — the old PlanDisplay/PlanApprovalWidget are deleted

- If richer preview is desired later, add a TaskPreviewWidget (not blocking)

- No new widgets needed — the old PlanDisplay/PlanApprovalWidget are deleted

- If richer preview is desired later, add a TaskPreviewWidget (not blocking)

### Web (`kg web`)

- AI Panel renders markdown tables via existing markdown-content component

- Board shows tasks immediately (they're real BACKLOG tasks)

- Task Inspector sidebar shows full metadata for quick review

- Future enhancement: highlight "just created" tasks with a temporary badge

- AI Panel renders markdown tables via existing markdown-content component

- Board shows tasks immediately (they're real BACKLOG tasks)

- Task Inspector sidebar shows full metadata for quick review

- Future enhancement: highlight "just created" tasks with a temporary badge

- Board shows tasks immediately (they're real BACKLOG tasks)

- Task Inspector sidebar shows full metadata for quick review

- Future enhancement: highlight "just created" tasks with a temporary badge

### MCP (`kg mcp`)

- Tool responses from `task_create` already return full task payloads
- MCP clients (Claude Desktop, etc.) render tool results natively
- No changes needed

## Prompt Changes

The orchestrator prompt `<workflow>` section step 4 changes from:

```text
4. On approval: call task_create with a tasks list.
```

To:

```text
4. On approval: call task_create with a tasks list.
5. IMMEDIATELY after creation: present a review table showing every created task
   with its id, title, launcher, priority, and acceptance_criteria count.
   Ask: "Review the tasks above. Want to edit anything before I start execution?"
6. Wait for user response. Apply any requested edits via task_update/task_delete.
7. Only after user confirms (or says "looks good" / "go" / "start"): proceed to
   execution waves.
```

The `<tool-discipline>` section adds:

```text
- After task_create: ALWAYS present a review table and ask for edits before
  starting execution. Never skip this step. Never auto-start without user confirmation.
```

The `<constraints>` ALWAYS section adds:

```text
- After creating tasks, present a structured review table and wait for user
  confirmation before starting any execution. This gives users a chance to
  edit titles, priorities, acceptance criteria, or execution modes.
```

## What This Is NOT

- **Not a blocking approval gate** — tasks are already created on the board
- **Not a new UI component** — uses existing rendering (markdown tables, board)
- **Not a new event type** — no `PLAN_UPDATE` or similar
- **Not a code change** — it's a prompt change enforcing orchestrator behavior

## Future Enhancements

1. **"Just created" badge** on web board — highlight tasks created in the last 30s
1. **Bulk edit dialog** on web — select multiple tasks, edit shared fields
1. **Task preview card** in chat — richer than a table, with inline edit buttons
1. **Undo creation** — "undo last batch" command that deletes all tasks from the
   most recent `task_create` call
