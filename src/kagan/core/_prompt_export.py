"""Export resolved prompts to GitHub Models .prompt.yml format.

Private module. Called by ``kagan.cli.prompts``.
"""

from pathlib import Path
from textwrap import indent
from types import SimpleNamespace
from typing import Any

from loguru import logger

from kagan.core._prompts import (
    resolve_orchestrator_prompt,
    resolve_review_prompt,
    resolve_task_prompt,
)

PROMPT_TYPES = ("orchestrator", "execution", "review")

_PLACEHOLDER_TASK = SimpleNamespace(
    title="Example task",
    description="Placeholder task for prompt export preview.",
    acceptance_criteria=["Tests pass", "No regressions"],
)


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
    content = _resolve(prompt_type, settings, task=task, task_id=task_id, project_path=project_path)
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
    return _resolve(prompt_type, settings, task=task, task_id=task_id, project_path=project_path)


def write_prompt_file(content: str, output_path: Path) -> Path:
    """Write exported prompt content to *output_path* and return the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.debug("Wrote prompt file to {}", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve(
    prompt_type: str,
    settings: dict[str, str],
    *,
    task: Any | None = None,
    task_id: str | None = None,
    project_path: Path | None = None,
) -> str:
    """Validate *prompt_type* and resolve through the three-layer pipeline."""
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(
            f"Unknown prompt type {prompt_type!r}. Choose from: {', '.join(PROMPT_TYPES)}"
        )

    if prompt_type == "orchestrator":
        return resolve_orchestrator_prompt(settings, project_path)
    if prompt_type == "execution":
        return resolve_task_prompt(task or _PLACEHOLDER_TASK, settings, project_path)
    return resolve_review_prompt(task_id or "TASK_ID_PLACEHOLDER", settings, project_path)


_YAML_MUST_QUOTE = frozenset(":#{}[]&*?|>=!%@`\"'")


def _yaml_quote(value: str) -> str:
    """Quote a YAML scalar value if it contains characters that need quoting.

    Hyphens, slashes, dots, and angle brackets in isolation are safe in YAML
    plain scalars. We only quote when truly ambiguous characters appear.
    """
    if _YAML_MUST_QUOTE.intersection(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _format_yml(*, name: str, description: str, model: str, content: str) -> str:
    """Build a .prompt.yml string without a YAML library.

    Header scalars are quoted to prevent YAML injection via special characters.
    The content field uses a block scalar (``|``) which is safe by construction.
    """
    indented = indent(content, "        ")
    return (
        f"name: {_yaml_quote(name)}\n"
        f"description: {_yaml_quote(description)}\n"
        f"model: {_yaml_quote(model)}\n"
        f"messages:\n"
        f"  - role: system\n"
        f"    content: |\n"
        f"{indented}\n"
    )
