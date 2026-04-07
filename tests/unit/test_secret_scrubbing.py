"""Tests for secret scrubbing in event payloads."""

import pytest

from kagan.core._events import _scrub_secrets

pytestmark = [pytest.mark.unit]


def test_scrub_aws_key() -> None:
    payload = {"text": "key is AKIAIOSFODNN7EXAMPLE"}
    result = _scrub_secrets(payload)
    assert result == {"text": "key is [REDACTED]"}


def test_scrub_github_pat() -> None:
    token = "ghp_" + "a" * 36
    payload = {"text": f"token={token}"}
    result = _scrub_secrets(payload)
    assert "[REDACTED]" in result["text"]
    assert token not in result["text"]


def test_scrub_github_user_token() -> None:
    token = "ghu_" + "b" * 36
    payload = {"msg": token}
    result = _scrub_secrets(payload)
    assert result["msg"] == "[REDACTED]"


def test_scrub_nested_dict() -> None:
    token = "ghp_" + "b" * 36
    payload = {"outer": {"inner": token}}
    result = _scrub_secrets(payload)
    assert result["outer"]["inner"] == "[REDACTED]"


def test_scrub_sensitive_key_name() -> None:
    secret_key = "pass" + "word"
    payload = {secret_key: "hunter" + "2", "normal": "value"}
    result = _scrub_secrets(payload)
    assert result[secret_key] == "[REDACTED]"
    assert result["normal"] == "value"


def test_scrub_token_key() -> None:
    payload = {"authorization": "anything", "status": "ok"}
    result = _scrub_secrets(payload)
    assert result["authorization"] == "[REDACTED]"
    assert result["status"] == "ok"


def test_scrub_list_values() -> None:
    token = "ghp_" + "c" * 36
    payload = {"items": ["normal", token]}
    result = _scrub_secrets(payload)
    assert result["items"][0] == "normal"
    assert result["items"][1] == "[REDACTED]"


def test_no_false_positive() -> None:
    # "sk-short" is too short for the OpenAI pattern (needs 20+ chars after sk-)
    payload = {"msg": "task-skip validation", "status": "ask-question", "val": "sk-short"}
    result = _scrub_secrets(payload)
    assert result == payload


def test_no_mutation() -> None:
    original = {"key": "AKIAIOSFODNN7EXAMPLE"}
    original_copy = dict(original)
    _scrub_secrets(original)
    assert original == original_copy


def test_non_string_values_unchanged() -> None:
    payload = {"count": 42, "flag": True, "nested": {"num": 3.14}}
    result = _scrub_secrets(payload)
    assert result == payload


def test_scrub_bearer_token() -> None:
    payload = {"header": "Bearer " + "abcdefghijklmnopqrstuvwxyz"}
    result = _scrub_secrets(payload)
    assert result["header"] == "[REDACTED]"


def test_scrub_openai_key() -> None:
    key = "sk-" + "x" * 30
    payload = {"info": f"Using key {key}"}
    result = _scrub_secrets(payload)
    assert "[REDACTED]" in result["info"]
    assert key not in result["info"]
