"""Tests for the _mention_links.linkify_mentions helper.

These tests verify that bare kagan#<id> and #<n> tokens are replaced with
markdown link syntax, and that already-linked tokens and URL fragments are
left untouched.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def _linkify(markdown: str, *, slug: str | None = None) -> str:
    from kagan.tui.widgets._mention_links import linkify_mentions

    return linkify_mentions(markdown, github_repo_slug=slug)


# ---------------------------------------------------------------------------
# kagan tokens
# ---------------------------------------------------------------------------


def test_linkify_kagan_token_with_short_id() -> None:
    result = _linkify("See kagan#aabbccdd for context.", slug=None)
    assert result == "See [kagan#aabbccdd](kagan-task://aabbccdd) for context."


def test_linkify_kagan_token_longer_id() -> None:
    result = _linkify("Fixes kagan#1234abcd5678.", slug=None)
    assert result == "Fixes [kagan#1234abcd5678](kagan-task://1234abcd5678)."


def test_linkify_kagan_token_no_slug_needed() -> None:
    """kagan# tokens are always linked regardless of github_repo_slug."""
    result = _linkify("kagan#deadbeef", slug=None)
    assert "[kagan#deadbeef](kagan-task://deadbeef)" in result


# ---------------------------------------------------------------------------
# GitHub #<n> tokens
# ---------------------------------------------------------------------------


def test_linkify_github_number_with_slug() -> None:
    result = _linkify("Closes #42.", slug="octocat/Hello-World")
    assert result == "Closes [#42](https://github.com/octocat/Hello-World/issues/42)."


def test_linkify_no_slug_renders_plain_hash_n() -> None:
    """When github_repo_slug is None, #<n> tokens are left as-is."""
    result = _linkify("Closes #42.", slug=None)
    assert result == "Closes #42."


def test_linkify_multiple_github_numbers() -> None:
    result = _linkify("Fixes #1 and #2.", slug="owner/repo")
    assert "[#1](https://github.com/owner/repo/issues/1)" in result
    assert "[#2](https://github.com/owner/repo/issues/2)" in result


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_linkify_idempotent_on_already_linked_kagan() -> None:
    """Running linkify twice on an already-linked kagan token must be a no-op."""
    first = _linkify("See kagan#aabbccdd.", slug=None)
    second = _linkify(first, slug=None)
    assert first == second


def test_linkify_idempotent_on_already_linked_github() -> None:
    """Running linkify twice on an already-linked GitHub token must be a no-op."""
    first = _linkify("Closes #42.", slug="octocat/Hello-World")
    second = _linkify(first, slug="octocat/Hello-World")
    assert first == second


def test_linkify_idempotent_on_explicit_markdown_link() -> None:
    """Manually written markdown links are untouched."""
    already = "[kagan#aabbccdd](kagan-task://aabbccdd)"
    result = _linkify(already, slug=None)
    assert result == already


# ---------------------------------------------------------------------------
# URL fragment safety
# ---------------------------------------------------------------------------


def test_linkify_does_not_touch_url_fragments() -> None:
    """Hash anchors in URLs (e.g. https://example.com/page#section) are not matched."""
    url = "https://example.com/page#section"
    result = _linkify(url, slug="owner/repo")
    assert result == url


def test_linkify_does_not_match_kagan_hash_inside_url() -> None:
    """kagan# inside an already-formed URL is not double-linked."""
    url = "(kagan-task://aabbccdd)"
    result = _linkify(url, slug=None)
    # The URL itself should not be modified; note there is no ``kagan#`` token here
    assert result == url


def test_linkify_mixed_tokens() -> None:
    text = "Related: kagan#deadbeef and #99."
    result = _linkify(text, slug="my/repo")
    assert "[kagan#deadbeef](kagan-task://deadbeef)" in result
    assert "[#99](https://github.com/my/repo/issues/99)" in result


def test_linkify_empty_string() -> None:
    assert _linkify("", slug=None) == ""
    assert _linkify("", slug="owner/repo") == ""


def test_linkify_kagan_too_short_id_not_matched() -> None:
    """kagan# tokens with fewer than 6 hex chars must NOT be matched."""
    result = _linkify("See kagan#ab123.", slug=None)
    # 5 hex chars — should NOT be matched
    assert result == "See kagan#ab123."
