"""Prompt resolution, behavioral settings, and persona helpers.

Private module. Public surface re-exported from ``kagan.core.__init__``.
"""

import importlib.resources
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


def _load_orchestrator_prompt() -> str:
    """Load the orchestrator system prompt from package data."""
    try:
        pkg = importlib.resources.files("kagan.core._prompts")
        return pkg.joinpath("orchestrator.md").read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, AttributeError) as exc:
        logger.warning("Could not load orchestrator.md from package data: {}", exc)
        return ""


DEFAULT_ORCHESTRATOR_PROMPT: str = _load_orchestrator_prompt()

DEFAULT_REVIEW_PROMPT = (
    "Review task {task_id}.\n\n"
    # Keep aligned with core.models.ReviewVerdict / review_verdict.
    "<review-protocol>\n"
    "1. `task_get` for acceptance criteria. None → respond "
    "'This task has no acceptance criteria — manual human review required.' "
    "and STOP (do not approve/reject).\n"
    "2. `review_clear_verdicts(task_id)`.\n"
    "3. For EACH criterion (0-based index): `review_verdict(criterion_index, "
    "verdict='PASS'|'FAIL', reason=<one-line evidence from the diff>)`. Skip none.\n"
    "4. Also flag bugs, missing edge cases, blocking style issues.\n"
    "5. All PASS + no blockers → `review_decide(verdict='approve')`. "
    "Any FAIL or blocker → `review_decide(verdict='reject', feedback=<failures>)`.\n"
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
            "- `task_list()` for siblings; check IN_PROGRESS for file overlap.",
            "- `task_get(task_id)` / `task_list(query=...)` for context.",
            "- On overlap: avoid shared files or sequence edits.",
            "",
            "MUST DO:",
            "- Commit ALL changes before signaling completion (WHY-focused message).",
            "- Run project test/lint commands if present.",
            "",
            "After edits:",
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
            "- Do NOT modify files outside this task's scope.",
            "- Do NOT delete or skip existing tests to make the build pass.",
            "- Do NOT suppress type errors or linter warnings.",
            "- Do NOT leave uncommitted changes.",
            "",
            "PRE-COMPLETION CHECKLIST:",
            "- [ ] All changes committed to git",
            "- [ ] Tests/lint pass (if applicable)",
            "- [ ] No uncommitted files left behind",
            "",
            "Signal completion only after the checklist passes. If blocked, "
            "explain the reason and signal blocked.",
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
