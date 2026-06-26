# Tests

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
```
