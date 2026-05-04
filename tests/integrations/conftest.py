"""Shared fixtures for tests/integrations/."""

import pytest

from tests.helpers.github_fixtures import (
    make_github_client,
    make_github_config,
    make_github_integration,
)


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
