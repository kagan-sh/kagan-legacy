"""Lightweight GitHub context resolver for task cards.

Provides synchronous lookups of issue# and PR# from already-loaded repo scripts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core.plugins.github.domain.repo_state import (
    load_issue_mapping_state,
    load_pr_mapping_state,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def resolve_github_context(
    task_id: str,
    repos_scripts: list[Mapping[str, object] | None],
) -> tuple[int | None, int | None]:
    """Resolve GitHub issue number and PR number for a task.

    Scans through all repo scripts dicts to find mappings for the given task_id.
    Returns (issue_number, pr_number). Both may be None if no mapping exists.

    Args:
        task_id: The Kagan task ID to look up.
        repos_scripts: List of Repo.scripts dicts (one per repo in the project).

    Returns:
        Tuple of (issue_number | None, pr_number | None).
    """
    issue_number: int | None = None
    pr_number: int | None = None

    for scripts in repos_scripts:
        if not scripts:
            continue

        if issue_number is None:
            mapping = load_issue_mapping_state(scripts)
            issue_number = mapping.get_issue_number(task_id)

        if pr_number is None:
            pr_mapping = load_pr_mapping_state(scripts)
            pr_link = pr_mapping.get_pr(task_id)
            if pr_link is not None:
                pr_number = pr_link.pr_number

        if issue_number is not None and pr_number is not None:
            break

    return issue_number, pr_number


def build_github_context_index(
    task_ids: set[str],
    repos_scripts: list[Mapping[str, object] | None],
) -> dict[str, tuple[int | None, int | None]]:
    """Build a batch index of GitHub context for multiple tasks.

    More efficient than calling resolve_github_context per-task when
    rendering many cards, as it parses each repo's scripts only once.

    Args:
        task_ids: Set of task IDs to look up.
        repos_scripts: List of Repo.scripts dicts.

    Returns:
        Dict mapping task_id -> (issue_number | None, pr_number | None).
    """
    issue_map: dict[str, int] = {}
    pr_map: dict[str, int] = {}

    for scripts in repos_scripts:
        if not scripts:
            continue

        mapping = load_issue_mapping_state(scripts)
        for tid in task_ids:
            if tid not in issue_map:
                issue_num = mapping.get_issue_number(tid)
                if issue_num is not None:
                    issue_map[tid] = issue_num

        pr_mapping = load_pr_mapping_state(scripts)
        for tid in task_ids:
            if tid not in pr_map:
                pr_link = pr_mapping.get_pr(tid)
                if pr_link is not None:
                    pr_map[tid] = pr_link.pr_number

    return {
        tid: (issue_map.get(tid), pr_map.get(tid))
        for tid in task_ids
        if tid in issue_map or tid in pr_map
    }


__all__ = [
    "build_github_context_index",
    "resolve_github_context",
]
