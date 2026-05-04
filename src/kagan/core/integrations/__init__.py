"""kagan.core.integrations — typed native integrations.

Today's integrations: github.

Top-level exports are deliberately minimal. Integration-specific helpers
(GitHub: canonical_repo_slug, preview_github_issues, …) live on their
submodules — import them directly from ``kagan.core.integrations.github``.
"""

from __future__ import annotations

from kagan.core.integrations._types import ExternalItem, ImportResult
from kagan.core.integrations.github import GitHubConfig, GitHubIntegration, github


def all_enabled() -> list[GitHubIntegration]:
    """Return currently-configured integrations.

    Today: always ``[github]``. The GitHub integration's runtime checks
    (gh CLI installed, authenticated) flow through ``preflight()`` rather
    than excluding it from the list — that way ``kg doctor`` can still
    report the missing dependency.
    """
    return [github]


__all__ = [
    "ExternalItem",
    "GitHubConfig",
    "GitHubIntegration",
    "ImportResult",
    "all_enabled",
    "github",
]
