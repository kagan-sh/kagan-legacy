# Agent Notes

## Toolchain

- Python is pinned to `>=3.14,<3.15`; use `uv`, not raw `pip`.
- Install deps with `uv sync --dev` locally; CI uses `uv sync --frozen --dev` via `.github/actions/setup`.
- Dev commands go through Poe: `uv run poe <task>`.

## Verification

- Full local gate: `uv run poe check` runs `check-syntax`, Ruff lint, Pyrefly, Vulture, import-linter boundaries, then tests.
- Fast/focused tests: `uv run pytest tests/kagan/ -m "unit or smoke" -n auto -q` matches CI fast gate.
- Single test while debugging: `uv run pytest path/to/test.py::test_name -n 0`; repo pytest defaults include `-x -n auto --dist=loadgroup`.
- Docs build: `uv run poe docs-check`; local docs server: `uv run poe docs-dev` uses `config/mkdocs.local.yml` to avoid the social cards libcairo dependency.
- Pre-commit runs gitleaks, mdformat, uv-lock, Ruff, and Pyrefly; baseline setup is `uv sync --dev && pre-commit install`.

## Package Boundaries

- CLI entrypoint is `kagan.cli:cli`; console scripts are `kagan` and `kg`.
- Bare `kagan` launches the interactive session after doctor checks; `kagan tui` is an alias; `kagan _run` is hidden internal runner.
- Public cross-surface domain imports belong in `kagan.core.api` or stable core modules such as `models`, `enums`, `errors`, `doctor_checks`, and `git`.
- `kagan.cli`, `kagan.mcp`, and `kagan.format` must not import `kagan.core.harness` directly; expose new surface needs through `kagan.core.api` and run `uv run poe check-boundaries`.
- `kagan.runtime_env` is a startup leaf and must not import other `kagan` packages.
- Do not add `from __future__ import annotations`; Ruff bans it because Python 3.14 deferred annotations are assumed.

## Tests

- Test tree mirrors `src/kagan/`; add tests under `tests/kagan/{core,cli,mcp,format}/` for the matching package.
- Prefer public imports in new tests; avoid importing `kagan.core._*` internals.
- Use pytest markers from `pyproject.toml` (`unit`, `smoke`, `contract`, `mcp`, `integration`, `windows_ci`, etc.) instead of relying on folder depth for suite selection.
- `tests/conftest.py` redirects XDG and `KAGAN_*` paths into a temp tree; do not assert against real user config/data dirs in tests.
- `uv run poe check-test-quality` rejects tautological tests such as `assert True` and tests whose only assertion is `assert X is not None`.

## Docs And Config

- Published docs live under `docs/`, but MkDocs config is in `config/mkdocs.yml`; paths there are relative to `config/`.
- `.kagan/repo.yaml` is the per-repo manifest modelled by `kagan.core.config.RepoConfig`; relative `review_rubric` paths resolve from the repo root.
- `config/server.json` is the MCP registry metadata and must keep package version in sync with `pyproject.toml` when cutting releases.

## Known Stale Guidance

- Parts of `CONTRIBUTING.md` still reference removed paths/tasks such as `src/kagan/tui/`, `src/kagan/core/prompts/`, and `uv run poe eval`; verify against `pyproject.toml` and current `src/kagan/` before following them.
- The CI snapshot job currently targets `tests/kagan/tui/smoke/`, which is not present in the current tree; do not invent new snapshot paths from that job without checking current tests.
