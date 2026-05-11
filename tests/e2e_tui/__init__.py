"""End-to-end TUI flow tests across screens and overlays.

Each test in this package boots a fresh ``KaganApp`` via
``tests.helpers.driver.KaganDriver.boot`` and drives the user surface
via ``Pilot``. ACP behaviour is scripted through the shipped
``FakeAgentDirector`` (see ``tests.helpers.fake_agent_backend``).

Replaces component-level widget tests in ``tests/tui/test_*.py``. See
``docs/internal/features/tui.md`` for the user-facing flows under test
and ``/Users/aorumbayev/.claude/plans/stateless-petting-steele.md`` for
the rewrite plan.

Anti-patterns (do NOT use):
- ``pilot.app.workers.wait_for_complete()`` / ``wait_for_workers()``
- raw ``asyncio.sleep`` in test loops
- monkeypatch inside ``async with app.run_test()`` body — patch before
"""
