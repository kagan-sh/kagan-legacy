"""Unit tests for SQLite WAL + tuning pragmas applied at engine creation."""

import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session as DBSession

from kagan.core._db import create_db_engine
from kagan.core._db_helpers import _db_async
from kagan.core.models import TelemetryEvent

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pragma(engine, pragma_name: str) -> str:
    """Return the current value of *pragma_name* as a lowercase string."""
    with engine.connect() as conn:
        result = conn.exec_driver_sql(f"PRAGMA {pragma_name}").scalar()
    return str(result).lower()


# ---------------------------------------------------------------------------
# Disk-engine pragma tests
# ---------------------------------------------------------------------------


def test_engine_uses_wal_journal_mode_on_disk_db(tmp_path: Path) -> None:
    db_path = tmp_path / "wal_test.db"
    engine = create_db_engine(db_path)
    try:
        assert _pragma(engine, "journal_mode") == "wal"
    finally:
        engine.dispose()


def test_engine_synchronous_normal(tmp_path: Path) -> None:
    db_path = tmp_path / "sync_test.db"
    engine = create_db_engine(db_path)
    try:
        # PRAGMA synchronous returns 1 for NORMAL
        value = _pragma(engine, "synchronous")
        assert value == "1", f"expected synchronous=1 (NORMAL), got {value!r}"
    finally:
        engine.dispose()


def test_engine_busy_timeout_is_5000(tmp_path: Path) -> None:
    db_path = tmp_path / "busy_test.db"
    engine = create_db_engine(db_path)
    try:
        assert _pragma(engine, "busy_timeout") == "5000"
    finally:
        engine.dispose()


def test_engine_foreign_keys_on(tmp_path: Path) -> None:
    db_path = tmp_path / "fk_test.db"
    engine = create_db_engine(db_path)
    try:
        # PRAGMA foreign_keys returns 1 when ON
        assert _pragma(engine, "foreign_keys") == "1"
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# In-memory engine: WAL must NOT be applied
# ---------------------------------------------------------------------------


def test_engine_skips_wal_on_in_memory_db() -> None:
    engine = create_db_engine(":memory:")
    try:
        journal_mode = _pragma(engine, "journal_mode")
        # WAL is incompatible with :memory: — SQLite silently keeps "memory"
        assert journal_mode != "wal", (
            f"journal_mode should not be 'wal' for :memory:, got {journal_mode!r}"
        )
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Concurrent writers — WAL regression guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_writers_dont_raise_database_is_locked(tmp_path: Path) -> None:
    """Five parallel async inserts must all complete without OperationalError.

    Without WAL + busy_timeout, SQLite's default rollback journal serialises
    writers and raises 'database is locked' almost immediately under concurrency.
    """
    db_path = tmp_path / "concurrent.db"
    engine = create_db_engine(db_path)

    try:

        async def _insert_one(i: int) -> None:
            def _do(session: DBSession) -> None:
                event = TelemetryEvent(event_type=f"pragma_test_{i}")
                session.add(event)
                session.commit()

            await _db_async(engine, _do)

        await asyncio.gather(*[_insert_one(i) for i in range(5)])

        # Verify all 5 rows landed
        with engine.connect() as conn:
            count = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM telemetry_events WHERE event_type LIKE 'pragma_test_%'"
            ).scalar()
        assert count == 5, f"expected 5 rows, found {count}"
    finally:
        engine.dispose()
