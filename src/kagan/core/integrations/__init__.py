"""kagan.core.integrations — typed native integrations.

Today's integrations: github.

Adding a new integration::

    1. Create src/kagan/core/integrations/<name>.py with a class implementing
       the Integration protocol (see _base.py).
    2. Add it to all_enabled() below.
    3. Wire per-id branches in _integration_routes.py and the MCP toolset.

Top-level exports are deliberately minimal. Integration-specific helpers
(GitHub: canonical_repo_slug, preview_github_issues, …) live on their
submodules — import them directly from ``kagan.core.integrations.github``.
"""

from __future__ import annotations

from kagan.core.integrations._base import ExternalItem, ImportResult, Integration
from kagan.core.integrations.github import GitHubConfig, GitHubIntegration, github


def all_enabled() -> list[Integration]:
    """Return currently-configured integrations.

    Today: always ``[github]``. The GitHub integration's runtime checks
    (gh CLI installed, authenticated) flow through ``preflight()`` rather
    than excluding it from the list — that way ``kg doctor`` can still
    report the missing dependency.

    When a future integration (Jira, Linear) requires per-project config to
    be useful, this function checks that config and excludes the integration
    when not configured.
    """
    return [github]


__all__ = [
    "ExternalItem",
    "GitHubConfig",
    "GitHubIntegration",
    "ImportResult",
    "Integration",
    "all_enabled",
    "github",
]
