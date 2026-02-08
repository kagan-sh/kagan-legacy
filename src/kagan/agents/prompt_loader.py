"""Prompt templates for Kagan agents loaded from markdown resources."""

from __future__ import annotations

from functools import cache
from importlib.resources import files


@cache
def _load_prompt_template(filename: str) -> str:
    """Load a prompt template from package resources."""
    return (files("kagan.agents.prompts") / filename).read_text(encoding="utf-8")


RUN_PROMPT = _load_prompt_template("run_prompt.md")
REVIEW_PROMPT = _load_prompt_template("review_prompt.md")


def get_review_prompt(
    title: str,
    task_id: str,
    description: str,
    commits: str,
    diff_summary: str,
) -> str:
    """Get formatted review prompt."""
    return REVIEW_PROMPT.format(
        title=title,
        task_id=task_id,
        description=description,
        commits=commits,
        diff_summary=diff_summary,
    )
