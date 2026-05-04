"""Unit tests for doctor --json flag, category field, and telemetry events.

Covers:
- DoctorCheck.category field assignment and derive_check_category
- --json flag serialization (all six fields present, valid JSON)
- _emit_doctor_warned_telemetry payload shape
- first_session_success guard (fires once, not twice)
- Analytics.session_timeline includes doctor_warned_count and first_session_success_count
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from sqlmodel import SQLModel, create_engine

from kagan.cli.doctor import (
    DoctorCheck,
    _emit_doctor_warned_telemetry,
    _emit_json,
)
from kagan.core import Analytics, db_sync, derive_check_category, emit_telemetry
from kagan.core.models import Project, Session

pytestmark = [pytest.mark.unit]


# ── Helpers ───────────────────────────────────────────────────────────


def _make_engine(tmp_path: Path):
    """Create a SQLite test engine with the full schema."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _make_check(
    name: str = "git",
    status: str = "pass",
    message: str = "ok",
    fix_hint: str = "",
    verify_hint: str = "git --version",
    category: str = "core",
) -> DoctorCheck:
    return DoctorCheck(
        name=name,
        status=status,
        message=message,
        fix_hint=fix_hint,
        verify_hint=verify_hint,
        category=category,
    )


# ── category field tests ──────────────────────────────────────────────


def test_derive_check_category_core_checks() -> None:
    for name in ("git", "tmux", "db"):
        assert derive_check_category(name) == "core", f"Expected 'core' for '{name}'"


def test_derive_check_category_backend() -> None:
    assert derive_check_category("agent backend") == "backend"


def test_derive_check_category_environment() -> None:
    for name in ("ide", "terminal multiplexer", "project config", "startup env"):
        assert derive_check_category(name) == "environment", f"Expected 'environment' for '{name}'"


def test_derive_check_category_unknown_becomes_integration() -> None:
    assert derive_check_category("some custom integration check") == "integration"


def test_doctor_check_has_category_field() -> None:
    check = _make_check(name="git", category="core")
    assert check.category == "core"


def test_doctor_check_category_default_is_core() -> None:
    """DoctorCheck defaults category to 'core'."""
    check = DoctorCheck(
        name="git",
        status="pass",
        message="ok",
        fix_hint="",
        verify_hint="git --version",
    )
    assert check.category == "core"


# ── --json flag serialization tests ──────────────────────────────────


def test_emit_json_is_valid_json(capsys) -> None:
    checks = [
        _make_check("git", "pass", "git found", "", "git --version", "core"),
        _make_check("agent backend", "warn", "not found", "install it", "which claude", "backend"),
    ]
    _emit_json(checks)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_emit_json_contains_all_six_fields(capsys) -> None:
    checks = [_make_check("git", "pass", "ok", "", "git --version", "core")]
    _emit_json(checks)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    item = parsed[0]
    assert set(item.keys()) == {"name", "status", "message", "fix_hint", "verify_hint", "category"}


def test_emit_json_jq_status_field_works(capsys) -> None:
    """Simulate `jq '.[].status'` — each item must have a 'status' key."""
    checks = [
        _make_check("git", "pass", "ok", "", "git --version", "core"),
        _make_check(
            "ide", "warn", "not detected", "install VS Code", "echo $TERM_PROGRAM", "environment"
        ),
    ]
    _emit_json(checks)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    statuses = [item["status"] for item in parsed]
    assert statuses == ["pass", "warn"]


def test_emit_json_preserves_all_field_values(capsys) -> None:
    checks = [
        _make_check(
            name="agent backend",
            status="fail",
            message="not found",
            fix_hint="install claude",
            verify_hint="which claude",
            category="backend",
        )
    ]
    _emit_json(checks)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    item = parsed[0]
    assert item["name"] == "agent backend"
    assert item["status"] == "fail"
    assert item["message"] == "not found"
    assert item["fix_hint"] == "install claude"
    assert item["verify_hint"] == "which claude"
    assert item["category"] == "backend"


# ── doctor_warned telemetry payload shape tests ───────────────────────


def test_emit_doctor_warned_not_called_for_all_pass() -> None:
    """No telemetry emitted when all checks pass."""
    checks = [
        _make_check("git", "pass"),
        _make_check("db", "pass"),
    ]

    with patch("kagan.cli.doctor.emit_telemetry") as mock_emit:
        _emit_doctor_warned_telemetry(checks)
        mock_emit.assert_not_called()


def test_emit_doctor_warned_payload_shape_with_warn() -> None:
    """Payload has failing_check_names, warn_count, fail_count for WARN checks."""
    import asyncio

    checks = [
        _make_check("git", "pass"),
        _make_check("ide", "warn", fix_hint="install VS Code"),
        _make_check("agent backend", "warn", fix_hint="install claude"),
    ]

    captured_payloads: list[dict[str, Any]] = []

    async def capturing_emit(engine, event_type, payload):
        captured_payloads.append({"event_type": event_type, "payload": payload})

    with (
        patch("kagan.cli.doctor.create_db_engine"),
        patch("kagan.cli.doctor.default_db_path"),
        patch("kagan.cli.doctor.emit_telemetry", new=capturing_emit),
        patch(
            "kagan.cli.doctor.run_async",
            side_effect=lambda coro: asyncio.run(coro),
        ),
    ):
        _emit_doctor_warned_telemetry(checks)

    assert len(captured_payloads) == 1
    ev = captured_payloads[0]
    assert ev["event_type"] == "doctor_warned"
    payload = ev["payload"]
    assert "failing_check_names" in payload
    assert "warn_count" in payload
    assert "fail_count" in payload
    assert payload["warn_count"] == 2
    assert payload["fail_count"] == 0
    assert set(payload["failing_check_names"]) == {"ide", "agent backend"}


def test_emit_doctor_warned_payload_shape_with_fail() -> None:
    """Payload correctly differentiates warn vs fail counts."""
    import asyncio

    checks = [
        _make_check("git", "fail", fix_hint="install git"),
        _make_check("ide", "warn", fix_hint="install VS Code"),
    ]

    captured_payloads: list[dict[str, Any]] = []

    async def capturing_emit(engine, event_type, payload):
        captured_payloads.append({"event_type": event_type, "payload": payload})

    with (
        patch("kagan.cli.doctor.create_db_engine"),
        patch("kagan.cli.doctor.default_db_path"),
        patch("kagan.cli.doctor.emit_telemetry", new=capturing_emit),
        patch(
            "kagan.cli.doctor.run_async",
            side_effect=lambda coro: asyncio.run(coro),
        ),
    ):
        _emit_doctor_warned_telemetry(checks)

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]["payload"]
    assert payload["warn_count"] == 1
    assert payload["fail_count"] == 1
    assert "git" in payload["failing_check_names"]
    assert "ide" in payload["failing_check_names"]


# ── first_session_success guard tests ────────────────────────────────


@pytest.mark.asyncio
async def test_first_session_success_fires_on_first_completion(tmp_path: Path) -> None:
    """Telemetry is emitted when there are no prior completed sessions."""
    from kagan.core._sessions import Sessions

    engine = _make_engine(tmp_path)

    # Create a project (determines install time)
    def setup(s):
        project = Project(name="TestProject")
        s.add(project)
        session_obj = Session(
            task_id="fake-task",
            agent_backend="claude-code",
            status="COMPLETED",
        )
        s.add(session_obj)
        s.commit()
        s.refresh(session_obj)
        return session_obj.id

    session_id = db_sync(engine, setup, commit=False)

    emitted: list[dict[str, Any]] = []

    async def fake_emit(_eng, event_type: str, payload: dict):
        emitted.append({"event_type": event_type, "payload": payload})

    sessions_obj = Sessions.__new__(Sessions)
    sessions_obj._engine = engine

    import kagan.core._sessions as sessions_mod

    original = sessions_mod.emit_telemetry
    sessions_mod.emit_telemetry = fake_emit  # type: ignore[assignment]
    try:
        await sessions_obj._maybe_emit_first_session_success(session_id, "claude-code")
    finally:
        sessions_mod.emit_telemetry = original

    assert len(emitted) == 1
    ev = emitted[0]
    assert ev["event_type"] == "FIRST_SESSION_SUCCESS"
    assert ev["payload"]["backend"] == "claude-code"
    assert "seconds_since_install" in ev["payload"]
    assert ev["payload"]["seconds_since_install"] >= 0.0


@pytest.mark.asyncio
async def test_first_session_success_does_not_fire_on_subsequent_completion(
    tmp_path: Path,
) -> None:
    """Telemetry is NOT emitted when prior completed sessions exist."""
    from kagan.core._sessions import Sessions

    engine = _make_engine(tmp_path)

    def setup(s):
        project = Project(name="TestProject")
        s.add(project)
        # Prior completed session
        prior = Session(
            task_id="fake-task",
            agent_backend="claude-code",
            status="COMPLETED",
        )
        s.add(prior)
        # New completed session
        new_sess = Session(
            task_id="fake-task",
            agent_backend="claude-code",
            status="COMPLETED",
        )
        s.add(new_sess)
        s.commit()
        s.refresh(new_sess)
        return new_sess.id

    new_session_id = db_sync(engine, setup, commit=False)

    emitted: list[dict[str, Any]] = []

    async def fake_emit(_eng, event_type: str, payload: dict):
        emitted.append({"event_type": event_type, "payload": payload})

    sessions_obj = Sessions.__new__(Sessions)
    sessions_obj._engine = engine

    import kagan.core._sessions as sessions_mod

    original = sessions_mod.emit_telemetry
    sessions_mod.emit_telemetry = fake_emit  # type: ignore[assignment]
    try:
        await sessions_obj._maybe_emit_first_session_success(new_session_id, "claude-code")
    finally:
        sessions_mod.emit_telemetry = original

    # Prior session exists, so no event should fire
    assert len(emitted) == 0


# ── analytics session_timeline telemetry integration ─────────────────


@pytest.mark.asyncio
async def test_session_timeline_includes_telemetry_counts(tmp_path: Path) -> None:
    """session_timeline rows include doctor_warned_count and first_session_success_count."""
    engine = _make_engine(tmp_path)

    # Emit a DOCTOR_WARNED telemetry event
    await emit_telemetry(
        engine,
        "DOCTOR_WARNED",
        {"failing_check_names": ["ide"], "warn_count": 1, "fail_count": 0},
    )
    # Emit a FIRST_SESSION_SUCCESS telemetry event
    await emit_telemetry(
        engine,
        "FIRST_SESSION_SUCCESS",
        {"backend": "claude-code", "seconds_since_install": 10.0},
    )

    analytics = Analytics(engine)
    # project_id can be anything — no sessions exist, telemetry events are project-agnostic
    timeline = await analytics.session_timeline("nonexistent-project", days=30)

    # Should have at least one row for today from telemetry events
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    today_rows = [r for r in timeline if r["date"] == today_str]
    assert len(today_rows) == 1
    row = today_rows[0]
    assert "doctor_warned_count" in row
    assert "first_session_success_count" in row
    assert row["doctor_warned_count"] == 1
    assert row["first_session_success_count"] == 1
