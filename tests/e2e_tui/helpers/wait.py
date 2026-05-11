"""Re-export of the canonical :func:`wait_for` predicate-poller.

Use this in every e2e_tui test. Anti-patterns (do NOT use):

- ``app.workers.wait_for_complete()`` / ``screen.workers.wait_for_complete()``
  — hides race conditions, especially with orphaned MarkdownStream workers
  (see kg memory).
- ``await pilot.pause()`` in a loop with bare ``assert`` after — timing
  dependent.
- ``asyncio.sleep(0.5)`` before asserting state — burns prompt cache and
  is non-deterministic.

Prefer:

    await wait_for(lambda: panel._runtime_status == "ready", tries=200)
    await wait_for(lambda: isinstance(app.screen, TaskScreen))
"""

from __future__ import annotations

from tests.helpers.async_utils import wait_for

__all__ = ["wait_for"]
