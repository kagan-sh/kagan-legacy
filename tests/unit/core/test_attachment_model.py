"""Unit tests for the Attachment boundary model.

Validates ``kagan.core._io.sessions.Attachment`` and the private
``AttachmentBody`` parser used by ``server/_chat_routes._parse_attachments``.
"""

from __future__ import annotations

import pytest

from kagan.core._io.sessions import Attachment, AttachmentBody

pytestmark = [pytest.mark.core, pytest.mark.unit]


# ---------------------------------------------------------------------------
# Attachment model — field validation
# ---------------------------------------------------------------------------


def test_attachment_requires_data_field() -> None:
    """Attachment.data is required; missing it raises ValidationError."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Attachment.model_validate({"type": "image", "name": "photo.png", "mime_type": "image/png"})


def test_attachment_optional_fields_default_to_empty_string() -> None:
    a = Attachment.model_validate({"data": "base64abc"})
    assert a.type == ""
    assert a.name == ""
    assert a.mime_type == ""
    assert a.data == "base64abc"


def test_attachment_accepts_full_payload() -> None:
    a = Attachment.model_validate(
        {"type": "image", "name": "pic.png", "mime_type": "image/png", "data": "abc123"}
    )
    assert a.type == "image"
    assert a.name == "pic.png"
    assert a.mime_type == "image/png"
    assert a.data == "abc123"


def test_attachment_extra_fields_ignored() -> None:
    """extra='ignore' — unknown keys do not raise."""
    a = Attachment.model_validate({"data": "x", "unknown_key": "ignored"})
    assert a.data == "x"


def test_attachment_is_frozen() -> None:
    """Attachment instances are immutable."""
    a = Attachment.model_validate({"data": "x"})
    with pytest.raises(Exception):
        a.data = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AttachmentBody — parsing the attachments array
# ---------------------------------------------------------------------------


def test_attachment_body_parses_valid_list() -> None:
    body = AttachmentBody.model_validate(
        {
            "attachments": [
                {"type": "image", "name": "a.png", "mime_type": "image/png", "data": "abc"},
                {"data": "xyz"},
            ]
        }
    )
    assert len(body.attachments) == 2
    assert body.attachments[0].type == "image"
    assert body.attachments[1].data == "xyz"


def test_attachment_body_empty_list_returns_empty() -> None:
    body = AttachmentBody.model_validate({"attachments": []})
    assert body.attachments == []


def test_attachment_body_missing_attachments_defaults_to_empty() -> None:
    body = AttachmentBody.model_validate({})
    assert body.attachments == []


def test_attachment_body_extra_keys_ignored() -> None:
    """extra='ignore' on AttachmentBody — other request-body fields do not raise."""
    body = AttachmentBody.model_validate(
        {"attachments": [{"data": "abc"}], "text": "hello", "agent_backend": "claude"}
    )
    assert len(body.attachments) == 1


def test_attachment_model_dump_returns_dict() -> None:
    """model_dump() produces a dict compatible with the downstream dict consumers."""
    a = Attachment.model_validate(
        {"type": "image", "name": "pic.png", "mime_type": "image/png", "data": "base64"}
    )
    dumped = a.model_dump()
    assert dumped == {
        "type": "image",
        "name": "pic.png",
        "mime_type": "image/png",
        "data": "base64",
    }
