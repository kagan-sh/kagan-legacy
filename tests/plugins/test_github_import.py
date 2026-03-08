"""Tests: GitHub import plugin — label mapping, idempotent sync, description building."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from kagan.core import KaganCore, Priority
from kagan.core.enums import WorkMode
from kagan.plugins._github import (
    GitHubImportConfig,
    GitHubImporter,
    _build_description,
    _extract_label_names,
    _map_labels,
)

pytestmark = [pytest.mark.plugins]


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


@pytest.fixture
def config():
    return GitHubImportConfig(owner="octocat", repo="hello-world")


@pytest.fixture
async def plugin(config, client):
    p = GitHubImporter(config)
    await p.setup(client)
    return p


# ---------------------------------------------------------------------------
# Label mapping (pure functions — fast, no I/O)
# ---------------------------------------------------------------------------


def test_extract_label_names_from_gh_format() -> None:
    """Labels are extracted from nested gh JSON format."""
    issue = {"labels": [{"name": "bug"}, {"name": "priority:high"}]}
    assert _extract_label_names(issue) == ["bug", "priority:high"]


def test_extract_label_names_handles_empty() -> None:
    """Empty or missing labels return empty list."""
    assert _extract_label_names({}) == []
    assert _extract_label_names({"labels": []}) == []
    assert _extract_label_names({"labels": None}) == []


def test_map_labels_priority() -> None:
    """Priority labels map to Priority enum values."""
    priority, mode, remaining = _map_labels(["priority:high", "bug"])
    assert priority == Priority.HIGH
    assert mode == WorkMode.AUTO  # default
    assert remaining == ["bug"]


def test_map_labels_execution_mode() -> None:
    """Execution mode labels map to WorkMode enum values."""
    priority, mode, remaining = _map_labels(["kagan:auto", "enhancement"])
    assert mode == WorkMode.AUTO
    assert priority == Priority.MEDIUM  # default
    assert remaining == ["enhancement"]


def test_map_labels_combined() -> None:
    """Priority + mode labels can appear together."""
    priority, mode, remaining = _map_labels(["priority:critical", "kagan:pair", "frontend", "bug"])
    assert priority == Priority.CRITICAL
    assert mode == WorkMode.PAIR
    assert remaining == ["frontend", "bug"]


def test_map_labels_case_insensitive() -> None:
    """Label matching is case-insensitive."""
    priority, _, _ = _map_labels(["Priority:HIGH"])
    assert priority == Priority.HIGH


def test_map_labels_defaults_when_no_mapped_labels() -> None:
    priority, mode, remaining = _map_labels(["bug", "documentation"])
    assert priority == Priority.MEDIUM
    assert mode == WorkMode.AUTO
    assert remaining == ["bug", "documentation"]


# ---------------------------------------------------------------------------
# Description building
# ---------------------------------------------------------------------------


def test_build_description_with_url_body_and_labels() -> None:
    """Description includes URL, extra labels as tags, and body."""
    issue = {
        "url": "https://github.com/octocat/hello-world/issues/42",
        "body": "Fix the login bug",
    }
    desc = _build_description(issue, ["bug", "frontend"])
    assert "https://github.com/octocat/hello-world/issues/42" in desc
    assert "[bug]" in desc
    assert "[frontend]" in desc
    assert "Fix the login bug" in desc


def test_build_description_no_labels_no_body() -> None:
    """Description with only URL when body and labels are empty."""
    issue = {"url": "https://github.com/x/y/issues/1", "body": ""}
    desc = _build_description(issue, [])
    assert desc == "https://github.com/x/y/issues/1"


# ---------------------------------------------------------------------------
# Sync config
# ---------------------------------------------------------------------------


def test_sync_config_settings_key(config: GitHubImportConfig) -> None:
    """Settings key uses owner/repo slug."""
    assert config.settings_key() == "plugin.github.octocat/hello-world.sync_map"


def test_sync_config_repo_slug(config: GitHubImportConfig) -> None:
    """repo_slug joins owner and repo."""
    assert config.repo_slug == "octocat/hello-world"


# ---------------------------------------------------------------------------
# Idempotent sync (with mocked gh CLI)
# ---------------------------------------------------------------------------


def _make_gh_issues(*issues):
    """Build a list of issue dicts in gh CLI JSON format."""
    result = []
    for num, title, labels in issues:
        result.append(
            {
                "number": num,
                "title": title,
                "body": f"Body for #{num}",
                "labels": [{"name": lbl} for lbl in labels],
                "state": "OPEN",
                "url": f"https://github.com/octocat/hello-world/issues/{num}",
            }
        )
    return result


@patch("kagan.plugins._github._gh_fetch_issues", new_callable=AsyncMock)
@patch("kagan.plugins._github._gh_is_authenticated", new_callable=AsyncMock, return_value=True)
@patch("kagan.plugins._github._gh_path", return_value="/usr/bin/gh")
async def test_sync_creates_tasks_from_issues(
    _mock_path, _mock_auth, mock_fetch, plugin, client
) -> None:
    """First sync creates tasks for each GitHub issue."""
    mock_fetch.return_value = _make_gh_issues(
        (1, "Bug report", ["bug", "priority:high"]),
        (2, "Feature request", ["enhancement", "kagan:auto"]),
    )

    result = await plugin.sync(client.active_project_id)
    assert result.created == 2
    assert result.skipped == 0

    tasks = await client.tasks.list()
    titles = {t.title for t in tasks}
    assert "Bug report" in titles
    assert "Feature request" in titles

    # Verify label mapping
    bug_task = next(t for t in tasks if t.title == "Bug report")
    assert bug_task.priority == Priority.HIGH

    feature_task = next(t for t in tasks if t.title == "Feature request")
    assert feature_task.execution_mode == WorkMode.AUTO


@patch("kagan.plugins._github._gh_fetch_issues", new_callable=AsyncMock)
@patch("kagan.plugins._github._gh_is_authenticated", new_callable=AsyncMock, return_value=True)
@patch("kagan.plugins._github._gh_path", return_value="/usr/bin/gh")
async def test_sync_is_idempotent(_mock_path, _mock_auth, mock_fetch, plugin, client) -> None:
    """Running sync twice with same issues creates tasks only once."""
    issues = _make_gh_issues((1, "Bug report", ["bug"]))
    mock_fetch.return_value = issues

    result1 = await plugin.sync(client.active_project_id)
    assert result1.created == 1

    # Second sync — same issues
    result2 = await plugin.sync(client.active_project_id)
    assert result2.created == 0
    assert result2.skipped == 1

    # Only one task exists
    tasks = await client.tasks.list()
    assert len(tasks) == 1


@patch("kagan.plugins._github._gh_fetch_issues", new_callable=AsyncMock)
@patch("kagan.plugins._github._gh_is_authenticated", new_callable=AsyncMock, return_value=True)
@patch("kagan.plugins._github._gh_path", return_value="/usr/bin/gh")
async def test_sync_reimports_deleted_tasks(
    _mock_path, _mock_auth, mock_fetch, plugin, client
) -> None:
    """If a synced task is deleted, re-sync re-creates it."""
    issues = _make_gh_issues((1, "Bug report", ["bug"]))
    mock_fetch.return_value = issues

    result1 = await plugin.sync(client.active_project_id)
    assert result1.created == 1

    # Delete the task
    tasks = await client.tasks.list()
    await client.tasks.delete(tasks[0].id)

    # Re-sync should re-create
    result2 = await plugin.sync(client.active_project_id)
    assert result2.created == 1
    assert result2.skipped == 0


@patch("kagan.plugins._github._gh_fetch_issues", new_callable=AsyncMock)
@patch("kagan.plugins._github._gh_is_authenticated", new_callable=AsyncMock, return_value=True)
@patch("kagan.plugins._github._gh_path", return_value="/usr/bin/gh")
async def test_sync_incremental_new_issues(
    _mock_path, _mock_auth, mock_fetch, plugin, client
) -> None:
    """Sync picks up new issues while skipping already-imported ones."""
    mock_fetch.return_value = _make_gh_issues((1, "First", []))
    result1 = await plugin.sync(client.active_project_id)
    assert result1.created == 1

    # New issue added
    mock_fetch.return_value = _make_gh_issues((1, "First", []), (2, "Second", []))
    result2 = await plugin.sync(client.active_project_id)
    assert result2.created == 1
    assert result2.skipped == 1

    tasks = await client.tasks.list()
    assert len(tasks) == 2


@patch("kagan.plugins._github._gh_fetch_issues", new_callable=AsyncMock)
@patch("kagan.plugins._github._gh_is_authenticated", new_callable=AsyncMock, return_value=True)
@patch("kagan.plugins._github._gh_path", return_value="/usr/bin/gh")
async def test_sync_persists_map_in_settings(
    _mock_path, _mock_auth, mock_fetch, plugin, client
) -> None:
    """Sync map is persisted in settings and survives plugin reinstantiation."""
    mock_fetch.return_value = _make_gh_issues((42, "Important fix", []))
    await plugin.sync(client.active_project_id)

    # Check settings
    settings = await client.settings.get()
    key = plugin._config.settings_key()
    assert key in settings
    sync_map = json.loads(settings[key])
    assert "42" in sync_map


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


@patch("kagan.plugins._github._gh_path", return_value=None)
def test_preflight_warns_gh_missing(_mock_path, plugin) -> None:
    """Preflight warns when gh CLI is not installed."""
    checks = plugin.preflight()
    assert any(c.name == "gh_cli" and c.status.value == "warn" for c in checks)
    assert any("https://cli.github.com" in c.fix_hint for c in checks)


@patch("kagan.plugins._github.subprocess")
@patch("kagan.plugins._github._gh_path", return_value="/usr/bin/gh")
def test_preflight_passes_when_gh_authed(_mock_path, mock_subprocess, plugin) -> None:
    """Preflight passes when gh is installed and authenticated."""
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "gho_fake_token"
    mock_subprocess.TimeoutExpired = TimeoutError

    checks = plugin.preflight()
    gh_cli = next(c for c in checks if c.name == "gh_cli")
    assert gh_cli.status.value == "pass"
