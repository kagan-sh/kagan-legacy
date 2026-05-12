"""End-to-end chat-flow tests across CLI, TUI, web, and vscode surfaces.

All tests in this package use the shipped ``FakeAgentDirector`` (via the
``tests.helpers.fake_agent_backend`` shim) to script deterministic agent
behavior. Output is pinned with ``inline_snapshot`` to keep regressions
visible without a separate golden-file directory.

See ``docs/internal/features/*.md`` for the user-facing flows under test
and ``/Users/aorumbayev/.claude/plans/stateless-petting-steele.md`` for
the rewrite plan.
"""
