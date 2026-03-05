import pytest

from kagan.core import CheckStatus, PreflightCheckResult
from kagan.integrations.github import (
    canonical_repo_slug,
    format_github_setup_message,
    github_blocking_checks,
    normalize_github_state,
    parse_github_repo_slug_from_remote_url,
)

pytestmark = [pytest.mark.plugins]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("octocat/hello-world", "octocat/hello-world"),
        ("  octocat/hello-world  ", "octocat/hello-world"),
    ],
)
def test_canonical_repo_slug_accepts_valid_values(raw: str, expected: str) -> None:
    assert canonical_repo_slug(raw) == expected


@pytest.mark.parametrize("raw", ["octocat", "octo cat/hello", "/hello", "octocat/"])
def test_canonical_repo_slug_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        canonical_repo_slug(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("open", "open"), ("CLOSED", "closed"), (" All ", "all")],
)
def test_normalize_github_state(raw: str, expected: str) -> None:
    assert normalize_github_state(raw) == expected


def test_normalize_github_state_rejects_unknown_values() -> None:
    with pytest.raises(ValueError):
        normalize_github_state("pending")


def test_github_blocking_checks_filters_non_pass_statuses() -> None:
    checks = [
        PreflightCheckResult(name="gh_cli", status=CheckStatus.PASS, message="ok", fix_hint=""),
        PreflightCheckResult(
            name="gh_auth",
            status=CheckStatus.WARN,
            message="not authenticated",
            fix_hint="Run gh auth login",
        ),
    ]
    blocked = github_blocking_checks(checks)

    assert len(blocked) == 1
    assert blocked[0].name == "gh_auth"


def test_format_github_setup_message_shows_fix_steps_for_blockers() -> None:
    checks = [
        PreflightCheckResult(
            name="gh_auth",
            status=CheckStatus.WARN,
            message="GitHub CLI not authenticated",
            fix_hint="Run gh auth login",
        )
    ]

    message = format_github_setup_message(checks)

    assert "GitHub setup is required before import" in message
    assert "GitHub CLI not authenticated" in message
    assert "Run gh auth login" in message


@pytest.mark.parametrize(
    ("remote_url", "expected"),
    [
        ("https://github.com/octocat/hello-world.git", "octocat/hello-world"),
        ("https://github.com/octocat/hello-world", "octocat/hello-world"),
        ("git@github.com:octocat/hello-world.git", "octocat/hello-world"),
        ("ssh://git@github.com/octocat/hello-world.git", "octocat/hello-world"),
        ("ssh://git@ssh.github.com:443/octocat/hello-world.git", "octocat/hello-world"),
    ],
)
def test_parse_github_repo_slug_from_remote_url(remote_url: str, expected: str) -> None:
    assert parse_github_repo_slug_from_remote_url(remote_url) == expected


@pytest.mark.parametrize(
    "remote_url",
    [
        "",
        "https://gitlab.com/octocat/hello-world.git",
        "https://evilgithub.com/octocat/hello-world.git",
        "https://github.com.evil.com/octocat/hello-world.git",
        "https://github.com@evil.com/octocat/hello-world.git",
        "git@github.com:octocat/hello/world.git",
        "github.com/octocat/hello-world",
    ],
)
def test_parse_github_repo_slug_from_remote_url_returns_none_for_unsupported(
    remote_url: str,
) -> None:
    assert parse_github_repo_slug_from_remote_url(remote_url) is None
