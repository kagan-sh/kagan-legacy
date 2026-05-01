"""kagan.core.integrations.mentions — dual-source mention autocomplete.

Merges kagan tasks and GitHub issues for ``#``-mention typeahead.

Usage::

    from kagan.core.integrations.mentions import search_mentions, Mention

    results = await search_mentions(client, project_id, "#login", limit=10)
    # [Mention(source="kagan", id="kagan#abc12345", title="...", state="BACKLOG"), ...]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from loguru import logger

if TYPE_CHECKING:
    from kagan.core import KaganCore


@dataclass(frozen=True)
class Mention:
    """A single mention result from the dual-source typeahead backend."""

    source: Literal["kagan", "github"]
    id: str  # insert form: "kagan#abc12345" or "#42"
    title: str
    state: str | None = None  # task status for kagan, issue state for github


def _score_mention(query: str, mention: Mention) -> int:
    """Assign a sort score (lower = better match).

    0 = exact short-id / number match
    1 = prefix match on id / short-id
    2 = substring match on title
    """
    q = query.lower().lstrip("#")
    raw_id = mention.id.lstrip("#").replace("kagan#", "")

    if raw_id == q:
        return 0

    # Check if it's a pure number query
    if q.isdigit() and raw_id == q:
        return 0

    if raw_id.startswith(q) or raw_id.lower().startswith(q):
        return 1

    if q in mention.title.lower():
        return 2

    return 3


async def search_mentions(
    client: KaganCore,
    project_id: str,
    query: str,
    *,
    limit: int = 10,
) -> list[Mention]:
    """Return merged, scored mention results from kagan tasks and GitHub issues.

    Always returns kagan-task results.  GitHub results are added when the active
    project has a linked GitHub repo (detected via git remote origin).  If GitHub
    is not configured or the query fails, kagan-only results are returned silently.

    Results are scored (exact → prefix → substring), interleaved source-by-source
    up to ``limit`` total.
    """
    kagan_mentions = await _fetch_kagan_mentions(client, project_id, query, limit=limit)
    github_mentions = await _fetch_github_mentions(client, project_id, query, limit=limit)

    scored_kagan = sorted(kagan_mentions, key=lambda m: _score_mention(query, m))
    scored_github = sorted(github_mentions, key=lambda m: _score_mention(query, m))

    # Interleave kagan and github results zip-wise, then append remainder
    merged: list[Mention] = []
    for k, g in zip(scored_kagan, scored_github, strict=False):
        merged.append(k)
        merged.append(g)

    remaining_k = scored_kagan[len(scored_github) :]
    remaining_g = scored_github[len(scored_kagan) :]
    merged.extend(remaining_k)
    merged.extend(remaining_g)

    return merged[:limit]


async def _fetch_kagan_mentions(
    client: KaganCore,
    project_id: str,
    query: str,
    *,
    limit: int,
) -> list[Mention]:
    """Fetch matching kagan tasks and return them as Mention objects."""
    try:
        tasks = await client.tasks.search(
            query,
            project_id=project_id,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("Mention search (kagan) failed: {}", exc)
        return []

    return [
        Mention(
            source="kagan",
            id=f"kagan#{t.id[:8]}",
            title=t.title,
            state=t.status.value,
        )
        for t in tasks
    ]


async def _fetch_github_mentions(
    client: KaganCore,
    project_id: str,
    query: str,
    *,
    limit: int,
) -> list[Mention]:
    """Fetch matching GitHub issues and return them as Mention objects.

    Returns empty list if no GitHub repo is linked or any error occurs.
    """
    try:
        from kagan.core.integrations.github import (
            _search_issues,
            detect_github_repo_slug_from_origin,
        )

        repos = await client.projects.repos(project_id)
        if not repos:
            return []

        slug: str | None = None
        for repo in repos:
            slug = await detect_github_repo_slug_from_origin(repo.path)
            if slug:
                break

        if slug is None:
            return []

        issues = await _search_issues(slug, query, limit=limit)
        return [
            Mention(
                source="github",
                id=f"#{issue.get('number')}",
                title=issue.get("title", ""),
                state=issue.get("state"),
            )
            for issue in issues
            if issue.get("number") and issue.get("title")
        ]
    except Exception as exc:
        logger.debug("Mention search (github) skipped or failed: {}", exc)
        return []


__all__ = [
    "Mention",
    "search_mentions",
]
