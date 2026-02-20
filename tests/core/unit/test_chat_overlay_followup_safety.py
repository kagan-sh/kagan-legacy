from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

from kagan.core.safety import REDACTED_EMAIL, REDACTED_TOKEN
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay

if TYPE_CHECKING:
    from pathlib import Path


def test_auto_follow_up_payload_redacts_sensitive_content() -> None:
    overlay = ChatOverlay()
    payload = overlay._build_auto_follow_up_payload(
        "Authorization: Bearer super-secret-token\ncontact=engineer@example.com"
    )

    assert REDACTED_TOKEN in payload
    assert REDACTED_EMAIL in payload
    assert "super-secret-token" not in payload
    assert "engineer@example.com" not in payload


def test_review_follow_up_payload_redacts_sensitive_content() -> None:
    note = ChatOverlay._build_review_follow_up_payload(
        "api_key=sk-1234567890abcdefghijklmnopqrst\nssn=123-45-6789"
    )

    assert REDACTED_TOKEN in note
    assert "sk-1234567890abcdefghijklmnopqrst" not in note
    assert "123-45-6789" not in note


def test_suppresses_removed_agent_commands() -> None:
    overlay = ChatOverlay()

    assert overlay._is_suppressed_agent_command(SimpleNamespace(name="textual")) is True
    assert overlay._is_suppressed_agent_command(SimpleNamespace(name="textual:snapshot")) is True
    assert overlay._is_suppressed_agent_command(SimpleNamespace(name="find-skills")) is False


def test_discover_local_skills_reads_metadata_with_precedence(tmp_path: Path) -> None:
    high_priority = tmp_path / "project-skills"
    low_priority = tmp_path / "user-skills"
    (high_priority / "code-review").mkdir(parents=True)
    (low_priority / "code-review").mkdir(parents=True)
    (low_priority / "doc-generator").mkdir(parents=True)

    (high_priority / "code-review" / "SKILL.md").write_text(
        (
            "---\n"
            "name: code-review\n"
            "description: Escalate to sec@example.com when uncertain.\n"
            "---\n"
            "# Skill body should never be auto-injected.\n"
        ),
        encoding="utf-8",
    )
    (low_priority / "code-review" / "SKILL.md").write_text(
        ("---\nname: code-review\ndescription: Lower precedence duplicate.\n---\n"),
        encoding="utf-8",
    )
    (low_priority / "doc-generator" / "SKILL.md").write_text(
        "# No frontmatter; fallback name should use directory name.\n",
        encoding="utf-8",
    )

    discovered = ChatOverlay._discover_local_skills_for_roots(
        [high_priority.resolve(), low_priority.resolve()]
    )
    by_name = {skill.name: skill for skill in discovered}

    assert set(by_name) == {"code-review", "doc-generator"}
    assert by_name["code-review"].source_root == high_priority.resolve()
    assert REDACTED_EMAIL in by_name["code-review"].description
    assert "sec@example.com" not in by_name["code-review"].description


def test_discover_local_skills_rejects_invalid_skill_names(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    (root / "valid-skill").mkdir(parents=True)
    (root / "fallback-skill").mkdir(parents=True)

    (root / "valid-skill" / "SKILL.md").write_text(
        ("---\nname: Invalid Name\ndescription: Should be rejected.\n---\n"),
        encoding="utf-8",
    )
    (root / "fallback-skill" / "SKILL.md").write_text(
        "# Missing frontmatter uses directory name.\n",
        encoding="utf-8",
    )

    discovered = ChatOverlay._discover_local_skills_for_roots([root.resolve()])
    names = {skill.name for skill in discovered}

    assert "invalid name" not in names
    assert names == {"fallback-skill"}


def test_supports_native_compact_when_agent_command_is_available() -> None:
    overlay = ChatOverlay()
    overlay._available_commands = [SimpleNamespace(name="compact")]

    assert overlay._supports_native_compact() is True


def test_supports_native_compact_false_without_agent_command() -> None:
    overlay = ChatOverlay()
    overlay._available_commands = [SimpleNamespace(name="plan_tasks")]

    assert overlay._supports_native_compact() is False


def test_compact_snapshot_redacts_sensitive_content() -> None:
    overlay = ChatOverlay()
    overlay._conversation_history = [
        ("user", "Authorization: Bearer super-secret-token"),
        ("assistant", "contact=engineer@example.com"),
    ]

    snapshot = overlay._build_compact_snapshot()

    assert "User:" in snapshot
    assert "Assistant:" in snapshot
    assert REDACTED_TOKEN in snapshot
    assert REDACTED_EMAIL in snapshot
    assert "super-secret-token" not in snapshot
    assert "engineer@example.com" not in snapshot


def test_intro_quote_probability_gate_can_skip_quote() -> None:
    overlay = ChatOverlay()
    with patch("kagan.tui.ui.widgets.chat_overlay.random.random", return_value=0.99):
        quote = overlay._build_intro_quote()

    assert quote == ""


def test_intro_quote_can_emit_funny_quote() -> None:
    overlay = ChatOverlay()
    with (
        patch("kagan.tui.ui.widgets.chat_overlay.random.random", return_value=0.0),
        patch(
            "kagan.tui.ui.widgets.chat_overlay.random.choice",
            return_value=("Funny", "Planning is just future debugging."),
        ),
    ):
        quote = overlay._build_intro_quote()

    assert quote == '"Planning is just future debugging."'


def test_intro_quote_can_emit_wise_quote() -> None:
    overlay = ChatOverlay()
    with (
        patch("kagan.tui.ui.widgets.chat_overlay.random.random", return_value=0.0),
        patch(
            "kagan.tui.ui.widgets.chat_overlay.random.choice",
            return_value=("Wise", "Small, finished steps beat perfect intentions."),
        ),
    ):
        quote = overlay._build_intro_quote()

    assert quote == '"Small, finished steps beat perfect intentions."'
