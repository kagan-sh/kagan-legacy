"""Tests: dual-source mention autocomplete (search_mentions)."""

from unittest.mock import AsyncMock, patch

import pytest

from kagan.core import KaganCore
from kagan.core.integrations.mentions import Mention, search_mentions

pytestmark = [pytest.mark.integrations]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(tmp_path):
    c = KaganCore(db_path=tmp_path / "test.db")
    project = await c.projects.create("Test Project")
    await c.projects.set_active(project.id)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Kagan-only (no GitHub link)
# ---------------------------------------------------------------------------


async def test_mentions_returns_kagan_tasks_only_when_no_github_link(client) -> None:
    """When the project has no GitHub link, only kagan tasks are returned."""
    await client.tasks.create("Login feature", description="auth work")
    await client.tasks.create("Logout feature", description="signout")

    project_id = client.active_project_id
    results = await search_mentions(client, project_id, "login")

    assert all(m.source == "kagan" for m in results)
    assert any("Login feature" in m.title for m in results)


async def test_mentions_insert_form_is_kagan_or_hash_n(client) -> None:
    """Kagan mention id is 'kagan#<8 chars>'; GitHub id is '#<n>'."""
    task = await client.tasks.create("Kagan task for mentions")
    project_id = client.active_project_id

    with patch(
        "kagan.core.integrations.mentions._fetch_github_mentions",
        new_callable=AsyncMock,
        return_value=[Mention(source="github", id="#42", title="GitHub issue", state="open")],
    ):
        results = await search_mentions(client, project_id, "kagan", limit=10)

    kagan_result = next((m for m in results if m.source == "kagan"), None)
    github_result = next((m for m in results if m.source == "github"), None)

    assert kagan_result is not None
    assert kagan_result.id.startswith("kagan#")
    assert len(kagan_result.id) == len("kagan#") + 8

    assert github_result is not None
    assert github_result.id.startswith("#")
    assert github_result.id[1:].isdigit()

    # Task short_id matches first 8 chars of task.id
    assert kagan_result.id == f"kagan#{task.id[:8]}"


# ---------------------------------------------------------------------------
# Merging kagan and github
# ---------------------------------------------------------------------------


async def test_mentions_merges_kagan_and_github_results(client) -> None:
    """Results from both sources are present in merged output."""
    await client.tasks.create("Auth task")
    project_id = client.active_project_id

    github_results = [
        Mention(source="github", id="#5", title="Auth GitHub issue", state="open")
    ]
    with patch(
        "kagan.core.integrations.mentions._fetch_github_mentions",
        new_callable=AsyncMock,
        return_value=github_results,
    ):
        results = await search_mentions(client, project_id, "auth", limit=10)

    sources = {m.source for m in results}
    assert "kagan" in sources
    assert "github" in sources


async def test_mentions_returns_at_most_limit(client) -> None:
    """Total results never exceed limit."""
    for i in range(8):
        await client.tasks.create(f"Task {i} matching query")

    github_results = [
        Mention(source="github", id=f"#{i}", title=f"Issue {i}", state="open")
        for i in range(8)
    ]
    project_id = client.active_project_id
    with patch(
        "kagan.core.integrations.mentions._fetch_github_mentions",
        new_callable=AsyncMock,
        return_value=github_results,
    ):
        results = await search_mentions(client, project_id, "task", limit=5)

    assert len(results) <= 5


# ---------------------------------------------------------------------------
# Ranking / scoring
# ---------------------------------------------------------------------------


async def test_mentions_short_id_exact_match_ranks_first(client) -> None:
    """A task whose short_id exactly matches the query appears first."""
    task = await client.tasks.create("Some unrelated title")
    project_id = client.active_project_id
    short_id = task.id[:8]

    results = await search_mentions(client, project_id, short_id, limit=10)
    kagan_results = [m for m in results if m.source == "kagan"]
    assert kagan_results[0].id == f"kagan#{short_id}"


async def test_mentions_github_number_exact_match_ranks_first(client) -> None:
    """A GitHub issue whose number exactly matches the query appears first."""
    github_results = [
        Mention(source="github", id="#42", title="Exact match", state="open"),
        Mention(source="github", id="#421", title="Similar number", state="open"),
    ]
    project_id = client.active_project_id
    with patch(
        "kagan.core.integrations.mentions._fetch_github_mentions",
        new_callable=AsyncMock,
        return_value=github_results,
    ):
        results = await search_mentions(client, project_id, "42", limit=10)

    github_results_out = [m for m in results if m.source == "github"]
    assert github_results_out[0].id == "#42"
