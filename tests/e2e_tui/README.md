# tests/e2e_tui — TUI flow tests

Surface-aware end-to-end tests for the Textual TUI. Each test file maps
to one user-facing journey from `docs/internal/features/tui.md`. Mirrors
the structure of `tests/e2e_chat/tui/`.

## Patterns to use

1. **Boot via `KaganDriver.boot(tmp_path)`** — real `KaganCore`, real
   DB, real worktree. Single entry point. Use the `tui_driver` fixture.
1. **Mock at the ACP seam** — replace `app.core.chat._acp` with a stub
   *before* `async with app.run_test():`. Restore in `finally`. Never
   mock at the widget level.
1. **`wait_for(predicate, tries=N)`** — predicate-poll for reactive
   state. Re-exported from `tests/helpers/async_utils.py` via
   `tests/e2e_tui/helpers/wait.py`.
1. **Screen transitions** — `app.push_screen(SomeScreen(...))` then
   `await wait_for_screen(app, SomeScreen)`. Type-safe via
   `isinstance(app.screen, SomeScreen)` (`helpers/screens.py`).
1. **Keyboard chords** — `await pilot.press("ctrl+space")`,
   `await pilot.press("h", "i")` for character sequences,
   `await pilot.press("escape")`. No `pilot.send_text` for control
   sequences.
1. **State capture** — prefer widget export methods
   (`panel.export_rendered_messages()`, `widget.children`) over DOM
   scraping. Visual regression stays in `tests/tui/snapshot/**`.
1. **Snapshots** — `inline_snapshot.snapshot()` only on stable
   normalised text. Always pre-process via
   `normalise(text, tmp_root=str(tmp_path))` from
   `tests/e2e_chat/helpers/inline_snapshot_normalisers.py`.
1. **Test isolation** — every test gets a fresh `tmp_path` workdir and
   a fresh `KaganDriver`. Never share state across tests.

## Anti-patterns — do NOT use

1. ❌ `pilot.app.workers.wait_for_complete()` /
   `screen.workers.wait_for_complete()` — hides race conditions,
   especially with orphaned `MarkdownStream` workers (see kg memory
   notes on Textual test timing issues).
1. ❌ `await pilot.pause()` in a loop with bare `assert` after — timing
   dependent.
1. ❌ `await asyncio.sleep(0.5)` before asserting state — burns prompt
   cache, non-deterministic.
1. ❌ Monkeypatching inside `async with app.run_test():` — initialization
   may have already consumed the original value. Patch *before* the
   context manager.
1. ❌ Mocking widgets directly — the seam is `app.core.chat._acp`.
1. ❌ String-id matching on screens (`app.screen.id == "kanban"`) — use
   `isinstance` via `helpers/screens.py`.

## Running

```bash
uv run poe e2e-tui            # run the suite (always -n0)
uv run poe e2e-tui-update     # create / refresh inline snapshots
```

For the full project gate including this suite:

```bash
uv run poe check
```

## Adding a flow

Pick the next free letter (current span is K–T). Use the existing flow
files as templates. Keep each test under ~100 LOC and single-responsibility.
If the feature is not yet surfaced, ship a `pytest.skip(...)` with a
specific reason citation rather than xfail or commented-out code.
