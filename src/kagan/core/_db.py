import contextlib
import os
import sqlite3
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from loguru import logger
from sqlalchemy import Connection, Engine, event
from sqlmodel import create_engine

_HEAD_REVISION = "6f4d63a80a1e"
_LEGACY_REVISION_REMAP = {
    "5b95758fdb4d": "0001_v060_to_latest",
    "0001_v060_to_latest": "0001_v060_to_latest",
}

logger.disable("sqlalchemy")
logger.disable("alembic")


def _make_alembic_config(database_url: str, connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", "kagan:core/adapters/db/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _normalize_revision_state(config: Config, connection: Connection) -> None:
    current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision is None:
        return

    if remapped := _LEGACY_REVISION_REMAP.get(current_revision):
        command.stamp(config, remapped, purge=True)
        return

    script = ScriptDirectory.from_config(config)
    try:
        if script.get_revision(current_revision) is not None:
            return
    except CommandError:
        pass

    logger.warning(
        "Unknown alembic revision '{}' — stamping to base and re-applying migrations",
        current_revision,
    )
    command.stamp(config, "base", purge=True)


def _run_alembic_upgrade(database_url: str, connection: Connection | None = None) -> None:
    """Run migrations with stdout suppressed to prevent JSON-RPC stream corruption."""
    config = _make_alembic_config(database_url, connection)
    with contextlib.redirect_stdout(StringIO()):
        if connection is not None:
            _normalize_revision_state(config, connection)
        command.upgrade(config, "head")


def _ensure_workspace_fk_compat(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    tables = {
        str(row[0])
        for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "workspaces" in tables:
        return

    schema_rows = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
    )
    has_workspace_refs = any(
        "references workspaces" in str(row[0]).lower() for row in schema_rows if row and row[0]
    )
    if not has_workspace_refs:
        return

    connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS workspaces (id VARCHAR PRIMARY KEY)")


def default_db_path() -> Path:
    kagan_override = os.environ.get("KAGAN_DATA_DIR")
    if kagan_override:
        return Path(kagan_override) / "kagan.db"
    from platformdirs import user_data_dir

    return Path(user_data_dir("kagan", "kagan")) / "kagan.db"


def create_db_engine(db_path: str | Path | None = None) -> Engine:
    resolved = str(db_path) if db_path is not None else str(default_db_path())
    logger.debug("Using database path: {}", resolved)

    if resolved != ":memory:":
        db_file = Path(resolved)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        url = f"sqlite:///{db_file}"
    else:
        url = "sqlite:///:memory:"

    engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    if resolved == ":memory:":
        with engine.begin() as connection:
            with contextlib.redirect_stdout(StringIO()):
                _run_alembic_upgrade(url, connection)
            _ensure_workspace_fk_compat(connection)
    else:
        with contextlib.redirect_stdout(StringIO()):
            with engine.begin() as connection:
                config = _make_alembic_config(url, connection)
                _normalize_revision_state(config, connection)
            _run_alembic_upgrade(url)
        with engine.begin() as connection:
            _ensure_workspace_fk_compat(connection)

    logger.debug("Database engine created and migrations applied")
    return engine


def get_db_version(engine: Engine) -> int:
    with engine.connect() as conn:
        if isinstance(value := conn.exec_driver_sql("PRAGMA data_version").scalar(), int):
            return value
    if value is None:
        raise RuntimeError("SQLite PRAGMA data_version returned no value")
    return int(value)


__all__ = ["create_db_engine", "default_db_path", "get_db_version"]
