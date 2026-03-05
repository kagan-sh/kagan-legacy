# Kagan2 Reliability Patterns (Selective Retrofit)

## Intent

Capture what made legacy `kagan2` reliable, but retrofit only the minimal pieces that fit current architecture in `docs/internal/`.

This is intentionally selective: legacy was functional, but overbuilt in places. We keep reliability-critical behavior and avoid framework-heavy layers.

______________________________________________________________________

## What Worked in Legacy (Worth Reusing)

### 1) Explicit Review Gates Before Merge

Legacy enforced a clear review contract: merge from REVIEW only, and optionally require explicit approval first.

References:

- `references/kagan2/src/kagan/core/api/reviews.py` (`review_merge`, `_is_latest_review_approved`)

Why it mattered:

- Prevented "silent" DONE transitions.
- Kept merge behavior deterministic and auditable.

Retrofit target in current design:

- Keep merge as the only `REVIEW -> DONE` path in core.
- Keep/extend explicit failure events and status events for evidence (`MERGE_FAILED`, `MERGE_COMPLETED`, `TASK_STATUS_CHANGED`).

______________________________________________________________________

### 2) Rebase Conflict Recovery as a First-Class Flow

Legacy treated rebase conflict as a normal state transition path, not an edge case.

References:

- `references/kagan2/src/kagan/core/api/reviews.py` (`_rebase_task_orchestration`, `review_rebase`)

Why it mattered:

- Conflicts did not dead-end task execution.
- System exposed conflict files and recovery actions.

Retrofit target in current design:

- Core review API exposes conflict lifecycle methods:
  - `conflicts(task_id)`

  - `rebase(task_id)`

  - `continue_rebase(task_id)`

  - `abort_rebase(task_id)`
- MCP surfaces these as dedicated tools so orchestrators can recover without guessing.

______________________________________________________________________

### 3) Capability-Aware MCP Access

Legacy consistently separated read/write/destructive behavior.

References:

- `references/kagan2/src/kagan/mcp/toolsets/review.py`
- `references/kagan2/src/kagan/core/policy.py`

Why it mattered:

- Reduced accidental destructive actions.
- Made behavior predictable for hosts and orchestrators.

Retrofit target in current design:

- Keep simple tiering in MCP policy (`READONLY`, `STANDARD`, `ADMIN`).

- Register review conflict status as read-only; mutate actions as default/admin.

______________________________________________________________________

### 4) Settings-Driven Behavior with an Allowlist Mindset

Legacy settings layer prevented random key mutation and made behavior explicit.

References:

- `references/kagan2/src/kagan/core/settings.py`

Why it mattered:

- Fewer accidental config states.
- Better operator trust and debuggability.

Retrofit target in current design:

- Keep current simple `Setting` table + `Settings` API.

- Add validation for behavior-critical keys only (not full legacy settings framework).

______________________________________________________________________

### 5) Bounded External Guardrails

Legacy used timeout-bounded guardrail checks before review transition.

References:

- `references/kagan2/src/kagan/core/api/reviews.py` (`_check_review_guardrails`)

Why it mattered:

- External integrations could fail without freezing the workflow.

Retrofit target in current design:

- If guardrails are added, they must be optional, timeout-bounded, and fail with explicit structured errors.

______________________________________________________________________

## What to Avoid from Legacy (Do Not Retrofit)

- Full command-decorator/registry framework for all API calls.
- Dual-layer request/response contract systems when core models already define behavior.
- Overly nested policy machinery that duplicates simple MCP access-tier checks.

Reason: these increased maintenance and cognitive load without being the core source of reliability.

______________________________________________________________________

## Retrofit Decisions for Current Architecture

Aligned with `docs/internal/architecture/core.md` and `docs/internal/features/core.md`.

1. Keep reliability logic in `core` (not chat/UI).
1. Keep MCP as thin adapter that exposes explicit recovery tools.
1. Preserve flat module boundaries and direct APIs.
1. Prefer explicit events and deterministic transitions over hidden side effects.

Concrete behavior contract:

- `task.set_status()` never reaches DONE directly.

- `review.merge()` is the only DONE transition and emits evidence events.

- rebase/conflict lifecycle is queryable and recoverable through MCP.

______________________________________________________________________

## Acceptance Checks (Parity Without Bloat)

- Orchestrator can move tasks from REVIEW to DONE only via merge path.
- Merge failures include conflict file evidence.
- Rebase conflicts can be inspected, continued, or aborted from MCP tools.
- Access tiers correctly hide/show review mutation tools.
- Settings for default agent/backend and branch behavior remain core-owned and deterministic.

______________________________________________________________________

## Source Index

Legacy references:

- `references/kagan2/src/kagan/core/api/reviews.py`
- `references/kagan2/src/kagan/core/settings.py`
- `references/kagan2/src/kagan/core/policy.py`
- `references/kagan2/src/kagan/mcp/toolsets/review.py`

Current design references:

- `docs/internal/architecture/core.md`
- `docs/internal/features/core.md`
- `docs/internal/features/mcp.md`
