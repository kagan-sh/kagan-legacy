"""Prompt snapshot tests — CI-breaking regression detection.

Any change to _build_detached_run_prompt template text causes these tests to FAIL.
Developers must consciously update the expected strings when changing prompts.
"""

import types

import pytest

from kagan.core._prompts import _build_detached_run_prompt, resolve_task_prompt
from kagan.core.git import KAGAN_AGENT_EMAIL, KAGAN_AGENT_NAME

pytestmark = [pytest.mark.unit]


def _make_task(
    title: str,
    description: str = "",
    acceptance_criteria: list[str] | None = None,
) -> object:
    return types.SimpleNamespace(
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria or [],
    )


# ── Exact snapshot helpers ────────────────────────────────────────────────────

_GIT_COMMIT_LINE = (
    f'git -c user.name="{KAGAN_AGENT_NAME}" -c user.email="{KAGAN_AGENT_EMAIL}"'
    ' -c commit.gpgsign=false commit -m "feat: explain why this change was needed"'
)

_SHARED_TAIL = "\n".join(
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
        _GIT_COMMIT_LINE,
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


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_detached_run_prompt_with_acceptance_criteria() -> None:
    """Exact snapshot: task with description + acceptance criteria."""
    task = _make_task(
        title="Fix the login bug",
        description="Users cannot log in with + in emails.",
        acceptance_criteria=["Login with user+test@example.com works", "Existing tests pass"],
    )
    result = _build_detached_run_prompt(task)

    expected = "\n".join(
        [
            "Task: Fix the login bug",
            "",
            "Description:",
            "Users cannot log in with + in emails.",
            "",
            "Acceptance Criteria (EVERY item must pass):",
            "- Login with user+test@example.com works",
            "- Existing tests pass",
            "",
            "EXPECTED OUTCOME:",
            "All acceptance criteria above are satisfied. Tests pass. No regressions.",
            "",
            _SHARED_TAIL,
        ]
    )
    assert result == expected


def test_detached_run_prompt_without_acceptance_criteria() -> None:
    """Exact snapshot: task with no description and no acceptance criteria."""
    task = _make_task(title="Refactor settings module")
    result = _build_detached_run_prompt(task)

    expected = "\n".join(
        [
            "Task: Refactor settings module",
            "",
            "EXPECTED OUTCOME:",
            "Task completed as described. Code compiles and tests pass.",
            "Note: this task has no acceptance criteria — it will require manual human review.",
            "",
            _SHARED_TAIL,
        ]
    )
    assert result == expected


def test_detached_run_prompt_description_only() -> None:
    """Exact snapshot: task with description but no acceptance criteria."""
    task = _make_task(
        title="Update config",
        description="Move settings to environment variables.",
    )
    result = _build_detached_run_prompt(task)

    expected = "\n".join(
        [
            "Task: Update config",
            "",
            "Description:",
            "Move settings to environment variables.",
            "",
            "EXPECTED OUTCOME:",
            "Task completed as described. Code compiles and tests pass.",
            "Note: this task has no acceptance criteria — it will require manual human review.",
            "",
            _SHARED_TAIL,
        ]
    )
    assert result == expected


def test_detached_run_prompt_key_phrases_present() -> None:
    """Structural regression guard: key phrases must all be present."""
    task = _make_task(
        title="Add unit test",
        acceptance_criteria=["Test passes"],
    )
    result = _build_detached_run_prompt(task)

    required_phrases = [
        "COORDINATION (check before starting):",
        "task_list()",
        "IN_PROGRESS",
        "MUST DO:",
        "Commit ALL changes before signaling completion",
        "test/lint",
        "WHY-focused",
        "git add -A",
        "commit.gpgsign=false",
        "MUST NOT DO:",
        "Do NOT modify files outside this task's scope.",
        "Do NOT delete or skip existing tests to make the build pass.",
        "Do NOT suppress type errors or linter warnings.",
        "PRE-COMPLETION CHECKLIST:",
        "All changes committed to git",
        "Signal completion only after the checklist passes",
        "If blocked",
    ]
    for phrase in required_phrases:
        assert phrase in result, f"Missing required phrase: {phrase!r}"


def test_resolve_task_prompt_with_learnings() -> None:
    """Learnings inject PROJECT CONTEXT section after base prompt."""
    task = _make_task(title="Write documentation")
    learnings = ["Always run poe check before committing", "Use loguru for logging"]
    result = resolve_task_prompt(task, settings={}, learnings=learnings)

    assert "PROJECT CONTEXT (from prior tasks):" in result
    assert "- Always run poe check before committing" in result
    assert "- Use loguru for logging" in result
    # Base prompt content still present
    assert "Task: Write documentation" in result
    assert "MUST DO:" in result


def test_resolve_task_prompt_no_learnings() -> None:
    """Empty or None learnings don't inject the PROJECT CONTEXT section."""
    task = _make_task(title="Write documentation")
    result_none = resolve_task_prompt(task, settings={}, learnings=None)
    result_empty = resolve_task_prompt(task, settings={}, learnings=[])

    assert "PROJECT CONTEXT" not in result_none
    assert "PROJECT CONTEXT" not in result_empty
