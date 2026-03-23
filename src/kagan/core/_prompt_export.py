"""Export resolved prompts to GitHub Models .prompt.yml format.

Private module. Called by ``kagan.cli.prompts``.
"""

from pathlib import Path
from textwrap import indent
from typing import Any

from loguru import logger

from kagan.core._prompts import (
    resolve_orchestrator_prompt,
    resolve_review_prompt,
    resolve_task_prompt,
)

PROMPT_TYPES = ("orchestrator", "execution", "review")


def export_prompt_yml(
    prompt_type: str,
    settings: dict[str, str],
    *,
    task: Any | None = None,
    task_id: str | None = None,
    project_path: Path | None = None,
    model: str = "openai/gpt-4.1",
) -> str:
    """Resolve a Kagan prompt and serialize to .prompt.yml format.

    Returns the YAML content as a string.

    Raises ``ValueError`` if *prompt_type* is not one of ``PROMPT_TYPES``.
    """
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(
            f"Unknown prompt type {prompt_type!r}. Choose from: {', '.join(PROMPT_TYPES)}"
        )

    # Resolve using the existing three-layer pipeline
    if prompt_type == "orchestrator":
        content = resolve_orchestrator_prompt(settings, project_path)
    elif prompt_type == "execution":
        content = resolve_task_prompt(
            task or _placeholder_task(),
            settings,
            project_path,
        )
    else:  # review
        content = resolve_review_prompt(
            task_id or "TASK_ID_PLACEHOLDER",
            settings,
            project_path,
        )

    return _format_yml(
        name=f"kagan-{prompt_type}",
        description=f"Kagan {prompt_type} system prompt",
        model=model,
        content=content,
    )


def export_prompt_text(
    prompt_type: str,
    settings: dict[str, str],
    *,
    task: Any | None = None,
    task_id: str | None = None,
    project_path: Path | None = None,
) -> str:
    """Resolve a Kagan prompt and return the raw text.

    Unlike :func:`export_prompt_yml`, this returns the resolved prompt content
    without any YAML wrapper — suitable for piping into other tools.

    Raises ``ValueError`` if *prompt_type* is not one of ``PROMPT_TYPES``.
    """
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(
            f"Unknown prompt type {prompt_type!r}. Choose from: {', '.join(PROMPT_TYPES)}"
        )

    if prompt_type == "orchestrator":
        return resolve_orchestrator_prompt(settings, project_path)
    elif prompt_type == "execution":
        return resolve_task_prompt(
            task or _placeholder_task(),
            settings,
            project_path,
        )
    else:  # review
        return resolve_review_prompt(
            task_id or "TASK_ID_PLACEHOLDER",
            settings,
            project_path,
        )


def write_prompt_yml(content: str, output_path: Path) -> Path:
    """Write .prompt.yml content to *output_path* and return the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.debug("Wrote prompt file to {}", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_yml(*, name: str, description: str, model: str, content: str) -> str:
    """Build a .prompt.yml string without a YAML library.

    The format is intentionally simple — a YAML library would be overkill
    for a fixed structure with one multi-line string field.
    """
    # Indent every line of content by 8 spaces for the YAML block scalar
    indented = indent(content, "        ")
    return (
        f"name: {name}\n"
        f"description: {description}\n"
        f"model: {model}\n"
        f"messages:\n"
        f"  - role: system\n"
        f"    content: |\n"
        f"{indented}\n"
    )


def _placeholder_task() -> object:
    """Minimal stand-in when no real task is provided for execution export."""

    class _Placeholder:
        title = "Example task"
        description = "Placeholder task for prompt export preview."
        acceptance_criteria: list[str] = ["Tests pass", "No regressions"]

    return _Placeholder()
