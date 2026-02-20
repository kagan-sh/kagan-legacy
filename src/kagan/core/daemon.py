"""Dedicated core daemon entrypoint used for detached background startup."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from kagan.core.services.runtime import run_core_host

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Kagan core daemon")
    parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help="Path to Kagan config.toml",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to Kagan SQLite database",
    )
    return parser.parse_args()


async def _run(config_path: Path | None, db_path: Path | None) -> None:
    await run_core_host(config_path=config_path, db_path=db_path)


def main() -> int:
    """Run the core host until it is stopped."""
    args = _parse_args()
    try:
        asyncio.run(_run(args.config_path, args.db_path))
    except KeyboardInterrupt:
        logger.info("Core daemon interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
