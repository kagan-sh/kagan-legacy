# Refinement Candidates: Lessons from Claude Code Unpacked

**Date:** 2026-04-02
**Source:** [ccunpacked.dev](https://ccunpacked.dev/) — analysis of Claude Code's 519K+ LOC codebase
**Branch:** `refine/ccunpacked-best-practices`

______________________________________________________________________

## Summary

Claude Code Unpacked maps the full internals of Claude Code: an 11-step agent loop,
53+ tools, 95+ slash commands, and several unreleased features (Coordinator Mode,
Auto-Dream, Bridge, Kairos). After comparing these patterns against Kagan's current
implementation, five high-impact refinement candidates emerge — each targeting a gap
that directly affects UX or reliability.

______________________________________________________________________

## Candidate 1: Context Compaction (Conversation Summarization)

**CC Pattern:** Step-based compaction via `/compact` command. Clears conversation
history but injects an AI-generated summary so the agent retains key context without
consuming the full token budget. Also has `Snip` (feature-gated) for trimming old
turns selectively.

**Kagan Gap:** Zero compaction. Sessions track `context_window_used` /
`context_window_size` as read-only metrics (in `models.py:105-106`), but when context
fills up the agent simply fails. There is no summarization, truncation, or message
pruning.

**Impact:** **Reliability — Critical.** Long-running tasks on large codebases hit
context limits and abort with no recovery path. This is the single biggest reliability
gap.

**Proposed Refinement:**

1. Add a `compact_session()` service method in `_sessions.py` that:
   - Reads the current ACP conversation history
   - Calls the LLM with a summarization prompt (keep tool results, drop verbose output)
   - Replaces history with: system prompt + summary message + last N tool results
1. Wire it into the agent loop: when `context_window_used / context_window_size > 0.8`,
   auto-trigger compaction before the next API call.
1. Expose as an MCP tool for manual use and as a TUI action.
1. Track compaction events in session metadata for observability.

**Affected files:**

- `src/kagan/core/_sessions.py` — new `compact_session()` method
- `src/kagan/core/_acp.py` — intercept context threshold in ACP callback
- `src/kagan/server/mcp/toolsets/sessions.py` — new MCP tool
- `src/kagan/tui/widgets/agent_status.py` — compaction indicator

______________________________________________________________________

## Candidate 2: Pre/Post Tool Execution Hooks

**CC Pattern:** Full hook lifecycle — post-sampling hooks (Step 10 in the agent loop)
run after every LLM response. Users configure hooks in `settings.json` tied to tool
events (e.g., `PreToolExecution`, `PostToolExecution`, `NotificationHook`). The
`/hooks` command manages them. Hooks can block, modify, or log tool calls.

**Kagan Gap:** Only a `RepetitionGuard` exists (`_repetition_guard.py`) — detects the
same tool call 8+ times in a 20-call window and cancels. No general-purpose hook
system for pre/post tool execution, no user-configurable hooks, no notification hooks.

**Impact:** **UX + Reliability — High.** Hooks enable guardrails (prevent destructive
commands), audit logging (track all file writes), quality gates (lint after every edit),
and notifications (alert on completion). Without them, users have no way to enforce
policy on agent behavior.

**Proposed Refinement:**

1. Define a `Hook` protocol in `src/kagan/core/hooks.py`:
   ```python
   class Hook(Protocol):
       event: HookEvent  # PRE_TOOL, POST_TOOL, POST_SAMPLING, SESSION_END

       async def execute(self, context: HookContext) -> HookResult: ...
   ```
1. Add a `HookRunner` that loads hooks from project settings (`.kagan/hooks/`) and
   fires them at the appropriate lifecycle points.
1. Integrate into `_sessions.py` ACP callback — fire `POST_TOOL` after each
   `ToolCallEnd` event, `POST_SAMPLING` after each full LLM turn.
1. Built-in hooks: `RepetitionGuard` (migrate existing), `DangerousCommandBlocker`
   (reject `rm -rf /`, `git push --force` etc.), `LintAfterEdit`.
1. Expose hook management via MCP toolset and TUI settings screen.

**Affected files:**

- `src/kagan/core/hooks.py` — new module
- `src/kagan/core/_sessions.py` — hook firing points
- `src/kagan/core/_repetition_guard.py` — migrate to hook interface
- `src/kagan/server/mcp/toolsets/settings.py` — hook CRUD tools

______________________________________________________________________

## Candidate 3: Plan Verification / Mid-Execution Validation

**CC Pattern:** `VerifyPlanExecution` tool (feature-gated) checks whether a plan step
was executed correctly before proceeding to the next. Separate from the review phase —
this is inline validation during execution. Combined with `EnterPlanMode` /
`ExitPlanMode` for structured plan-then-execute workflows.

**Kagan Gap:** Acceptance criteria are embedded in the task prompt and verified only
during the separate review phase (by a different AI reviewer). No mid-execution
checkpoint. If an agent drifts on step 2 of 10, it wastes the remaining 8 steps before
review catches it.

**Impact:** **Reliability — High.** Early drift detection saves tokens, time, and
prevents compounding errors. Especially important for multi-step tasks where each step
builds on the last.

**Proposed Refinement:**

1. Add a `verify_step()` service method that:
   - Takes the current task, step index, and expected outcome
   - Runs a lightweight LLM call (or deterministic check) to verify the step
   - Returns PASS / FAIL / NEEDS_RETRY with explanation
1. Integrate with the existing planning depth setting (`planning_depth` in settings):
   - When `planning_depth: "always"`, inject verification checkpoints between plan steps
   - Agent prompt includes: "After completing each step, call verify_step() before
     proceeding"
1. On FAIL: inject a correction prompt into the ACP session with the failure reason
1. Track verification results in session events for post-mortem analysis
1. Expose as MCP tool for orchestrator-level verification

**Affected files:**

- `src/kagan/core/_sessions.py` — verification integration
- `src/kagan/core/_prompts.py` — checkpoint injection in task prompts
- `src/kagan/server/mcp/toolsets/sessions.py` — `verify_step()` tool
- `src/kagan/core/models.py` — `VerificationResult` model

______________________________________________________________________

## Candidate 4: Session Rewind / Conversation Branching

**CC Pattern:** `/rewind` restores code AND conversation to a previous point (uses git
commits as anchors). `/branch` creates a fork of the current conversation at a specific
turn. Together they let users recover from agent mistakes without starting over.

**Kagan Gap:** No rewind capability. Tasks can be moved back to BACKLOG for re-attempt,
and sessions can be cancelled, but there's no way to restore to a mid-session state.
The worktree system has git history, but no UI or service to leverage it for rewind.

**Impact:** **UX — High.** When an agent goes off-track at turn 15 of 30, users
currently must cancel and re-run from scratch. Rewind to turn 14 would save significant
time and token cost.

**Proposed Refinement:**

1. Add automatic git checkpoint tagging in worktrees:
   - After each successful tool execution that modifies files, create a lightweight git
     tag: `kagan/checkpoint/{session_id}/{step_n}`
   - Store checkpoint metadata (step index, timestamp, context snapshot) in session events
1. Add `rewind_session()` service method:
   - Takes session_id and target step/checkpoint
   - Resets worktree to that checkpoint's git state (`git reset --hard`)
   - Truncates session events after that point
   - Optionally re-runs from that point with a corrective prompt
1. Expose via:
   - MCP tool: `session_rewind(session_id, step)`
   - TUI: Rewind action in session detail view (pick from checkpoint list)
   - Web: Timeline scrubber on task detail page
1. For conversation branching: clone the session up to a point and create a new session
   with the same history prefix but divergent continuation

**Affected files:**

- `src/kagan/core/_sessions.py` — checkpoint creation, rewind logic
- `src/kagan/core/_worktrees.py` — git checkpoint tagging
- `src/kagan/server/mcp/toolsets/sessions.py` — rewind/branch tools
- `src/kagan/tui/screens/task_detail.py` — rewind UI

______________________________________________________________________

## Candidate 5: Auto-Dream / Memory Consolidation

**CC Pattern:** "Auto-Dream" — between sessions, the AI reviews what happened and
organizes what it learned. Combined with `memdir/` (persistent memory directory) for
session-to-session knowledge. Also "Kairos" mode with memory consolidation and
autonomous background actions.

**Kagan Gap:** Only `[LEARNING]` prefixed notes exist — manually added by agents,
collected up to 20 per project, injected into next task prompt. No automatic
consolidation, no cross-project knowledge, no between-session review, no structured
memory taxonomy.

**Impact:** **UX — Medium-High.** Over many tasks, agents repeat mistakes and
re-discover patterns. Automatic memory consolidation would accumulate project-specific
knowledge (common error patterns, architecture decisions, preferred approaches) and make
each subsequent task smarter.

**Proposed Refinement:**

1. Add a `consolidate_learnings()` background task that runs after session completion:
   - Reviews all session events and tool outputs from the completed session
   - Extracts key learnings, error patterns, and architectural insights
   - Deduplicates against existing project learnings
   - Categorizes: `[PATTERN]`, `[ERROR]`, `[ARCHITECTURE]`, `[PREFERENCE]`
1. Store consolidated memory in a structured format:
   - New `ProjectMemory` model with categories, relevance scores, and timestamps
   - Decay old memories (reduce relevance score over time)
   - Cap at configurable limit (default: 50 entries)
1. Smarter injection into prompts:
   - Instead of raw `[LEARNING]` strings, select most relevant memories based on task
     description similarity (simple keyword/embedding match)
   - Include category labels so the agent knows what kind of knowledge it is
1. Expose memory management:
   - MCP tool: `memory_list()`, `memory_add()`, `memory_remove()`
   - TUI: Memory browser screen showing project knowledge base
   - CLI: `kagan memory list/add/remove/consolidate`

**Affected files:**

- `src/kagan/core/_memory.py` — new module for memory consolidation
- `src/kagan/core/models.py` — `ProjectMemory` model
- `src/kagan/core/_sessions.py` — trigger consolidation on session end
- `src/kagan/server/mcp/toolsets/memory.py` — new MCP toolset
- `src/kagan/cli/memory.py` — new CLI command group

______________________________________________________________________

## Priority Matrix

| #   | Candidate            | Impact                  | Effort | Priority |
| --- | -------------------- | ----------------------- | ------ | -------- |
| 1   | Context Compaction   | Critical (reliability)  | Medium | **P0**   |
| 2   | Tool Execution Hooks | High (reliability + UX) | Medium | **P1**   |
| 3   | Plan Verification    | High (reliability)      | Medium | **P1**   |
| 4   | Session Rewind       | High (UX)               | High   | **P2**   |
| 5   | Auto-Dream Memory    | Medium-High (UX)        | High   | **P2**   |

**Recommended order:** 1 → 2 → 3 → 4 → 5

Candidates 1-3 are foundational reliability improvements that should land before the
UX-oriented candidates 4-5. Context compaction (1) is the single most impactful change
because it eliminates the hard failure mode of context exhaustion.

______________________________________________________________________

## Appendix: CC Patterns Evaluated but Deprioritized

| CC Pattern                                       | Why Deprioritized                                                                         |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Bridge (remote control from phone/browser)       | Kagan already has web dashboard + SSE streaming                                           |
| Buddy (virtual pet)                              | Fun but zero reliability/UX impact                                                        |
| Voice mode                                       | Niche use case, high effort                                                               |
| Daemon mode (tmux --bg)                          | Kagan already runs detached processes                                                     |
| UDS Inbox (inter-session messaging)              | Low priority until multi-session orchestration matures                                    |
| Coordinator Mode (lead agent + parallel workers) | Kagan already has parallel worktree agents; gap is coordination quality, not architecture |
