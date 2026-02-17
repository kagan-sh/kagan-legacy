"""Resolve GitHub context for a task from repo scripts (read-only, no API calls)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kagan.core.plugins.github.domain.repo_state import (
    load_connection_state,
    load_issue_mapping_state,
    load_pr_mapping_state,
    resolve_owner_repo,
)

if TYPE_CHECKING:
    from kagan.core.adapters.db.schema import Repo
    from kagan.core.plugins.github.sync import TaskPRLink


@dataclass(frozen=True, slots=True)
class GitHubTaskContext:
    """Read-only GitHub context resolved for a single task."""

    connected: bool = False
    repo_full_name: str = ""
    issue_number: int | None = None
    pr_link: TaskPRLink | None = None


def resolve_github_context(
    repos: list[Repo],
    task_id: str,
) -> GitHubTaskContext:
    """Resolve GitHub context for a task from project repos.

    Reads from Repo.scripts dicts only — no network calls.
    Returns the first connected repo's context for the task.
    """
    for repo in repos:
        scripts = repo.scripts
        conn_state = load_connection_state(scripts)
        if conn_state.normalized is None:
            continue

        owner_repo = resolve_owner_repo(conn_state.normalized)
        full_name = f"{owner_repo[0]}/{owner_repo[1]}" if owner_repo else ""

        issue_mapping = load_issue_mapping_state(scripts)
        issue_number = issue_mapping.get_issue_number(task_id)

        pr_mapping = load_pr_mapping_state(scripts)
        pr_link = pr_mapping.get_pr(task_id)

        return GitHubTaskContext(
            connected=True,
            repo_full_name=full_name,
            issue_number=issue_number,
            pr_link=pr_link,
        )

    return GitHubTaskContext()


def format_github_context(ctx: GitHubTaskContext) -> list[str]:
    """Format GitHub context into display lines."""
    if not ctx.connected:
        return ["Not connected — use repo actions to connect"]

    lines: list[str] = []

    if ctx.repo_full_name:
        lines.append(f"Repository: {ctx.repo_full_name} (connected)")

    if ctx.issue_number is not None:
        lines.append(f"Issue: #{ctx.issue_number}")
    else:
        lines.append("No linked issue")

    if ctx.pr_link is not None:
        pr = ctx.pr_link
        state_label = pr.pr_state.lower()
        branch_label = pr.head_branch or ""
        parts = [f"PR: #{pr.pr_number}"]
        if state_label:
            parts.append(f"({state_label})")
        if branch_label:
            parts.append(f"— {branch_label}")
        lines.append(" ".join(parts))

    return lines


__all__ = [
    "GitHubTaskContext",
    "format_github_context",
    "resolve_github_context",
]
