from __future__ import annotations

import pytest

from tests.helpers.wait import wait_until, wait_until_async


@pytest.mark.asyncio
async def test_wait_until_returns_when_predicate_eventually_true() -> None:
    attempts = 0

    def predicate() -> bool:
        nonlocal attempts
        attempts += 1
        return attempts >= 3

    await wait_until(predicate, timeout=0.25, check_interval=0.001, description="attempt threshold")
    assert attempts >= 3


@pytest.mark.asyncio
async def test_wait_until_timeout_includes_description() -> None:
    with pytest.raises(TimeoutError, match="waiting for missing condition"):
        await wait_until(
            lambda: False,
            timeout=0.01,
            check_interval=0.001,
            description="missing condition",
        )


@pytest.mark.asyncio
async def test_wait_until_async_timeout_includes_description() -> None:
    async def predicate() -> bool:
        return False

    with pytest.raises(TimeoutError, match="waiting for async missing condition"):
        await wait_until_async(
            predicate,
            timeout=0.01,
            check_interval=0.001,
            description="async missing condition",
        )
