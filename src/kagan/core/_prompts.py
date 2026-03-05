"""Prompt customization — setting keys, default personas, injection helpers.

Private module. Public surface re-exported from ``kagan.core.__init__``.
"""

import json
from typing import Any

# ---------------------------------------------------------------------------
# Setting keys for prompt customization
# ---------------------------------------------------------------------------

PROMPT_ORCHESTRATOR_KEY = "custom_orchestrator_prompt"
PROMPT_TASK_KEY = "custom_task_prompt"
PROMPT_REVIEW_KEY = "custom_review_prompt"
PERSONA_DEFINITIONS_KEY = "persona_definitions"
PERSONA_USER_WHITELIST_KEY = "persona_repo_whitelist"

# ---------------------------------------------------------------------------
# Default persona definitions (OMO-inspired pipeline phases)
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


# ---------------------------------------------------------------------------
# Persona loading
# ---------------------------------------------------------------------------


def load_persona_definitions(settings: dict[str, str]) -> dict[str, dict[str, str]]:
    """Load persona definitions from settings, falling back to defaults."""
    raw = settings.get(PERSONA_DEFINITIONS_KEY)
    if not raw:
        return dict(DEFAULT_PERSONAS)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): v for k, v in parsed.items() if isinstance(v, dict)}
    except (json.JSONDecodeError, TypeError):
        pass
    return dict(DEFAULT_PERSONAS)


def get_persona_prompt(persona_key: str, settings: dict[str, str]) -> str | None:
    """Get the system prompt for a named persona, or None if not found."""
    personas = load_persona_definitions(settings)
    persona = personas.get(persona_key)
    if persona and isinstance(persona.get("prompt"), str):
        return persona["prompt"]
    return None


# ---------------------------------------------------------------------------
# Prompt injection helpers
# ---------------------------------------------------------------------------


def prepend_custom_prompt(base_prompt: str, custom: str | None) -> str:
    """Prepend a custom prompt section to a base prompt if provided."""
    if not custom or not custom.strip():
        return base_prompt
    return f"## Custom Instructions\n\n{custom.strip()}\n\n{base_prompt}"


def build_persona_section(persona_prompt: str) -> str:
    """Format a persona prompt as a section to prepend to agent prompts."""
    return f"## Persona\n\n{persona_prompt.strip()}"


def inject_settings_prompt(
    base_prompt: str,
    settings: dict[str, str],
    setting_key: str,
) -> str:
    """Check settings for a custom prompt override and prepend it if present."""
    custom = settings.get(setting_key, "").strip()
    return prepend_custom_prompt(base_prompt, custom if custom else None)


def serialize_persona_definitions(personas: dict[str, Any]) -> str:
    """Serialize persona definitions to JSON for storage in settings."""
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


# ---------------------------------------------------------------------------
# Conflict resolution feedback
# ---------------------------------------------------------------------------


_MAX_CONFLICT_FILES_SHOWN = 20


def build_conflict_resolution_feedback(
    *,
    conflict_files: list[str],
    target_branch: str,
    task_title: str,
) -> str:
    """Build agent feedback for resolving merge conflicts with the base branch.

    Returns a structured instruction string suitable for ``reject(feedback=...)``
    or direct agent prompting.  Pure function — no IO, no side effects.
    """
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
