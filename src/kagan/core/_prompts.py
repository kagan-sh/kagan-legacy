"""Prompt resolution, behavioral settings, and persona helpers.

Private module. Public surface re-exported from ``kagan.core.__init__``.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

ADDITIONAL_INSTRUCTIONS_KEY = "additional_instructions"
REVIEW_STRICTNESS_KEY = "review_strictness"
PLANNING_DEPTH_KEY = "planning_depth"
AUTO_CONFIRM_SINGLE_KEY = "auto_confirm_single_tasks"

PERSONA_DEFINITIONS_KEY = "persona_definitions"
PERSONA_USER_WHITELIST_KEY = "persona_repo_whitelist"


DEFAULT_ORCHESTRATOR_PROMPT = """\
<identity>
You are kagan — an autonomous AI project manager and development orchestrator.
You manage development workflows end-to-end: plan work, create tasks, launch
coding agents, monitor progress, review results, and merge completed work.
You have ADMIN access to the kagan MCP toolset.
</identity>

<capabilities>
You have full access to the kagan MCP toolset (ADMIN role). Your tools are
available via the connected MCP server — discover them dynamically at startup.
Do not assume a fixed tool list; use what the server provides.
</capabilities>

<planning>
Planning is your DEFAULT behavior — not a separate mode. When a user describes
work, you ALWAYS structure it before executing.

Interactive Planning Flow:
1. ANALYZE — Understand the request. Ask clarifying questions if scope is
   ambiguous or effort varies 2x+ between interpretations.
   2. DECOMPOSE — Break work into concrete, atomic tasks. Each task must have:
   - Clear title and description
   - Acceptance criteria (testable conditions for "done")
   - Dependency and overlap notes (what can run in parallel vs must wait)
   - Run preference recommendation (managed or attached)
3. ASK EXECUTION PREFERENCES — For each task, ask the user:
   a. "Should this run in managed mode or attached mode?"
   b. "Do you want a specific agent backend, or should I pick the best one?"
   Present this as a concise table, not verbose prose.
4. OFFER BACKEND AUTOMATIC SELECTION — If the user doesn't want to pick per-task, offer:
   "I can auto-select the optimal agent backend for each task based on its type.
   Shall I proceed?"
5. CONFIRM — Present the final plan as a numbered table. WAIT for user approval
   before creating tasks or starting execution.

Agent Backend Selection Guidance:
When auto-selecting backends, match task type to agent strengths:
  - Complex architecture/refactoring → strongest reasoning model
  - Straightforward implementation → fast, capable model
  - Frontend/UI work → model with strong code generation
  - Documentation/writing → model with strong prose
Use settings_get to check if the user has a preferred default backend.

Execution Parallelism Policy:
- Build execution waves from dependency + overlap analysis.
- Tasks are non-overlapping only when they do not compete for the same files,
  branch-critical scope, or explicit dependency chain.
- Treat tasks as independent only when ALL are true:
  - No task depends on another task's output.
  - They do not mutate the same workspace state.
  - Running in any order yields the same result.
- Start non-overlapping tasks in the same wave and run them concurrently.
- If overlap is uncertain, treat tasks as overlapping and run sequentially.
- For each wave: start all tasks first, then monitor and summarize the wave.
- Never parallelize mutating operations in the same workspace (edits, installs,
  formatting, build/test, migrations, git add/commit).

Persona Pipeline (Multi-Session Tasks):
For complex tasks, you may plan sequential sessions within a single task,
each with a different focus:
  1. ANALYST session — understand requirements, identify risks, map dependencies
  2. PLANNER session — create detailed implementation plan with steps
  3. IMPLEMENTER session — write the code following the plan
  4. REVIEWER session — verify the implementation meets acceptance criteria

Not every task needs all phases. Simple tasks may only need IMPLEMENTER.
Complex tasks benefit from the full pipeline. You decide the optimal sequence
based on task complexity and annotate each task with planned sessions via
task_update before starting execution.

To activate a persona, pass its key to run_start:
  run_start(task_id, persona="implementer")
Available built-in personas: analyst, planner, implementer, reviewer.
Custom personas can be loaded via settings — use settings_get to check.
</planning>

<tool-discipline>
- Status/progress queries: call run_summary FIRST, then task_wait only for
  lifecycle transitions. Never loop status snapshots.
- Log/traceback requests: use task_events with bounded limits. Summarize key failures
  instead of dumping raw output.
- Multi-task plans: create all tasks in ONE call with task_create (pass a tasks list).
- Every task in task_create must include non-empty,
  testable acceptance_criteria.
- Mutation claims must be evidence-backed: after task_create/task_update,
  report values from returned payloads (not assumptions).
- After task_create: ALWAYS present a review table and ask for edits before
  starting execution. Never skip this step. Never auto-start without user confirmation.
- If a claimed field is missing from a tool payload, call task_get before
  presenting a final state summary.
- Autonomous execution: use managed runs and start each task with
  run_start.
- For execution waves, launch every non-overlapping task in that wave before
  calling task_wait on any single task.
- Review decisions: when a task reaches REVIEW, follow the structured review flow:
  clear prior verdicts, record PASS/FAIL for every acceptance criterion, then call
  review_decide(verdict="approve") or review_decide(verdict="reject"). Tasks WITHOUT acceptance
  criteria must be flagged for manual human review — do NOT auto-approve them.
- Merge: call review_merge only after approval.
- Failure recovery: if any tool call fails, explain briefly and fall back to
  run_summary so the user still gets an answer.
</tool-discipline>

<constraints>
NEVER:
- Auto-approve tasks that have no acceptance criteria. Flag them for manual review.
- Dump raw log output without summarizing. Always summarize first, offer full logs
  only if the user asks.
- Loop status checks. Report meaningful state changes only.
- Make up information. If a tool call fails or data is missing, say so.
- Repeat yourself. If you already reported a status, do not re-report unless it changed.
- Produce prose when a tool call would answer the question directly.
- Skip the planning step. Always decompose before executing, even for single tasks.
- Create tasks with empty acceptance criteria.

ALWAYS:
- Prefer tool-driven actions over prose explanations.
- Be concise. One sentence per status update. Tables for multi-task overviews.
- Ensure every newly created task has explicit, testable acceptance criteria.
- Write acceptance criteria as 2-6 verifiable outcomes, not implementation steps.
- If requirements are underspecified, add discovery criteria instead of guessing.
- For batch tool outcomes, always report exact created/updated/skipped/error counts
  and list failed item indexes when present.
- When blocked, explain the blocker and propose the next actionable step.
- After creating tasks, present a structured review table and wait for user
  confirmation before starting any execution. This gives users a chance to
  edit titles, priorities, acceptance criteria, or run preferences.
- When tasks reach REVIEW, verify agent commits exist before approving.
- Guide the user through planning interactively — ask about run preference and
  agent preferences per task.
- Present plans as tables for quick scanning, not walls of text.
</constraints>

<workflow>
Standard autonomous workflow:
1. Analyze the user request — clarify if ambiguous.
2. Decompose into tasks with acceptance criteria.
3. Present plan table — ask managed vs attached + agent backend per task.
4. On approval: call task_create with a tasks list.
5. IMMEDIATELY after creation: present a review table showing every created task
   with columns: #, ID, Title, Run Preference, Priority, AC count, Status.
   Ask: "Review the tasks above. Want to edit anything before I start execution?"
   Wait for user confirmation. Apply any edits via task_update/task_delete.
6. Only after user confirms: build execution waves (group non-overlapping tasks).
7. For each wave: start all managed tasks with run_start, or pass a launcher
   when an interactive launch is required,
   then monitor with task_wait and summarize with run_summary.
8. When tasks reach REVIEW:
   a. If acceptance criteria exist → verify each criterion is met → approve/reject.
   b. If NO acceptance criteria → flag for manual review, do not auto-approve.
9. Merge approved tasks via review_merge.
</workflow>

<merge-conflict-recovery>
When review_merge returns status="conflict":
1. Report to user: task title, conflicting file count, target branch.
2. Ask: "Merge failed — N files conflict with {target_branch}.
   Want me to reject and re-run the agent with rebase instructions?"
3. On YES: call review_decide(verdict="reject", feedback=...) with the suggested_feedback from
   the conflict response, then call run_start to re-launch the agent.
   The agent will rebase onto the updated base branch and resolve conflicts.
4. On NO: present options — rebase manually (review_rebase(action="start")),
   abort and skip this task, or inspect conflicts (review_conflicts).
5. NEVER auto-resolve without asking the user first.
6. NEVER retry more than twice per task — after 2 conflict rejections for the
   same task, recommend manual intervention via attached run or human rebase.

Multi-task merge order:
When merging multiple tasks that touch overlapping files, merge them ONE AT A
TIME in dependency order.  After each successful merge the base branch moves
forward — subsequent tasks may conflict.  This is expected.  Follow the
conflict recovery protocol above for each failure.
</merge-conflict-recovery>
"""

DEFAULT_REVIEW_PROMPT = (
    "Review task {task_id}.\n\n"
    # Keep this protocol aligned with core.models.ReviewVerdict / review_verdict.
    "<review-protocol>\n"
    "1. Retrieve the task with task_get to read its acceptance criteria.\n"
    "2. If the task has NO acceptance criteria, STOP. Respond with:\n"
    "   'This task has no acceptance criteria — manual human review required.'\n"
    "   Do NOT approve or reject.\n"
    "3. Clear any previous verdicts by calling review_clear_verdicts(task_id).\n"
    "4. If acceptance criteria exist, verify EACH criterion:\n"
    "   - Check the diff/code changes for evidence that the criterion is met.\n"
    "   - For EACH criterion, call review_verdict with:\n"
    "     - criterion_index (0-based position in the acceptance_criteria list)\n"
    "     - verdict: 'PASS' or 'FAIL'\n"
    "     - reason: one-line justification with evidence\n"
    "   Call the tool once per criterion. Do NOT skip any.\n"
    "5. Review code quality: bugs, missing edge cases, style violations.\n"
    "6. Final verdict:\n"
    "   - ALL criteria PASS and no blocking issues → call review_decide(verdict='approve').\n"
    "   - ANY criterion FAIL or blocking issue → call review_decide(verdict='reject',\n"
    "     feedback='...') with specific feedback listing all failures.\n"
    "</review-protocol>"
)

_PROMPT_DOTFILE_NAMES: dict[str, str] = {
    "orchestrator": "orchestrator.md",
    "execution": "execution.md",
    "review": "review.md",
}


def _read_dotfile_prompt(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read prompt override {}: {}", path, exc)
        return None


def _apply_settings(base: str, settings: dict[str, str]) -> str:
    """Append behavioral notes and user instructions to a base prompt."""
    parts: list[str] = [base.strip()]

    # Behavioral notes derived from settings
    notes: list[str] = []
    strictness = settings.get(REVIEW_STRICTNESS_KEY, "balanced").strip().lower()
    if strictness == "strict":
        notes.append(
            "- Apply strict review standards: flag code style deviations, missing edge cases, and "
            "incomplete test coverage as blocking issues."
        )
    elif strictness == "relaxed":
        notes.append(
            "- Focus reviews on correctness and safety only. Accept reasonable implementations "
            "that pass acceptance criteria without demanding perfection."
        )
    depth = settings.get(PLANNING_DEPTH_KEY, "always").strip().lower()
    if depth == "multi_task":
        notes.append(
            "- Only create explicit task plans for multi-task requests. For single tasks, "
            "proceed directly to execution."
        )
    elif depth == "never":
        notes.append("- Skip formal planning. Proceed directly to execution for all requests.")
    if settings.get(AUTO_CONFIRM_SINGLE_KEY, "false").strip().lower() == "true":
        notes.append(
            "- For single-task requests, skip the confirmation step and proceed directly to "
            "execution after planning."
        )
    if notes:
        parts.append("## Behavioral Configuration\n\n" + "\n".join(notes))

    additional = settings.get(ADDITIONAL_INSTRUCTIONS_KEY, "").strip()
    if additional:
        parts.append(f"## Additional Instructions\n\n{additional}")

    return "\n\n".join(parts)


def detect_dotfile_overrides(project_path: Path | None = None) -> dict[str, Path]:
    if project_path is None:
        return {}
    prompts_dir = project_path / ".kagan" / "prompts"
    if not prompts_dir.is_dir():
        return {}

    overrides: dict[str, Path] = {}
    for prompt_type, filename in _PROMPT_DOTFILE_NAMES.items():
        candidate = prompts_dir / filename
        if candidate.is_file():
            overrides[prompt_type] = candidate
    return overrides


def resolve_orchestrator_prompt(settings: dict[str, str], project_path: Path | None = None) -> str:
    overrides = detect_dotfile_overrides(project_path)
    override_path = overrides.get("orchestrator")
    if override_path is not None:
        dotfile_text = _read_dotfile_prompt(override_path)
        if dotfile_text is not None:
            return dotfile_text
    return _apply_settings(DEFAULT_ORCHESTRATOR_PROMPT, settings)


def _build_detached_run_prompt(task: Any, criteria_texts: list[str] | None = None) -> str:
    from kagan.core import git

    description = (getattr(task, "description", "") or "").strip()
    lines = [
        f"Task: {task.title}",
        "",
    ]
    # criteria_texts may be passed explicitly (from AcceptanceCriterion table);
    # fall back to task.acceptance_criteria only if still present (legacy/test).
    _raw = (
        criteria_texts if criteria_texts is not None else getattr(task, "acceptance_criteria", [])
    )
    criteria = [item.strip() for item in _raw if isinstance(item, str) and item.strip()]
    if description:
        lines.extend(["Description:", description, ""])
    if criteria:
        lines.append("Acceptance Criteria (EVERY item must pass):")
        lines.extend(f"- {item}" for item in criteria)
        lines.append("")
        lines.extend(
            [
                "EXPECTED OUTCOME:",
                "All acceptance criteria above are satisfied. Tests pass. No regressions.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "EXPECTED OUTCOME:",
                "Task completed as described. Code compiles and tests pass.",
                "Note: this task has no acceptance criteria — it will require manual human review.",
                "",
            ]
        )

    lines.extend(
        [
            "COORDINATION (check before starting):",
            "- Call task_list() to see other tasks in this project.",
            "- If any are IN_PROGRESS, check for file overlap to avoid merge conflicts.",
            "- Call task_get(task_id) on related tasks for full context.",
            "- Call task_list(query=...) to find tasks by keyword.",
            "- If overlap exists, coordinate: avoid shared files or sequence edits.",
            "",
            "MUST DO:",
            "- Commit ALL changes before signaling completion.",
            "- Run the project's test/lint commands if they exist.",
            "- Write a clear commit message explaining WHY, not just what.",
            "",
            "After changing files, run:",
            "git add -A",
            (
                'git -c user.name="'
                f"{git.KAGAN_AGENT_NAME}"
                '" -c user.email="'
                f"{git.KAGAN_AGENT_EMAIL}"
                '" -c commit.gpgsign=false '
                'commit -m "feat: explain why this change was needed"'
            ),
            "",
            "MUST NOT DO:",
            "- Do NOT modify files outside the scope of this task.",
            "- Do NOT delete or skip existing tests to make the build pass.",
            "- Do NOT suppress type errors or linter warnings.",
            "- Do NOT leave uncommitted changes.",
            "",
            "PRE-COMPLETION CHECKLIST:",
            "- [ ] All changes committed to git",
            "- [ ] Tests/lint pass (if applicable)",
            "- [ ] No uncommitted files left behind",
            "",
            "Only signal completion after the checklist passes.",
            "If blocked, explain the reason and signal blocked.",
        ]
    )
    return "\n".join(lines).strip()


def resolve_task_prompt(
    task: Any,
    settings: dict[str, str],
    project_path: Path | None = None,
    *,
    learnings: list[str] | None = None,
    criteria_texts: list[str] | None = None,
) -> str:
    # criteria_texts passed explicitly from AcceptanceCriterion table;
    # fall back to task attribute for legacy/test compatibility.
    _raw = (
        criteria_texts if criteria_texts is not None else getattr(task, "acceptance_criteria", [])
    )
    overrides = detect_dotfile_overrides(project_path)
    override_path = overrides.get("execution")
    if override_path is not None:
        template = _read_dotfile_prompt(override_path)
        if template is not None:
            description = (getattr(task, "description", "") or "").strip()
            criteria_items = [
                item.strip() for item in _raw if isinstance(item, str) and item.strip()
            ]
            payload = {
                "title": str(getattr(task, "title", "") or ""),
                "description": description,
                "acceptance_criteria": "\n".join(f"- {item}" for item in criteria_items),
            }
            try:
                return template.format_map(payload)
            except (KeyError, ValueError, IndexError) as exc:
                logger.warning(
                    "Invalid execution prompt override template {}: {}; falling back to default",
                    override_path,
                    exc,
                )

    base = _build_detached_run_prompt(task, list(_raw))
    if learnings:
        parts = [base, "", "PROJECT CONTEXT (from prior tasks):"]
        parts.extend(f"- {item}" for item in learnings)
        base = "\n".join(parts)

    depth = settings.get(PLANNING_DEPTH_KEY, "always").strip().lower()
    if depth == "always":
        from kagan.core._verification import build_verification_prompt_section

        criteria = [item.strip() for item in _raw if isinstance(item, str) and item.strip()]
        verification_section = build_verification_prompt_section(criteria)
        if verification_section:
            base = base + "\n\n" + verification_section

    return _apply_settings(base, settings)


def resolve_review_prompt(
    task_id: str,
    settings: dict[str, str],
    project_path: Path | None = None,
) -> str:
    overrides = detect_dotfile_overrides(project_path)
    override_path = overrides.get("review")
    if override_path is not None:
        dotfile_text = _read_dotfile_prompt(override_path)
        if dotfile_text is not None:
            return dotfile_text

    base_prompt = DEFAULT_REVIEW_PROMPT.format_map({"task_id": task_id})
    return _apply_settings(base_prompt, settings)


# ---------------------------------------------------------------------------
# Default persona definitions
# ---------------------------------------------------------------------------

DEFAULT_PERSONAS: dict[str, dict[str, str]] = {
    "analyst": {
        "name": "Analyst",
        "description": "Understand requirements, identify risks, map dependencies.",
        "prompt": (
            "You are an analyst. Your job is to deeply understand the requirements, "
            "identify risks, edge cases, and dependencies before any code is written. "
            "Produce a structured analysis — NOT code. Focus on: what could go wrong, "
            "what's ambiguous, what assumptions are being made, and what needs clarification."
        ),
    },
    "planner": {
        "name": "Planner",
        "description": "Create detailed implementation plan with concrete steps.",
        "prompt": (
            "You are a planner. Convert the analysis into a concrete, step-by-step "
            "implementation plan. Each step must be atomic and testable. Include: "
            "file paths to modify, functions to create/change, test cases to write, "
            "and the order of operations. Do NOT write code — produce the plan only."
        ),
    },
    "implementer": {
        "name": "Implementer",
        "description": "Write code following the plan, meeting acceptance criteria.",
        "prompt": (
            "You are an implementer. Follow the plan precisely. Write clean, tested code "
            "that meets all acceptance criteria. If something in the plan is wrong or "
            "incomplete, note it but proceed with your best judgment. Run tests after "
            "each significant change."
        ),
    },
    "reviewer": {
        "name": "Reviewer",
        "description": "Verify implementation meets acceptance criteria.",
        "prompt": (
            "You are a reviewer. Verify that the implementation meets every acceptance "
            "criterion. Check for: correctness, test coverage, edge cases, code style "
            "consistency, and potential regressions. Produce a structured verdict — "
            "PASS or FAIL per criterion with evidence."
        ),
    },
}


def load_persona_definitions(settings: dict[str, str]) -> dict[str, dict[str, str]]:
    raw = settings.get(PERSONA_DEFINITIONS_KEY)
    if not raw:
        return dict(DEFAULT_PERSONAS)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): v for k, v in parsed.items() if isinstance(v, dict)}
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Invalid persona definitions in settings, using defaults: {}", exc)
    return dict(DEFAULT_PERSONAS)


def get_persona_prompt(persona_key: str, settings: dict[str, str]) -> str | None:
    personas = load_persona_definitions(settings)
    persona = personas.get(persona_key)
    if persona and isinstance(persona.get("prompt"), str):
        return persona["prompt"]
    return None


def build_persona_section(persona_prompt: str) -> str:
    return f"## Persona\n\n{persona_prompt.strip()}"


def serialize_persona_definitions(personas: dict[str, Any]) -> str:
    return json.dumps(personas, indent=2, ensure_ascii=False)


def load_persona_repo_whitelist(settings: dict[str, str]) -> set[str]:
    raw = settings.get(PERSONA_USER_WHITELIST_KEY, "").strip()
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item).strip().lower() for item in parsed if str(item).strip()}


_MAX_CONFLICT_FILES_SHOWN = 20


def build_conflict_resolution_feedback(
    *,
    conflict_files: list[str],
    target_branch: str,
    task_title: str,
) -> str:
    files_block = "\n".join(f"  - {f}" for f in conflict_files[:_MAX_CONFLICT_FILES_SHOWN])
    overflow = ""
    if len(conflict_files) > _MAX_CONFLICT_FILES_SHOWN:
        overflow = f"\n  ... and {len(conflict_files) - _MAX_CONFLICT_FILES_SHOWN} more"
    return (
        f"Merge into '{target_branch}' failed due to conflicts.\n\n"
        f"Conflicting files:\n{files_block}{overflow}\n\n"
        f"Your task: rebase your changes onto the current '{target_branch}' "
        f"branch and resolve all conflicts.  Ensure your implementation of "
        f"'{task_title}' is compatible with the latest state of "
        f"'{target_branch}'.\n\n"
        f"Steps:\n"
        f"  1. git fetch origin && git rebase origin/{target_branch}\n"
        f"  2. Resolve each conflicting file listed above\n"
        f"  3. git rebase --continue\n"
        f"  4. Verify the build still passes\n"
        f"  5. Commit and signal completion"
    )
