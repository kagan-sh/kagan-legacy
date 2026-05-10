"""Shared fixtures for tests/integrations/."""

import sys

import pytest

import kagan.core.integrations.github  # noqa: F401  (side-effect: registers module in sys.modules)
from tests.helpers.github_fixtures import (
    make_github_client,
    make_github_config,
    make_github_integration,
)

_gh_module = sys.modules["kagan.core.integrations.github"]


@pytest.fixture
async def client(tmp_path):
    c = await make_github_client(tmp_path)
    yield c
    c.close()


@pytest.fixture
def config():
    return make_github_config()


@pytest.fixture
def integration():
    return make_github_integration()


@pytest.fixture
def authed_gh(monkeypatch):
    """Patch ``_gh_path`` and ``_gh_is_authenticated`` so integration code
    treats the gh CLI as available and authenticated without a real binary.
    """
    monkeypatch.setattr(_gh_module, "_gh_path", lambda: "/usr/bin/gh")

    async def _always_authed() -> bool:
        return True

    monkeypatch.setattr(_gh_module, "_gh_is_authenticated", _always_authed)
