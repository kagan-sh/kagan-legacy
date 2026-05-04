"""Shared GitHub integration test factories.

Provides factory functions consumed by conftest.py in tests/integrations/
to build the client, config, and integration fixtures.
"""

from __future__ import annotations

from kagan.core import KaganCore
from kagan.core.integrations.github import GitHubConfig, GitHubIntegration
from tests.helpers.helpers import make_git_repo


async def make_github_client(tmp_path):
    """Build a KaganCore instance with a project and a single attached git repo."""
    c = KaganCore(db_path=tmp_path / "test.db")
    project = await c.projects.create("Test Project")
    await c.projects.set_active(project.id)
    repo_path = tmp_path / "test-repo"
    await make_git_repo(repo_path)
    await c.projects.add_repo(project.id, str(repo_path))
    return c


def make_github_config() -> GitHubConfig:
    return GitHubConfig(owner="octocat", repo="hello-world")


def make_github_integration() -> GitHubIntegration:
    return GitHubIntegration()


__all__ = ["make_github_client", "make_github_config", "make_github_integration"]
