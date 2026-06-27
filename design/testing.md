# Testing

Layout mirrors `src/kagan/` (tests outside `src/`, package-shaped tree).

```
tests/
  conftest.py          # session env, xdist groups, shared fixtures
  helpers/             # drivers, fakes — not collected (import submodules directly)
  kagan/               # mirrors src/kagan/
    core/
    cli/
    format/            # pure Rich renderers (render -> string asserts)
    mcp/
```

## Where to add a test

| Changed             | Path                  |
| ------------------- | --------------------- |
| `src/kagan/core/`   | `tests/kagan/core/`   |
| `src/kagan/cli/`    | `tests/kagan/cli/`    |
| `src/kagan/mcp/`    | `tests/kagan/mcp/`    |
| `src/kagan/format/` | `tests/kagan/format/` |

Use markers (e.g. `unit`, `smoke`, `contract`) — not folder depth — to choose CI speed.

## Imports

Prefer public imports (`kagan.core.api`, `kagan.core.doctor_checks`) in new tests — do not import `kagan.core._*` internal modules.

## Commands

```bash
uv run pytest tests/ -n auto         # fast gate
uv run poe check                     # full gate
uv run poe check-test-quality        # tautology + private-reach-in + over-mock lint
```

## Test quality commandments

An audit of the suite (~631 test functions) found smells behind rules 1–3 and 7–8 already at ~0 suite-wide; the live debt is rules 5 and 6, concentrated in `tests/kagan/cli/test_session.py`. `scripts/check_test_quality.py` enforces the [linted] rules; the rest are review checklist items.

1. **Assert a consequence, not a round-trip.** [review] If an assert only proves "the literal I injected came back out", it guards a bare setter — delete or strengthen it.
1. **The test name is a claim; it must be able to fail on that claim.** [review] A test named for an invariant must exercise that invariant, not an adjacent step.
1. **Cover the dangerous branch, not just the happy path.** [review] The valuable case is the empty/placeholder input that MUST keep a gate locked.
1. **Test through the narrowest public seam.** [review] Prefer the public API; mock at most the I/O edge (input pipe, subprocess spawn, clock, network), never the code under test.
1. **Don't over-mock the unit's own privates.** [linted — depth≥3 fatal] Stubbing many private methods of the SUT tests wiring between privates, not behavior. A branch-matrix unit test may stub ONE frame method to inject a verb sequence; promote anything heavier.
1. **Don't assert on privates.** [linted — fatal] Assert public return values / public state, not `obj._x`. Read private functions through their public callers.
1. **Mock only what you don't own or can't control.** [review]
1. **Parametrize equivalence classes instead of asserting one magic literal.** [review]

Inline exemptions for rule 6 or 5 use `# check-test-quality: noqa <rule> -- <reason>` on the flagged line.
